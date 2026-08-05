import asyncio
import aiohttp
import logging
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse, urljoin
from typing import Dict, Optional
import time

logger = logging.getLogger(__name__)


class RobotsParser:
    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._cache: Dict[str, RobotFileParser] = {}
        self._crawl_delay_cache: Dict[str, float] = {}
        self._last_request_time: Dict[str, float] = {}
        self._default_crawl_delay = 1.0

    async def fetch_robots(self, base_url: str) -> dict:
        domain = urlparse(base_url).netloc
        if domain in self._cache:
            return {'crawl_delay': self._crawl_delay_cache.get(domain, self._default_crawl_delay)}

        robots_url = urljoin(base_url, "/robots.txt")
        parser = RobotFileParser()
        close_session = False
        if self._session is None:
            self._session = aiohttp.ClientSession()
            close_session = True

        crawl_delay = self._default_crawl_delay
        try:
            async with self._session.get(robots_url, timeout=5) as response:
                if response.status == 200:
                    content = await response.text()
                    parser.parse(content.splitlines())
                    crawl_delay = self._extract_crawl_delay(content)
                    self._cache[domain] = parser
                    self._crawl_delay_cache[domain] = crawl_delay
                    logger.info(f"Robots.txt для {domain} загружен, crawl_delay={crawl_delay}")
                else:
                    self._cache[domain] = RobotFileParser()
                    self._crawl_delay_cache[domain] = self._default_crawl_delay
                    logger.warning(f"Robots.txt для {domain} не загружен (статус {response.status})")

        except asyncio.TimeoutError:
            logger.warning(f"Таймаут загрузки robots.txt для {domain}")
            self._cache[domain] = RobotFileParser()
            self._crawl_delay_cache[domain] = self._default_crawl_delay
        except Exception as e:
            logger.error(f"Ошибка загрузки robots.txt для {domain}: {e}")
            self._cache[domain] = RobotFileParser()
            self._crawl_delay_cache[domain] = self._default_crawl_delay
        finally:
            if close_session and self._session:
                await self._session.close()
                self._session = None

        return {'crawl_delay': crawl_delay}

    def _extract_crawl_delay(self, content: str) -> float:
        for line in content.splitlines():
            line = line.strip()
            if line.lower().startswith('crawl-delay:'):
                try:
                    delay = float(line.split(':', 1)[1].strip())
                    if delay > 0:
                        return delay
                except ValueError:
                    pass
        return self._default_crawl_delay

    def can_fetch(self, url: str, user_agent: str = "*") -> bool:
        domain = urlparse(url).netloc
        parser = self._cache.get(domain)
        if parser is None:
            return True
        try:
            return parser.can_fetch(user_agent, url)
        except Exception:
            return True

    def get_crawl_delay(self, domain: str) -> float:
        return self._crawl_delay_cache.get(domain, self._default_crawl_delay)

    async def wait_for_crawl_delay(self, domain: str, user_agent: str = "*") -> None:
        key = (domain, user_agent)
        crawl_delay = self._crawl_delay_cache.get(key, self._default_crawl_delay)
        if crawl_delay <= 0:
            return
        now = time.monotonic()
        last = self._last_request_time.get(domain, 0)
        elapsed = now - last
        if elapsed < crawl_delay:
            wait_time = crawl_delay - elapsed
            logger.debug(f"Ожидание {wait_time:.2f} сек для домена {domain} (Crawl-delay для {user_agent})")
            await asyncio.sleep(wait_time)
        self._last_request_time[domain] = time.monotonic()
    async def ensure_robots_fetched(self, url: str, user_agent: str = "*") -> None:
        domain = urlparse(url).netloc
        if (domain, user_agent) not in self._cache:
            await self.fetch_robots(url)

    def is_allowed(self, url: str, user_agent: str = "*") -> bool:
        domain = urlparse(url).netloc
        key = (domain, user_agent)
        parser = self._cache.get(key)
        if parser is None:
            return True
        try:
            return parser.can_fetch(user_agent, url)
        except Exception:
            return True