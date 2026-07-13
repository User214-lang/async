import logging
from typing import List, Dict, Optional, Any
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


class HTMLParser:

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)

    @staticmethod
    def _get_domain(url: str) -> str:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain

    @classmethod
    def extract_links(
        cls,
        soup: BeautifulSoup,
        base_url: str,
        filter_external: bool = False,
        allowed_domains: Optional[List[str]] = None
    ) -> List[str]:
        links = []

        base_domain = cls._get_domain(base_url) if filter_external else None
        allowed_domains_set = set(allowed_domains) if allowed_domains else set()
        allowed_domains_set.add(base_domain) if base_domain else None

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            absolute_url = urljoin(base_url, href)
            if not absolute_url or absolute_url.startswith('#'):
                continue
            if not cls._is_valid_url(absolute_url):
                continue
            if filter_external:
                link_domain = cls._get_domain(absolute_url)
                if allowed_domains_set:
                    if link_domain not in allowed_domains_set:
                        continue
                else:
                    if link_domain != base_domain:
                        continue
            links.append(absolute_url)

        seen = set()
        unique_links = []
        for link in links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)
        return unique_links

    @staticmethod
    def extract_text(soup: BeautifulSoup, selector: Optional[str] = None) -> str:
        if selector:
            elements = soup.select(selector)
            text = ' '.join(el.get_text(strip=True) for el in elements)
        else:
            text = soup.get_text(separator=' ', strip=True)
        return text

    @staticmethod
    def extract_metadata(soup: BeautifulSoup) -> Dict[str, str]:
        metadata = {'title': '', 'description': '', 'keywords': ''}
        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get_text(strip=True)

        for meta in soup.find_all('meta'):
            if meta.get('name') == 'description':
                metadata['description'] = meta.get('content', '')
            elif meta.get('name') == 'keywords':
                metadata['keywords'] = meta.get('content', '')
        return metadata

    @staticmethod
    def extract_images(soup: BeautifulSoup) -> List[Dict[str, str]]:
        images = []
        for img in soup.find_all('img'):
            src = img.get('src', '')
            alt = img.get('alt', '')
            if src:
                images.append({'src': src, 'alt': alt})
        return images

    @staticmethod
    def extract_headings(soup: BeautifulSoup) -> Dict[str, List[str]]:
        headings = {'h1': [], 'h2': [], 'h3': []}
        for level in ['h1', 'h2', 'h3']:
            for tag in soup.find_all(level):
                text = tag.get_text(strip=True)
                if text:
                    headings[level].append(text)
        return headings

    @staticmethod
    def extract_tables(soup: BeautifulSoup) -> List[List[List[str]]]:
        tables = []
        for table in soup.find_all('table'):
            rows = []
            for tr in table.find_all('tr'):
                cells = []
                for td in tr.find_all(['td', 'th']):
                    cells.append(td.get_text(strip=True))
                if cells:
                    rows.append(cells)
            if rows:
                tables.append(rows)
        return tables

    @staticmethod
    def extract_lists(soup: BeautifulSoup) -> Dict[str, List[str]]:
        lists = {'ul': [], 'ol': []}
        for list_type in ['ul', 'ol']:
            for lst in soup.find_all(list_type):
                for li in lst.find_all('li', recursive=False):
                    text = li.get_text(strip=True)
                    if text:
                        lists[list_type].append(text)
        return lists

    async def parse_html(
        self,
        html: str,
        url: str,
        filter_external: bool = False,
        allowed_domains: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        try:
            soup = BeautifulSoup(html, 'lxml')
        except Exception as e:
            logger.error(f"Ошибка создания BeautifulSoup для {url}: {e}")
            return {
                'url': url,
                'error': f"Ошибка парсинга HTML: {e}",
                'title': '',
                'description': '',
                'keywords': '',
                'text': '',
                'links': [],
                'images': [],
                'headings': {'h1': [], 'h2': [], 'h3': []},
                'tables': [],
                'lists': {'ul': [], 'ol': []}
            }

        try:
            metadata = self.extract_metadata(soup)
        except Exception as e:
            logger.warning(f"Ошибка извлечения метаданных для {url}: {e}")
            metadata = {'title': '', 'description': '', 'keywords': ''}

        try:
            links = self.extract_links(soup, url, filter_external, allowed_domains)
        except Exception as e:
            logger.warning(f"Ошибка извлечения ссылок для {url}: {e}")
            links = []

        try:
            text = self.extract_text(soup)
        except Exception as e:
            logger.warning(f"Ошибка извлечения текста для {url}: {e}")
            text = ''

        try:
            images = self.extract_images(soup)
        except Exception as e:
            logger.warning(f"Ошибка извлечения изображений для {url}: {e}")
            images = []

        try:
            headings = self.extract_headings(soup)
        except Exception as e:
            logger.warning(f"Ошибка извлечения заголовков для {url}: {e}")
            headings = {'h1': [], 'h2': [], 'h3': []}

        try:
            tables = self.extract_tables(soup)
        except Exception as e:
            logger.warning(f"Ошибка извлечения таблиц для {url}: {e}")
            tables = []

        try:
            lists = self.extract_lists(soup)
        except Exception as e:
            logger.warning(f"Ошибка извлечения списков для {url}: {e}")
            lists = {'ul': [], 'ol': []}

        result = {
            'url': url,
            'title': metadata['title'],
            'description': metadata['description'],
            'keywords': metadata['keywords'],
            'text': text,
            'links': links,
            'images': images,
            'headings': headings,
            'tables': tables,
            'lists': lists
        }

        return result