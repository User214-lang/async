import aiohttp
import asyncio
import logging
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET
from typing import List, Optional

logger = logging.getLogger(__name__)


class SitemapParser:
    def __init__(self, session: Optional[aiohttp.ClientSession] = None, max_urls: int = 50000):
        self._session = session
        self.max_urls = max_urls
        self._visited_sitemaps = set()

    async def _fetch_xml(self, url: str) -> str:
        close_session = False
        if self._session is None:
            self._session = aiohttp.ClientSession()
            close_session = True
        try:
            async with self._session.get(url, timeout=30) as response:
                response.raise_for_status()
                return await response.text()
        finally:
            if close_session and self._session:
                await self._session.close()
                self._session = None

    def _parse_sitemap_urls(self, xml_content: str, base_url: str) -> List[str]:
        urls = []
        try:
            root = ET.fromstring(xml_content)
            for loc in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                url = loc.text
                if url:
                    urls.append(url)
        except ET.ParseError as e:
            logger.error(f"Ошибка парсинга XML: {e}")
        return urls

    def _parse_sitemap_index(self, xml_content: str, base_url: str) -> List[str]:
        #Извлечение url из индексного sitemap (теги <sitemap><loc>)
        sitemap_urls = []
        try:
            root = ET.fromstring(xml_content)
            for loc in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                url = loc.text
                if url:
                    sitemap_urls.append(url)
        except ET.ParseError as e:
            logger.error(f"Ошибка парсинга XML: {e}")
        return sitemap_urls

    async def fetch_sitemap(self, sitemap_url: str) -> List[str]:
        # Рекурсивнfz обработка подчиненных sitemap
    
        if sitemap_url in self._visited_sitemaps:
            logger.debug(f"Sitemap уже обработан: {sitemap_url}")
            return []
        self._visited_sitemaps.add(sitemap_url)

        logger.info(f"Загрузка sitemap: {sitemap_url}")
        try:
            xml_content = await self._fetch_xml(sitemap_url)
        except Exception as e:
            logger.error(f"Ошибка загрузки sitemap {sitemap_url}: {e}")
            return []

        if '<sitemapindex' in xml_content.lower():
            child_sitemaps = self._parse_sitemap_index(xml_content, sitemap_url)
            all_urls = []
            for child_url in child_sitemaps:
                child_urls = await self.fetch_sitemap(child_url)
                all_urls.extend(child_urls)
                if len(all_urls) >= self.max_urls:
                    logger.warning(f"Достигнут лимит URL ({self.max_urls}), остановка обработки")
                    break
            return all_urls[:self.max_urls]
        else:
            #Обычный sitemap
            urls = self._parse_sitemap_urls(xml_content, sitemap_url)
            if len(urls) > self.max_urls:
                urls = urls[:self.max_urls]
            logger.info(f"Извлечено {len(urls)} URL из {sitemap_url}")
            return urls

    async def get_urls_from_sitemap(self, sitemap_url: str) -> List[str]:
        self._visited_sitemaps.clear()
        return await self.fetch_sitemap(sitemap_url)