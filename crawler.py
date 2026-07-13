import asyncio
import aiohttp
import logging
import time
from typing import List, Dict, Union, Optional
from parser import HTMLParser
from queue_manager import CrawlerQueue
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AsyncCrawler:

    def __init__(
        self,
        max_concurrent: int = 10,
        timeout_total: int = 30,
        timeout_connect: int = 5,
        timeout_read: int = 5,
        limit_connections: int = 100,
        limit_per_host: int = 30
    ):
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self.queue = CrawlerQueue()

        timeout = aiohttp.ClientTimeout(
            total=timeout_total,
            connect=timeout_connect,
            sock_read=timeout_read
        )

        connector = aiohttp.TCPConnector(
            limit=limit_connections,
            limit_per_host=limit_per_host,
            ttl_dns_cache=300
        )

        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={'User-Agent': 'AsyncCrawler/1.0'}
        )

        logger.info(
            f"Краулер инициализирова, max_concurrent={max_concurrent}, "
            f"Таймауты: total={timeout_total}, connect={timeout_connect}, read={timeout_read}, "
            f"Пул: limit={limit_connections}, per_host={limit_per_host}"
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def fetch_url(self, url: str) -> str:
        async with self._semaphore:
            start_time = time.monotonic()
            logger.info(f"Start: {url}")

            try:
                async with self._session.get(url) as response:
                    response.raise_for_status()
                    html = await response.text()
                    elapsed = time.monotonic() - start_time
                    logger.info(
                        f"Успешно загружена: {url} "
                        f"(размер: {len(html)} байт, время: {elapsed} c)"
                    )
                    return html

            #http-ошибки
            except aiohttp.ClientResponseError as e:
                elapsed = time.monotonic() - start_time
                if e.status >= 500:
                    logger.error(
                        f"Ошибка сервера {e.status} для {url} - Сам дурак "
                        f"(время: {elapsed:.2f} с)"
                )
                elif 400 <= e.status < 500:
                    logger.error(
                        f"Ошибка клиента {e.status} для {url} - Неверный запрос"
                        f"(время: {elapsed:.2f} с)"
                )
                else:
                    logger.error(
                    f"HTTP ошибка {e.status} для {url}: {e.message} "
                    f"(время: {elapsed:.2f} с)"
                )
                raise

            #Сетевые ошикби
            except aiohttp.ClientError as e:
                elapsed = time.monotonic() - start_time
                logger.error(
                    f"Сетевая ошибка для {url}: {type(e).__name__} - {str(e)} "
                    f"(время: {elapsed:.2f} с)"
                )
                raise

            except asyncio.TimeoutError:
                elapsed = time.monotonic() - start_time
                logger.error(
                    f"Таймаут при загрузке {url} "
                    f"(время: {elapsed:.2f} с)"
                )
                raise

            except Exception as e:
                elapsed = time.monotonic() - start_time
                logger.error(
                    f"Неизвестная ошибка для {url}: {type(e).__name__} - {str(e)} "
                    f"(время: {elapsed:.2f} с)"
                )
                raise

    async def fetch_urls(self, urls: List[str]) -> Dict[str, Union[str, str]]:
        #Параллельная загрузка

        logger.info(f"Загрузка {len(urls)} URL")
        total_start = time.monotonic()
        tasks = [self.fetch_url(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {}
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                error_type = type(result).__name__
                error_msg = str(result)
                output[url] = f"ERROR: {error_type} - {error_msg}"
            else:
                output[url] = result

        success = sum(1 for v in output.values() if not v.startswith("ERROR:"))
        total_elapsed = time.monotonic() - total_start
        logger.info(
            f"Успешно загружены: {success}, ошибок: {len(urls) - success}, "
            f"Oбщее время: {total_elapsed:.2f} с"
        )
        return output

    async def fetch_and_parse(
    self,
    url: str,
    filter_external: bool = False,
    allowed_domains: Optional[List[str]] = None
) -> dict:
    
        try:
            html = await self.fetch_url(url)
        except Exception as e:
            return {
            'url': url,
            'error': str(e),
            'title': '',
            'text': '',
            'links': [],
            'metadata': {},
            'images': [],
            'headings': {'h1': [], 'h2': [], 'h3': []},
            'tables': [],
            'lists': {'ul': [], 'ol': []}
        }

        parser = HTMLParser()
        parsed = await parser.parse_html(
            html,
            url,
            filter_external=filter_external,
            allowed_domains=allowed_domains
    )

        return {
            'url': parsed['url'],
            'title': parsed['title'],
            'text': parsed['text'],
            'links': parsed['links'],
            'metadata': {
                'description': parsed.get('description', ''),
                'keywords': parsed.get('keywords', '')
            },
            'images': parsed['images'],
            'headings': parsed['headings'],
            'tables': parsed['tables'],
            'lists': parsed['lists']
        }



    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("Сессия закрыта")

    async def crawl(
        self,
        start_urls: list[str],
        max_pages: int = 100,
        max_depth: int = 3,
        same_domain_only: bool = True,
        exclude_patterns: Optional[List[str]] = None,
        include_patterns: Optional[List[str]] = None
    ) -> Dict[str, str]:
        base_domain = None
        if same_domain_only and start_urls:
            from urllib.parse import urlparse
            base_domain = urlparse(start_urls[0]).netloc

        for url in start_urls:
            await self.queue.add_url(url, priority=0, depth=0)

        results = {}
        processed = 0
        start_time = time.monotonic()
        last_print_time = start_time
        print_interval = 1.0

        while not self.queue.is_empty and processed < max_pages:
            item = await self.queue.get_next()
            if item is None:
                break

            url, depth = item

            if depth > max_depth:
                logger.debug(f"Пропуск {url} из-за глубины {depth} > {max_depth}")
                continue

            try:
                html = await self.fetch_url(url)
                self.queue.mark_processed(url)
                results[url] = html
                processed += 1

                parser = HTMLParser()
                soup = BeautifulSoup(html, 'lxml')
                links = parser.extract_links(soup, url, filter_external=False)

                for link in links:
                    if same_domain_only:
                        from urllib.parse import urlparse
                        link_domain = urlparse(link).netloc
                        if link_domain != base_domain:
                            continue

                    if exclude_patterns:
                        if any(pattern in link for pattern in exclude_patterns):
                            continue
                    if include_patterns:
                        if not any(pattern in link for pattern in include_patterns):
                            continue

                    await self.queue.add_url(link, priority=1, depth=depth + 1)

            except Exception as e:
                self.queue.mark_failed(url, str(e))
                results[url] = f"ERROR: {e}"

            now = time.monotonic()
            if now - last_print_time >= print_interval:
                stats = self.queue.get_stats()
                elapsed = now - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"[{elapsed:.1f}с] Обработано: {processed}, "
                    f"В очереди: {stats['pending']}, Ошибок: {stats['total_failed']}, "
                    f"Скорость: {rate:.2f} стр/с")
                last_print_time = now

        elapsed = time.monotonic() - start_time
        stats = self.queue.get_stats()
        print("Итоговая статистика:\n")
        print(f"Обработано страниц: {processed}")
        print(f"Всего добавлено: {stats['total_added']}")
        print(f"Успешно: {stats['total_processed']}, Ошибок: {stats['total_failed']}")
        print(f"Время работы: {elapsed:.2f} с")
        print(f"Средняя скорость: {processed / elapsed:.2f} стр/с")

        return results