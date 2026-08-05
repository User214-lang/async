import asyncio
import aiohttp
import logging
import time
from datetime import datetime
import random
from typing import List, Dict, Union, Optional
from parser import HTMLParser
from queue_manager import CrawlerQueue
from bs4 import BeautifulSoup
from semaphore_manager import SemaphoreManager
from urllib.parse import urlparse
from rate_limiter import RateLimiter
from robots_parser import RobotsParser
from retry_strategy import RetryStrategy
from exceptions import TransientError, PermanentError, NetworkError, ParseError, RateLimitError
from circuit_breaker import CircuitBreakerManager, CircuitBreakerOpenError
from storage import DataStorage
from crawler_stats import CrawlerStats
from sitemap_parser import SitemapParser

logger = logging.getLogger(__name__)


class AsyncCrawler:

    def __init__(
        self,
        max_concurrent: int = 10,
        timeout_total: int = 30,
        timeout_connect: int = 5,
        timeout_read: int = 5,
        timeout_increase_factor: float = 1.5,
        max_timeout_total: int = 120,
        max_timeout_connect: int = 30,
        max_timeout_read: int = 30,
        limit_connections: int = 100,
        limit_per_host: int = 30,
        requests_per_second: float = 5.0,
        per_domain_limit: int = 5,
        min_delay: float = 0.5,
        jitter: float = 0.3,
        backoff_factor: float = 2.0,
        max_backoff: float = 60.0,
        user_agent: Union[str, List[str]] = "AsyncCrawler/1.0",
        retry_max_attempts: int = 3,
        retry_backoff_factor: float = 2.0,
        retry_on: Optional[tuple] = None,
        transient_retry_max: Optional[int] = None,
        transient_retry_backoff: Optional[float] = None,
        network_retry_max: Optional[int] = None,
        network_retry_backoff: Optional[float] = None,
        rate_limit_retry_max: Optional[int] = None,
        rate_limit_retry_backoff: Optional[float] = None,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_window: float = 60.0,
        circuit_breaker_cooldown: float = 30.0,
        storage: Optional[DataStorage] = None,
        save_retry_attempts: int = 3,
        save_retry_delay: float = 1.0,
        respect_robots: bool = True,
        sitemap_url: Optional[str] = None
        ):

        self.max_concurrent = max_concurrent
        self._semaphore = SemaphoreManager(
        global_limit=max_concurrent,
        per_domain_limit=per_domain_limit
        )
        self.queue = CrawlerQueue()

        if isinstance(user_agent, str):
            self.user_agents = [user_agent]
        else:
            self.user_agents = user_agent
        self._current_agent_index = 0

        self.visited_urls = set()
        self.failed_urls = {}
        self.processed_urls = {}

        self.total_requests = 0
        self.total_time = 0.0
        self.blocked_by_robots = 0

        self.timeout_total = timeout_total
        self.timeout_connect = timeout_connect
        self.timeout_read = timeout_read
        self.timeout_increase_factor = timeout_increase_factor
        self.max_timeout_total = max_timeout_total
        self.max_timeout_connect = max_timeout_connect
        self.max_timeout_read = max_timeout_read

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
            #headers={'User-Agent': 'AsyncCrawler/1.0'}
        )
        self.rate_limiter = RateLimiter(
            requests_per_second=requests_per_second,
            per_domain=True,
            min_delay=min_delay,
            jitter=jitter,
            backoff_factor=backoff_factor,
            max_backoff=max_backoff
        )
        self.robots_parser = RobotsParser(session=self._session)

        self.retry_strategy = RetryStrategy(
        max_retries=retry_max_attempts,
        backoff_factor=retry_backoff_factor,
        retry_on=retry_on,
        transient_max_retries=transient_retry_max,
        transient_backoff_factor=transient_retry_backoff,
        network_max_retries=network_retry_max,
        network_backoff_factor=network_retry_backoff,
        rate_limit_max_retries=rate_limit_retry_max,
        rate_limit_backoff_factor=rate_limit_retry_backoff
    )

        self.circuit_breaker = CircuitBreakerManager(
        error_threshold=circuit_breaker_threshold,
        time_window=circuit_breaker_window,
        cooldown=circuit_breaker_cooldown
        )

        self.error_stats = {}
        self.permanent_error_urls = set()

        self.storage = storage

        self.save_retry_attempts = save_retry_attempts
        self.save_retry_delay = save_retry_delay
        self.respect_robots = respect_robots

        self.stats = CrawlerStats()

        self.requests_per_second = requests_per_second
        self.sitemap_parser = SitemapParser(session=self._session)
        self._initial_sitemap_url = sitemap_url

        logger.info(
            f"Краулер инициализирова, max_concurrent={max_concurrent}, "
            f"Таймауты: total={timeout_total}, connect={timeout_connect}, read={timeout_read}, "
            f"Пул: limit={limit_connections}, per_host={limit_per_host}"
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _get_user_agent(self) -> str:
        return random.choice(self.user_agents)

    async def _fetch_internal(self, url: str, user_agent: str) -> tuple:
        try:
            attempt = self.retry_strategy.attempts
            if attempt > 1:
                factor = self.timeout_increase_factor ** (attempt - 1)
                total = min(self.timeout_total * factor, self.max_timeout_total)
                connect = min(self.timeout_connect * factor, self.max_timeout_connect)
                read = min(self.timeout_read * factor, self.max_timeout_read)
                timeout = aiohttp.ClientTimeout(total=total, connect=connect, sock_read=read)
            else:
                timeout = self._session.timeout

            async with self._session.get(url, headers={'User-Agent': user_agent}, timeout=timeout) as response:
                response.raise_for_status()
                html = await response.text()
                status = response.status
                content_type = response.headers.get('Content-Type', '')
                return html, status, content_type
        except asyncio.TimeoutError as e:
            raise NetworkError(f"Timeout: {e}") from e
        except aiohttp.ClientResponseError as e:
            if e.status == 429:
                raise RateLimitError(f"{e.status} {e.message}") from e
            elif e.status >= 500 or e.status == 503:
                raise TransientError(f"{e.status} {e.message}") from e
            elif 400 <= e.status < 500:
                raise PermanentError(f"{e.status} {e.message}") from e
            else:
                raise TransientError(f"Unknown HTTP {e.status}") from e
        except aiohttp.ClientError as e:
            raise NetworkError(f"{type(e).__name__}: {e}") from e
        
    async def fetch_url(self, url: str) -> str:
        html, _, _ = await self.fetch_url_with_meta(url)
        return html

    async def fetch_url_with_meta(self, url: str) -> tuple:
        logger.info(f"fetch_url_with_meta вызван для {url}")
        domain = urlparse(url).netloc

        if not self.circuit_breaker.is_allowed(domain):
            logger.warning(f"Домен {domain} временно заблокирован Circuit Breaker")
            raise CircuitBreakerOpenError(f"Домен {domain} заблокирован")

        user_agent = self._get_user_agent()

        if self.respect_robots:
            await self.robots_parser.ensure_robots_fetched(url, user_agent)
            if not self.robots_parser.is_allowed(url, user_agent):
                logger.warning(f"URL запрещён robots.txt: {url}")
                self.blocked_by_robots += 1
                raise PermissionError(f"URL {url} запрещён robots.txt для {user_agent}")

        await self.rate_limiter.acquire(domain)
        await self.robots_parser.wait_for_crawl_delay(domain, user_agent)
        await self._semaphore.acquire(domain)

        start_time = time.monotonic()
        logger.info(f"Start: {url} (User-Agent: {user_agent})")

        try:
            html, status, content_type = await self.retry_strategy.execute_with_retry(
                self._fetch_internal, url, user_agent
            )
            self.circuit_breaker.record_success(domain)
            elapsed = time.monotonic() - start_time
            self.total_requests += 1
            self.total_time += elapsed
            self.stats.record_success(url, status, elapsed)
            logger.info(
                f"Успешно загружена: {url} "
                f"(размер: {len(html)} байт, время: {elapsed:.2f} с)"
            )
            self.rate_limiter.record_success(domain)
            return html, status, content_type

        except (TransientError, NetworkError, RateLimitError) as e:
            elapsed = time.monotonic() - start_time
            attempts = self.retry_strategy.attempts
            error_type = type(e).__name__
            self.error_stats[error_type] = self.error_stats.get(error_type, 0) + 1
            self.stats.record_failure(url, error_type)
            details = self.retry_strategy._attempt_details[-1] if self.retry_strategy._attempt_details else {}
            delay = details.get('delay', 0)
            logger.error(
                f"Временная ошибка {error_type} для {url} "
                f"(время: {elapsed:.2f} с, попыток: {attempts}, задержка до следующей: {delay:.2f}с)"
            )
            self.rate_limiter.record_failure(domain)
            self.circuit_breaker.record_failure(domain)
            self.failed_urls[url] = str(e)
            raise

        except PermanentError as e:
            elapsed = time.monotonic() - start_time
            attempts = self.retry_strategy.attempts
            error_type = type(e).__name__
            self.error_stats[error_type] = self.error_stats.get(error_type, 0) + 1
            self.stats.record_failure(url, error_type)
            self.permanent_error_urls.add(url)
            details = self.retry_strategy._attempt_details[-1] if self.retry_strategy._attempt_details else {}
            delay = details.get('delay', 0)
            logger.error(
                f"Постоянная ошибка {error_type} для {url} "
                f"(время: {elapsed:.2f} с, попыток: {attempts}, задержка до следующей: {delay:.2f}с)"
            )
            self.rate_limiter.record_failure(domain)
            self.failed_urls[url] = str(e)
            raise

        except Exception as e:
            elapsed = time.monotonic() - start_time
            attempts = self.retry_strategy.attempts
            error_type = type(e).__name__
            self.error_stats[error_type] = self.error_stats.get(error_type, 0) + 1
            self.stats.record_failure(url, error_type)
            self.permanent_error_urls.add(url)
            details = self.retry_strategy._attempt_details[-1] if self.retry_strategy._attempt_details else {}
            delay = details.get('delay', 0)
            logger.error(
                f"Неизвестная ошибка для {url}: {error_type} - {str(e)} "
                f"(время: {elapsed:.2f} с, попыток: {attempts}, задержка до следующей: {delay:.2f}с)"
            )
            self.rate_limiter.record_failure(domain)
            self.circuit_breaker.record_failure(domain)
            self.failed_urls[url] = str(e)
            raise

        finally:
            self._semaphore.release(domain)

    async def _save_data(self, url: str, html: str, parsed: dict, status: int, content_type: str) -> None:
        if self.storage is None:
            return
        data = {
            'url': url,
            'title': parsed.get('title', ''),
            'text': parsed.get('text', ''),
            'links': parsed.get('links', []),
            'metadata': parsed.get('metadata', {}),
            'crawled_at': datetime.now().isoformat(),
            'status_code': status,
            'content_type': content_type,
            'text_length': len(parsed.get('text', '')),
            'images': parsed.get('images', []),
            'headings': parsed.get('headings', {}),
            'error': ''
        }
        for attempt in range(1, self.save_retry_attempts + 1):
            try:
                await self.storage.save(data)
                logger.debug(f"Данные сохранены для {url} (попытка {attempt})")
                return
            except Exception as e:
                if attempt == self.save_retry_attempts:
                    logger.error(f"Не удалось сохранить данные для {url} после {attempt} попыток: {e}")
                    #Не пробрасываем исключение, продолжаем работу
                    return
                delay = self.save_retry_delay * (2 ** (attempt - 1))
                logger.warning(f"Ошибка сохранения для {url} (попытка {attempt}): {e}. Повтор через {delay:.2f}с")
                await asyncio.sleep(delay)

    async def _save_error(self, url: str, error: str) -> None:
        if self.storage is None:
            return
        data = {
            'url': url,
            'error': error,
            'crawled_at': datetime.now().isoformat(),
            'status_code': 0,
            'content_type': '',
            'text': '',
            'title': '',
            'links': [],
            'metadata': {}
        }
        for attempt in range(1, self.save_retry_attempts + 1):
            try:
                await self.storage.save(data)
                logger.debug(f"Ошибка сохранена для {url} (попытка {attempt})")
                return
            except Exception as e:
                if attempt == self.save_retry_attempts:
                    logger.error(f"Не удалось сохранить ошибку для {url} после {attempt} попыток: {e}")
                    return
                delay = self.save_retry_delay * (2 ** (attempt - 1))
                logger.warning(f"Ошибка сохранения ошибки для {url} (попытка {attempt}): {e}. Повтор через {delay:.2f}с")
                await asyncio.sleep(delay)

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
        allowed_domains = set()
        if same_domain_only and start_urls:
            for start_url in start_urls:
                domain = urlparse(start_url).netloc
                if domain:
                    allowed_domains.add(domain)

        for url in start_urls:
            await self.queue.add_url(url, priority=0, depth=0)

        results = {}
        processed = 0
        start_time = time.monotonic()
        last_print_time = start_time
        print_interval = 1.0
        workers = self.max_concurrent

        async def worker():
            nonlocal processed, last_print_time
            while not self.queue.is_empty and processed < max_pages:
                logger.debug(f"Воркер: очередь не пуста? {not self.queue.is_empty}, processed={processed}, max_pages={max_pages}")
                item = await self.queue.get_next()
                if item is None:
                    break
                url, depth = item

                if depth > max_depth:
                    logger.debug(f"Пропуск {url} из-за глубины {depth} > {max_depth}")
                    continue

                try:
                    html, status, content_type = await self.fetch_url_with_meta(url)
                    self.processed_urls[url] = html
                    self.visited_urls.add(url)
                    results[url] = html
                    processed += 1

                    parser = HTMLParser()
                    soup = BeautifulSoup(html, 'lxml')
                    parsed = await parser.parse_html(html, url)
                    await self._save_data(url, html, parsed, status, content_type)
                    links = parser.extract_links(soup, url, filter_external=False)

                    for link in links:
                        if same_domain_only:
                            link_domain = urlparse(link).netloc
                            if link_domain not in allowed_domains:
                                continue
                        if exclude_patterns:
                            if any(pattern in link for pattern in exclude_patterns):
                                continue
                        if include_patterns:
                            if not any(pattern in link for pattern in include_patterns):
                                continue
                        await self.queue.add_url(link, priority=1, depth=depth + 1)

                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Ошибка при обработке {url}: {type(e).__name__} - {str(e)}")
                    self.failed_urls[url] = str(e)
                    self.visited_urls.add(url)
                    results[url] = f"ERROR: {e}"
                    await self._save_error(url, str(e))

                now = time.monotonic()
                if now - last_print_time >= print_interval:
                    stats = self.queue.get_stats()
                    elapsed = now - start_time
                    rate = self.total_requests / elapsed if elapsed > 0 else 0
                    avg_delay = self.total_time / self.total_requests if self.total_requests > 0 else 0
                    if max_pages > 0:
                        progress = (processed / max_pages) * 100
                    else:
                        progress = 0.0
                    if rate > 0 and processed < max_pages:
                        remaining = (max_pages - processed) / rate
                    else:
                        remaining = 0.0

                    bar_length = 30
                    filled = int(bar_length * processed / max_pages) if max_pages > 0 else 0
                    bar = '█' * filled + '░' * (bar_length - filled)
                    print(f"\r[{elapsed:.1f}с] {bar} {progress:.1f}% | {processed}/{max_pages} стр | "
                        f"Скорость: {rate:.2f} стр/с | Осталось: {remaining:.1f}с | "
                        f"Очередь: {stats['pending']} | Ошибки: {len(self.failed_urls)} | "
                        f"Активно: {workers} задач", end='')
                    last_print_time = now
            
        logger.info(f"Запуск {workers} воркеров. В очереди: {self.queue.size}")
        await asyncio.gather(*[worker() for w in range(workers)])
        if self.storage:
            await self.storage.close()

        self.stats.finish()
        #self.stats.print_stats()
        elapsed = time.monotonic() - start_time
        avg_delay = self.total_time / self.total_requests if self.total_requests > 0 else 0

        print("Итоговая статистика:\n")
        print(f"Обработано страниц: {processed}")
        print(f"Всего добавлено: {self.queue.get_stats()['total_added']}")
        print(f"Успешно: {len(self.processed_urls)}, Ошибок: {len(self.failed_urls)}")
        print(f"Блокировано robots.txt: {self.blocked_by_robots}")
        print(f"Время работы: {elapsed:.2f} с")
        print(f"Средняя скорость запросов: {self.total_requests / elapsed:.2f} req/s")
        print(f"Средняя задержка: {avg_delay:.2f} с")


        print("\nСтатистика ошибок:")
        for err_type, count in self.error_stats.items():
            print(f"  {err_type}: {count}")
        print(f"  URL с постоянными ошибками: {len(self.permanent_error_urls)}")
        if self.permanent_error_urls:
            print("  Примеры:", list(self.permanent_error_urls)[:5])

        retry_stats = self.retry_strategy.get_retry_stats()
        print(f"Успешных повторов: {retry_stats['successful_retries']}")
        avg_retry_time = retry_stats['total_retry_time'] / retry_stats['successful_retries'] if retry_stats['successful_retries'] > 0 else 0
        print(f"Среднее время на повтор: {avg_retry_time:.2f}с")


        return results
        print()

