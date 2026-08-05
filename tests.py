import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock, MagicMock
from bs4 import BeautifulSoup
from crawler import AsyncCrawler
from queue_manager import CrawlerQueue
from parser import HTMLParser
from exceptions import NetworkError

class TestDay1Crawler:

    @pytest.mark.asyncio
    async def test_fetch_valid_url(self):
        async with AsyncCrawler(max_concurrent=2) as crawler:
            html = await crawler.fetch_url("https://example.com")
            assert isinstance(html, str)
            assert len(html) > 0
            assert "Example Domain" in html

    @pytest.mark.asyncio
    async def test_fetch_invalid_url(self):
        async with AsyncCrawler(max_concurrent=2) as crawler:
            results = await crawler.fetch_urls([
                "https://non-existent-domain-12345.com"
            ])
            assert "ERROR:" in results["https://non-existent-domain-12345.com"]

    @pytest.mark.asyncio
    async def test_timeout(self):
        crawler = AsyncCrawler(
            max_concurrent=2,
            timeout_total=1,
            timeout_connect=1,
            timeout_read=1
        )
        async with crawler:
            with pytest.raises(NetworkError):
                await crawler.fetch_url("http://192.0.2.0/")

    @pytest.mark.asyncio
    async def test_crawler_respects_crawl_delay(self):
        crawler = AsyncCrawler(max_concurrent=1, requests_per_second=100)

        async def fake_wait(domain, ua):
            await asyncio.sleep(0.5)
        crawler.robots_parser.wait_for_crawl_delay = fake_wait
        crawler.robots_parser.is_allowed = lambda url, ua: True
        crawler.robots_parser.ensure_robots_fetched = AsyncMock()

        crawler._semaphore.acquire = AsyncMock()
        crawler._semaphore.release = MagicMock()
        crawler.rate_limiter.acquire = AsyncMock()
        crawler.rate_limiter.record_success = MagicMock()
        crawler.rate_limiter.record_failure = MagicMock()
        crawler.circuit_breaker.is_allowed = MagicMock(return_value=True)
        crawler.circuit_breaker.record_success = MagicMock()
        crawler.circuit_breaker.record_failure = MagicMock()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = AsyncMock(return_value="<html>mock</html>")
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'text/html'}

        class AsyncCM:
            async def __aenter__(self):
                return mock_response
            async def __aexit__(self, *args):
                pass

        crawler._session.get = MagicMock(return_value=AsyncCM())

        start = time.monotonic()
        await crawler.fetch_url("https://example.com")
        elapsed = time.monotonic() - start

        assert elapsed >= 0.45
        assert elapsed < 0.7
        await crawler.close()

class TestDay2Parser:

    @pytest.fixture
    def parser(self):
        return HTMLParser()

    @pytest.mark.asyncio
    async def test_parse_valid_html(self, parser):
        html = """
        <html>
            <head>
                <title>Test Page</title>
                <meta name="description" content="Test description">
                <meta name="keywords" content="test, parser">
            </head>
            <body>
                <h1>Main Header</h1>
                <h2>Sub Header</h2>
                <p>Some text here.</p>
                <a href="/page1">Link 1</a>
                <a href="https://external.com">External</a>
                <img src="image.png" alt="image">
                <ul>
                    <li>Item 1</li>
                    <li>Item 2</li>
                </ul>
                <table>
                    <tr><td>Cell 1</td><td>Cell 2</td></tr>
                </table>
            </body>
        </html>
        """
        url = "https://example.com"
        result = await parser.parse_html(html, url)

        assert result['url'] == url
        assert result['title'] == "Test Page"
        assert result['description'] == "Test description"
        assert result['keywords'] == "test, parser"
        assert "Some text here" in result['text']
        assert len(result['links']) == 2
        assert "https://example.com/page1" in result['links']
        assert "https://external.com" in result['links']
        assert len(result['images']) == 1
        assert result['images'][0]['src'] == "image.png"
        assert result['images'][0]['alt'] == "image"
        assert result['headings']['h1'] == ["Main Header"]
        assert result['headings']['h2'] == ["Sub Header"]
        assert len(result['tables']) == 1
        assert result['tables'][0][0] == ["Cell 1", "Cell 2"]
        assert result['lists']['ul'] == ["Item 1", "Item 2"]

    @pytest.mark.asyncio
    async def test_parse_broken_html(self, parser):
        broken_html = "<html><body><h1>Unclosed tag</p>"
        url = "https://example.com"
        result = await parser.parse_html(broken_html, url)

        assert result['url'] == url
        assert 'title' in result
        assert 'text' in result
        assert 'error' not in result or result['error'] == ''

    def test_extract_links(self, parser):
        html = """
        <html>
            <body>
                <a href="/relative">Relative</a>
                <a href="https://absolute.com">Absolute</a>
                <a href="#anchor">Anchor</a>
                <a href="javascript:void(0)">JS</a>
                <a href="http://example.com">HTTP</a>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, 'lxml')
        base_url = "https://base.com"
        links = parser.extract_links(soup, base_url, filter_external=False)

        assert "https://base.com/relative" in links
        assert "https://absolute.com" in links
        assert "http://example.com" in links

    def test_convert_relative_urls(self, parser):
        html = """
        <html>
            <body>
                <a href="/path/to/page">Page</a>
                <a href="page2">Page2</a>
                <a href="../up">Up</a>
                <a href="//example.com">Protocol-relative</a>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, 'lxml')
        base_url = "https://site.com/dir/subdir/"
        links = parser.extract_links(soup, base_url, filter_external=False)

        assert "https://site.com/path/to/page" in links
        assert "https://site.com/dir/subdir/page2" in links
        assert "https://site.com/dir/up" in links
        assert "https://example.com" in links

class TestDay3QueueAndCrawling:

    @pytest.mark.asyncio
    async def test_queue_priorities(self):
        queue = CrawlerQueue()
        await queue.add_url("http://example.com", priority=1)
        await queue.add_url("http://example.org", priority=0)
        url, depth = await queue.get_next()
        assert url == "http://example.org"
        assert depth == 0
        url2, _ = await queue.get_next()
        assert url2 == "http://example.com"

    @pytest.mark.asyncio
    async def test_queue_no_duplicates(self):
        queue = CrawlerQueue()
        await queue.add_url("http://example.com")
        await queue.add_url("http://example.com")
        assert queue.size == 1
        await queue.get_next()
        queue.mark_processed("http://example.com")
        await queue.add_url("http://example.com")
        assert queue.size == 0
        assert queue.is_empty
        stats = queue.get_stats()
        assert stats['visited'] == 1
        assert stats['total_added'] == 1

    @pytest.mark.asyncio
    async def test_crawl_depth_limit(self):
        mock_html = """
        <html>
            <body>
                <a href="/page1">Page1</a>
                <a href="/page2">Page2</a>
            </body>
        </html>
        """
        async def fake_fetch(url):
            return mock_html

        with patch.object(AsyncCrawler, 'fetch_url', new=fake_fetch):
            crawler = AsyncCrawler(max_concurrent=2)
            try:
                results = await crawler.crawl(
                    start_urls=["http://test.com"],
                    max_pages=10,
                    max_depth=1,
                    same_domain_only=False
                )
                assert results
                assert crawler.queue.is_empty
            finally:
                await crawler.close()

    @pytest.mark.asyncio
    async def test_crawl_same_domain_only(self):
        mock_html = """
        <html>
            <body>
                <a href="/internal">Internal</a>
                <a href="https://external.com">External</a>
            </body>
        </html>
        """
        async def fake_fetch(url):
            return mock_html

        with patch.object(AsyncCrawler, 'fetch_url', new=fake_fetch):
            crawler = AsyncCrawler(max_concurrent=2)
        try:
            results = await crawler.crawl(
                start_urls=["http://test.com"],
                max_pages=10,
                max_depth=2,
                same_domain_only=True
            )
            assert "https://external.com" not in results
        finally:
            await crawler.close()

    @pytest.mark.asyncio
    async def test_crawl_exclude_patterns(self):
        mock_html = """
        <html>
            <body>
                <a href="/page1">Page1</a>
                <a href="/page2">Page2</a>
            </body>
        </html>
        """
        async def fake_fetch(url):
            return mock_html

        with patch.object(AsyncCrawler, 'fetch_url', new=fake_fetch):
            crawler = AsyncCrawler(max_concurrent=2)
        try:
            results = await crawler.crawl(
                start_urls=["http://test.com"],
                max_pages=10,
                max_depth=2,
                same_domain_only=False,
                exclude_patterns=["page2"]
            )
            for url in results:
                assert "page2" not in url
        finally:
            await crawler.close()

    @pytest.mark.asyncio
    async def test_crawl_include_patterns(self):
        mock_html = """
        <html>
            <body>
                <a href="/page1">Page1</a>
                <a href="/page2">Page2</a>
            </body>
        </html>
        """
        async def fake_fetch(url):
            return mock_html

        with patch.object(AsyncCrawler, 'fetch_url', new=fake_fetch):
            crawler = AsyncCrawler(max_concurrent=2)
        try:
            results = await crawler.crawl(
                start_urls=["http://test.com"],
                max_pages=10,
                max_depth=2,
                same_domain_only=False,
                include_patterns=["page1"]
            )
            for url in results:
                if "http://test.com/page2" in url:
                    assert False, "page2 не должен быть включён"
        finally:
            await crawler.close()


class TestDay4Advanced:

    @pytest.mark.asyncio
    async def test_rate_limiting_single_domain(self):
        from rate_limiter import RateLimiter
        limiter = RateLimiter(requests_per_second=10.0, per_domain=True, min_delay=0.1, jitter=0.0)
        domain = "example.com"
        n_requests = 20
        start = time.monotonic()
        for _ in range(n_requests):
            await limiter.acquire(domain)
        elapsed = time.monotonic() - start
        expected_min = (n_requests - 1) * 0.1 * 0.9
        assert elapsed >= expected_min

    @pytest.mark.asyncio
    async def test_rate_limiting_different_domains(self):
        from rate_limiter import RateLimiter
        limiter = RateLimiter(requests_per_second=10.0, per_domain=True, min_delay=0.2, jitter=0.0)
        domain1 = "a.com"
        domain2 = "b.com"
        n_requests = 10
        start = time.monotonic()
        for _ in range(n_requests):
            await limiter.acquire(domain1)
        for _ in range(n_requests):
            await limiter.acquire(domain2)
        elapsed = time.monotonic() - start
        expected_min = 2 * (n_requests - 1) * 0.2 * 0.8
        assert elapsed >= expected_min

    @pytest.mark.asyncio
    async def test_robots_parser_fetch(self):
        from robots_parser import RobotsParser
        parser = RobotsParser()
        try:
            info = await parser.fetch_robots("https://httpbin.org")
            assert 'crawl_delay' in info
            assert info['crawl_delay'] == 1.0
        except Exception:
            pytest.skip("Сетевой запрос не удался")

    def test_robots_parser_can_fetch(self):
        from robots_parser import RobotsParser
        from urllib.robotparser import RobotFileParser

        parser = RobotsParser()
        mock_parser = RobotFileParser()
        mock_parser.parse(["User-agent: *", "Disallow: /deny"])
        parser._cache[('example.com', '*')] = mock_parser

        assert parser.is_allowed("https://example.com/", "*") is True
        assert parser.is_allowed("https://example.com/deny", "*") is False

    @pytest.mark.asyncio
    async def test_crawler_blocks_disallowed_url(self):
        crawler = AsyncCrawler(max_concurrent=1, requests_per_second=100)
        crawler.robots_parser.is_allowed = lambda url, ua: False
        with pytest.raises(PermissionError) as excinfo:
            await crawler.fetch_url("https://example.com")
        assert "запрещён robots.txt" in str(excinfo.value)
        assert crawler.blocked_by_robots == 1
        await crawler.close()

    @pytest.mark.asyncio
    async def test_crawler_respects_crawl_delay(self):
        crawler = AsyncCrawler(max_concurrent=1, requests_per_second=100)

        async def fake_wait(domain, ua):
            await asyncio.sleep(0.5)
        crawler.robots_parser.wait_for_crawl_delay = fake_wait
        crawler.robots_parser.is_allowed = lambda url, ua: True
        crawler.robots_parser.ensure_robots_fetched = AsyncMock()

        crawler._semaphore.acquire = AsyncMock()
        crawler._semaphore.release = MagicMock()
        crawler.rate_limiter.acquire = AsyncMock()
        crawler.rate_limiter.record_success = MagicMock()
        crawler.rate_limiter.record_failure = MagicMock()
        crawler.circuit_breaker.is_allowed = MagicMock(return_value=True)
        crawler.circuit_breaker.record_success = MagicMock()
        crawler.circuit_breaker.record_failure = MagicMock()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = AsyncMock(return_value="<html>mock</html>")
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'text/html'}

        class AsyncCM:
            async def __aenter__(self):
                return mock_response
            async def __aexit__(self, *args):
                pass

        crawler._session.get = MagicMock(return_value=AsyncCM())

        start = time.monotonic()
        await crawler.fetch_url("https://example.com")
        elapsed = time.monotonic() - start

        assert elapsed >= 0.45
        assert elapsed < 0.7
        await crawler.close()

class TestDay5Retry:

    @pytest.mark.asyncio
    async def test_retry_strategy_timeout_retries(self):
        
        from retry_strategy import RetryStrategy
        from exceptions import NetworkError

        mock_func = AsyncMock()
        mock_func.side_effect = [
            NetworkError("Timeout 1"),
            NetworkError("Timeout 2"),
            "success"
        ]

        strategy = RetryStrategy(max_retries=3, backoff_factor=2.0)

        with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
            result = await strategy.execute_with_retry(mock_func)

        assert result == "success"
        assert mock_func.call_count == 3
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [2.0, 4.0]

        stats = strategy.get_retry_stats()
        assert stats['successful_retries'] == 1
        assert stats['total_attempts'] == 3

    @pytest.mark.asyncio
    async def test_retry_strategy_503_retries(self):
        from retry_strategy import RetryStrategy
        from exceptions import TransientError
        mock_func = AsyncMock()
        mock_func.side_effect = [
            TransientError("503 Service Unavailable"),
            TransientError("503 Service Unavailable"),
            "success"
        ]

        strategy = RetryStrategy(max_retries=3, backoff_factor=2.0)
        with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
            result = await strategy.execute_with_retry(mock_func)

        assert result == "success"
        assert mock_func.call_count == 3
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [2.0, 4.0]

        stats = strategy.get_retry_stats()
        assert stats['successful_retries'] == 1

    @pytest.mark.asyncio
    async def test_retry_strategy_404_no_retry(self):
        """Проверка, что PermanentError (404) не повторяется."""
        from retry_strategy import RetryStrategy
        from exceptions import PermanentError

        mock_func = AsyncMock()
        mock_func.side_effect = PermanentError("404 Not Found")

        strategy = RetryStrategy(max_retries=3, backoff_factor=2.0)
        with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
            with pytest.raises(PermanentError):
                await strategy.execute_with_retry(mock_func)

        assert mock_func.call_count == 1
        mock_sleep.assert_not_called()

        stats = strategy.get_retry_stats()
        assert stats['successful_retries'] == 0
        assert stats['total_attempts'] == 1

    @pytest.mark.asyncio
    async def test_retry_strategy_exponential_backoff(self):
        from retry_strategy import RetryStrategy
        from exceptions import NetworkError

        mock_func = AsyncMock()
        mock_func.side_effect = [
            NetworkError("Fail 1"),
            NetworkError("Fail 2"),
            NetworkError("Fail 3"),
            "success"
        ]

        strategy = RetryStrategy(max_retries=4, backoff_factor=2.0)
        with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
            await strategy.execute_with_retry(mock_func)

        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [2.0, 4.0, 8.0]

    @pytest.mark.asyncio
    async def test_crawler_error_classification_and_stats(self):
        from exceptions import NetworkError, TransientError, PermanentError

        crawler = AsyncCrawler(max_concurrent=1, requests_per_second=100)
        async def mock_fetch_internal(url, user_agent):
            if "timeout" in url:
                raise NetworkError("Timeout")
            elif "503" in url:
                raise TransientError("503 Service Unavailable")
            elif "404" in url:
                raise PermanentError("404 Not Found")
            else:
                return "<html>ok</html>", 200, "text/html"

        crawler._fetch_internal = mock_fetch_internal
        crawler.robots_parser.is_allowed = lambda url, ua: True
        crawler.robots_parser.ensure_robots_fetched = AsyncMock()
        crawler.robots_parser.wait_for_crawl_delay = AsyncMock()

        with patch('asyncio.sleep', new=AsyncMock()):
            with pytest.raises(NetworkError):
                await crawler.fetch_url("http://timeout.com")

            #URL с 503 (TransientError) – будет повторяться
            with pytest.raises(TransientError):
                await crawler.fetch_url("http://503.com")

            #URL с 404 (PermanentError) – не будет повторяться
            with pytest.raises(PermanentError):
                await crawler.fetch_url("http://404.com")

            #Успешный URL
            result = await crawler.fetch_url("http://success.com")
            assert result == "<html>ok</html>"

        assert crawler.error_stats.get('NetworkError') == 1
        assert crawler.error_stats.get('TransientError') == 1
        assert crawler.error_stats.get('PermanentError') == 1
        assert crawler.permanent_error_urls == {"http://404.com"}

        assert crawler.total_requests == 1

        assert len(crawler.failed_urls) == 3

        await crawler.close()

    @pytest.mark.asyncio
    async def test_crawler_retry_stats(self):
        #Проверка, что retry_statsсобирается корректно
        from exceptions import NetworkError

        crawler = AsyncCrawler(max_concurrent=1, requests_per_second=100, retry_max_attempts=3)
        crawler.robots_parser.is_allowed = lambda url, ua: True
        crawler.robots_parser.ensure_robots_fetched = AsyncMock()
        crawler.robots_parser.wait_for_crawl_delay = AsyncMock()

        call_count = 0
        async def mock_fetch_internal(url, user_agent):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise NetworkError("Timeout")
            return "<html>ok</html>", 200, "text/html"

        crawler._fetch_internal = mock_fetch_internal
        crawler.rate_limiter.acquire = AsyncMock()
        crawler._semaphore.acquire = AsyncMock()
        crawler._semaphore.release = MagicMock()

        with patch('asyncio.sleep', new=AsyncMock()):
            result = await crawler.fetch_url("http://test.com")
            assert result == "<html>ok</html>"
            assert call_count == 3

            retry_stats = crawler.retry_strategy.get_retry_stats()
            assert retry_stats['successful_retries'] == 1
            assert retry_stats['total_attempts'] == 3

            assert crawler.error_stats.get('NetworkError') is None

        await crawler.close()

class TestDay6Storage:

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    @pytest.mark.asyncio
    async def test_json_storage(self, temp_dir):
        from storage import JsonStorage
        filepath = temp_dir / "test.jsonl"
        storage = JsonStorage(str(filepath), buffer_size=2, indent=None)

        data1 = {"url": "https://example.com", "title": "Example", "status_code": 200}
        data2 = {"url": "https://httpbin.org", "title": "HTTPBin", "status_code": 200}

        await storage.save(data1)
        await storage.save(data2)
        await storage.close()

        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 2
            import json
            saved1 = json.loads(lines[0])
            saved2 = json.loads(lines[1])
            assert saved1["url"] == data1["url"]
            assert saved2["url"] == data2["url"]
            assert "crawled_at" in saved1

    @pytest.mark.asyncio
    async def test_csv_storage(self, temp_dir):
        from storage import CsvStorage
        filepath = temp_dir / "test.csv"
        storage = CsvStorage(str(filepath), buffer_size=2)

        data1 = {"url": "https://example.com", "title": "Example", "status_code": 200}
        data2 = {"url": "https://httpbin.org", "title": "HTTPBin", "status_code": 200}

        await storage.save(data1)
        await storage.save(data2)
        await storage.close()

        #CSV
        import csv
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
            assert rows[0]["url"] == data1["url"]
            assert rows[1]["url"] == data2["url"]

    @pytest.mark.asyncio
    async def test_sqlite_storage(self, temp_dir):
        from storage import SqliteStorage
        db_path = temp_dir / "test.db"
        storage = SqliteStorage(str(db_path), batch_size=2)

        data1 = {"url": "https://example.com", "title": "Example", "status_code": 200}
        data2 = {"url": "https://httpbin.org", "title": "HTTPBin", "status_code": 200}

        await storage.save(data1)
        await storage.save(data2)
        await storage.close()

        import aiosqlite
        async with aiosqlite.connect(str(db_path)) as conn:
            cursor = await conn.execute("SELECT url, title, status_code FROM crawled_data ORDER BY id")
            rows = await cursor.fetchall()
            assert len(rows) == 2
            assert rows[0][0] == data1["url"]
            assert rows[1][0] == data2["url"]

    @pytest.mark.asyncio
    async def test_storage_retry_on_error(self):
        from unittest.mock import AsyncMock, patch
        from crawler import AsyncCrawler
        from storage import DataStorage

        mock_storage = AsyncMock(spec=DataStorage)
        mock_storage.save = AsyncMock(side_effect=[
            Exception("Write error 1"),
            Exception("Write error 2"),
            None
        ])
        mock_storage.close = AsyncMock()

        crawler = AsyncCrawler(max_concurrent=1, storage=mock_storage)
        crawler.save_retry_attempts = 3
        crawler.save_retry_delay = 0.01

        with patch('asyncio.sleep', new=AsyncMock()):
            await crawler._save_data(
                url="https://test.com",
                html="<html>test</html>",
                parsed={"title": "Test", "text": "content", "links": [], "metadata": {}, "images": [], "headings": {}},
                status=200,
                content_type="text/html"
            )

        assert mock_storage.save.call_count == 3
        await crawler.close()

    @pytest.mark.asyncio
    async def test_data_integrity(self):
        from crawler import AsyncCrawler
        from storage import JsonStorage
        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as tmp:
            tmp_path = tmp.name

        storage = JsonStorage(tmp_path, buffer_size=1, indent=None)
        crawler = AsyncCrawler(max_concurrent=1, storage=storage)

        test_url = "https://example.com"
        test_html = "<html><title>Example Domain</title></html>"
        test_parsed = {
            "title": "Example Domain",
            "text": "This domain is for use in illustrative examples",
            "links": ["https://www.iana.org/domains/example"],
            "metadata": {"description": "Example Domain"},
            "images": [],
            "headings": {"h1": ["Example Domain"]}
        }
        test_status = 200
        test_content_type = "text/html"

        await crawler._save_data(test_url, test_html, test_parsed, test_status, test_content_type)
        await storage.close()

        with open(tmp_path, "r", encoding="utf-8") as f:
            saved = json.loads(f.readline())

        assert saved["url"] == test_url
        assert saved["title"] == test_parsed["title"]
        assert saved["text"] == test_parsed["text"]
        assert saved["links"] == test_parsed["links"]
        assert saved["metadata"] == test_parsed["metadata"]
        assert saved["status_code"] == test_status
        assert saved["content_type"] == test_content_type
        assert "crawled_at" in saved
        assert saved["error"] == ""

        await crawler.close()

        import os
        os.unlink(tmp_path)


class TestDay7Advanced:

    @pytest.fixture
    def sample_sitemap_xml(self):
        return """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/page1</loc></url>
            <url><loc>https://example.com/page2</loc></url>
        </urlset>
        """

    @pytest.fixture
    def sample_sitemap_index_xml(self):
        return """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/sitemap1.xml</loc></sitemap>
            <sitemap><loc>https://example.com/sitemap2.xml</loc></sitemap>
        </sitemapindex>
        """

    @pytest.mark.asyncio
    async def test_sitemap_parser_fetch(self, sample_sitemap_xml):
        from sitemap_parser import SitemapParser
        from unittest.mock import AsyncMock

        parser = SitemapParser()
        parser._fetch_xml = AsyncMock(return_value=sample_sitemap_xml)
        urls = await parser.fetch_sitemap("https://example.com/sitemap.xml")
        assert len(urls) == 2
        assert "https://example.com/page1" in urls
        assert "https://example.com/page2" in urls

    @pytest.mark.asyncio
    async def test_sitemap_parser_index(self, sample_sitemap_index_xml, sample_sitemap_xml):
        from sitemap_parser import SitemapParser

        parser = SitemapParser()
        async def mock_fetch(url):
            if url == "https://example.com/sitemap.xml":
                return sample_sitemap_index_xml
            else:
                return sample_sitemap_xml
        parser._fetch_xml = mock_fetch
        urls = await parser.fetch_sitemap("https://example.com/sitemap.xml")
        assert len(urls) == 4
        assert "https://example.com/page1" in urls
        assert "https://example.com/page2" in urls

    def test_crawler_stats_export(self, tmp_path):
        from crawler_stats import CrawlerStats
        import json

        stats = CrawlerStats()
        stats.record_success("https://example.com", 200, 0.5)
        stats.record_success("https://httpbin.org", 200, 0.3)
        stats.record_failure("https://bad.com", "NetworkError")
        stats.finish()

        json_file = tmp_path / "stats.json"
        stats.export_to_json(str(json_file))
        assert json_file.exists()
        with open(json_file) as f:
            data = json.load(f)
            assert data['total_processed'] == 3
            assert data['successful_requests'] == 2
            assert data['failed_requests'] == 1

        html_file = tmp_path / "report.html"
        stats.export_to_html_report(str(html_file))
        assert html_file.exists()
        content = html_file.read_text()
        assert "Отчёт краулера" in content
        assert "Детальная статистика" in content

    @pytest.mark.asyncio
    async def test_config_loader(self):
        from config_loader import ConfigLoader
        from storage import JsonStorage
        import tempfile
        import yaml
        import os

        config = {
            'max_concurrent': 5,
            'requests_per_second': 2.0,
            'start_urls': ['https://example.com'],
            'storage': {'type': 'json', 'path': 'test.jsonl'}
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_path = f.name

        loaded = ConfigLoader.load_config(config_path)
        assert loaded['max_concurrent'] == 5
        assert loaded['start_urls'] == ['https://example.com']

        crawler = ConfigLoader.create_crawler_from_config(loaded)
        assert crawler.max_concurrent == 5
        assert crawler.requests_per_second == 2.0
        assert isinstance(crawler.storage, JsonStorage)

        await crawler.close()
        os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_performance_mock(self):
        from crawler import AsyncCrawler
        from unittest.mock import patch, AsyncMock
        import time

        async def mock_fetch_url_with_meta(self, url):
            await asyncio.sleep(0.1)
            return "<html>mock</html>", 200, "text/html"

        with patch.object(AsyncCrawler, 'fetch_url_with_meta', new=mock_fetch_url_with_meta):
            crawler = AsyncCrawler(max_concurrent=5, requests_per_second=100)
            crawler.robots_parser.is_allowed = lambda url, ua: True
            crawler.robots_parser.ensure_robots_fetched = AsyncMock()
            crawler.robots_parser.wait_for_crawl_delay = AsyncMock()

            crawler._semaphore.acquire = AsyncMock()
            crawler._semaphore.release = AsyncMock()

            start = time.monotonic()
            results = await crawler.crawl(
                start_urls = [f"https://test.com/{i}" for i in range(20)],
                max_pages=20,
                max_depth=0,
                same_domain_only=False
            )
            elapsed = time.monotonic() - start

            assert elapsed < 1.0, f"Слишком медленно: {elapsed:.2f} сек"
            assert len(results) == 20
            await crawler.close()

    def test_sync_vs_async(self):
        import requests
        import time
        import asyncio
        from crawler import AsyncCrawler

        urls = ["https://example.com", "https://httpbin.org/get", "https://httpbin.org/status/200"] * 3

        start = time.monotonic()
        for url in urls:
            try:
                requests.get(url, timeout=5)
            except Exception:
                pass
        sync_time = time.monotonic() - start

        async def async_fetch():
            async with AsyncCrawler(max_concurrent=5, requests_per_second=100) as crawler:
                crawler.robots_parser.is_allowed = lambda url, ua: True
                crawler.robots_parser.ensure_robots_fetched = lambda url, ua: None
                await crawler.fetch_urls(urls)

        start = time.monotonic()
        asyncio.run(async_fetch())
        async_time = time.monotonic() - start

        assert async_time < sync_time, f"Асинхронный ({async_time:.2f}) медленнее синхронного ({sync_time:.2f})"

    @pytest.mark.asyncio
    async def test_scalability(self):
        from crawler import AsyncCrawler
        from unittest.mock import patch, AsyncMock
        import time

        n_values = [10, 30, 50]
        times = []
        async def mock_fetch_url_with_meta(self, url):
            await asyncio.sleep(0.05)
            return "<html>mock</html>", 200, "text/html"

        with patch.object(AsyncCrawler, 'fetch_url_with_meta', new=mock_fetch_url_with_meta):
            for n in n_values:
                crawler = AsyncCrawler(max_concurrent=5, requests_per_second=100)
                crawler.robots_parser.is_allowed = lambda url, ua: True
                crawler.robots_parser.ensure_robots_fetched = AsyncMock()
                crawler.robots_parser.wait_for_crawl_delay = AsyncMock()
                crawler._semaphore.acquire = AsyncMock()
                crawler._semaphore.release = AsyncMock()

                start = time.monotonic()
                await crawler.crawl(
                    start_urls=["https://test.com"] * n,
                    max_pages=n,
                    max_depth=0,
                    same_domain_only=False
                )
                elapsed = time.monotonic() - start
                times.append(elapsed)
                await crawler.close()

        assert times[2] < times[0] * 4, f"Масштабируемость плохая: для 10 -> {times[0]:.2f}, для 50 -> {times[2]:.2f}"
        print(f"Время для {n_values[0]} страниц: {times[0]:.2f} сек, для {n_values[-1]} страниц: {times[-1]:.2f} сек")