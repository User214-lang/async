import pytest
import asyncio
import time
from unittest.mock import patch
from crawler import AsyncCrawler
from queue_manager import CrawlerQueue

#Тесты базового краулера

@pytest.mark.asyncio
async def test_fetch_valid_url():
    async with AsyncCrawler(max_concurrent=2) as crawler:
        html = await crawler.fetch_url("https://example.com")
        assert isinstance(html, str)
        assert len(html) > 0
        assert "Example Domain" in html

@pytest.mark.asyncio
async def test_fetch_invalid_url():
    async with AsyncCrawler(max_concurrent=2) as crawler:
        results = await crawler.fetch_urls([
            "https://non-existent-domain-12345.com"
        ])
        assert "ERROR:" in results["https://non-existent-domain-12345.com"]

@pytest.mark.asyncio
async def test_timeout():
    crawler = AsyncCrawler(
        max_concurrent=2,
        timeout_total=1,
        timeout_connect=1,
        timeout_read=1
    )
    async with crawler:
        with pytest.raises(asyncio.TimeoutError):
            await crawler.fetch_url("http://192.0.2.0/")

@pytest.mark.asyncio
async def test_parallel_vs_sequential():
    urls = [
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/1"
    ]
    start_seq = time.time()
    async with AsyncCrawler(max_concurrent=1) as seq_crawler:
        await seq_crawler.fetch_urls(urls)
    elapsed_seq = time.time() - start_seq

    start_par = time.time()
    async with AsyncCrawler(max_concurrent=3) as par_crawler:
        await par_crawler.fetch_urls(urls)
    elapsed_par = time.time() - start_par

    assert elapsed_par < elapsed_seq
    assert elapsed_seq / elapsed_par > 1

#Тесты для CrawlerQueue

@pytest.mark.asyncio
async def test_queue_add_and_get():
    queue = CrawlerQueue()
    await queue.add_url("http://example.com", priority=1)
    await queue.add_url("http://example.org", priority=0)
    url, depth = await queue.get_next()
    assert url == "http://example.org"
    assert depth == 0
    url2, _ = await queue.get_next()
    assert url2 == "http://example.com"

@pytest.mark.asyncio
async def test_queue_no_duplicates():
    queue = CrawlerQueue()
    await queue.add_url("http://example.com")
    await queue.add_url("http://example.com")
    assert queue.size == 1
    await queue.get_next()
    queue.mark_processed("http://example.com")
    await queue.add_url("http://example.com")
    assert queue.size == 0
    assert queue.is_empty

@pytest.mark.asyncio
async def test_queue_mark_failed():
    queue = CrawlerQueue()
    await queue.add_url("http://example.com")
    url, _ = await queue.get_next()
    queue.mark_failed(url, "error")
    stats = queue.get_stats()
    assert stats['total_failed'] == 1
    assert stats['failed_count'] == 1
    assert queue.is_visited("http://example.com")

@pytest.mark.asyncio
async def test_queue_stats():
    queue = CrawlerQueue()
    await queue.add_url("http://a.com")
    await queue.add_url("http://b.com")
    await queue.get_next()
    stats = queue.get_stats()
    assert stats['total_added'] == 2
    assert stats['pending'] == 1

#Тесты расширенного краулера

@pytest.fixture
def mock_html_with_links():
    return """
    <html>
        <body>
            <a href="/page1">Page1</a>
            <a href="https://external.com">External</a>
            <a href="/page2">Page2</a>
        </body>
    </html>
    """

@pytest.mark.asyncio
async def test_crawl_depth_limit(mock_html_with_links):
    async def fake_fetch(url):
        return mock_html_with_links

    with patch.object(AsyncCrawler, 'fetch_url', new=fake_fetch):
        crawler = AsyncCrawler(max_concurrent=2)
        results = await crawler.crawl(
            start_urls=["http://test.com"],
            max_pages=10,
            max_depth=1,
            same_domain_only=False
        )
        assert results
        assert crawler.queue.is_empty

@pytest.mark.asyncio
async def test_crawl_same_domain_only(mock_html_with_links):
    async def fake_fetch(url):
        return mock_html_with_links

    with patch.object(AsyncCrawler, 'fetch_url', new=fake_fetch):
        crawler = AsyncCrawler(max_concurrent=2)
        results = await crawler.crawl(
            start_urls=["http://test.com"],
            max_pages=10,
            max_depth=2,
            same_domain_only=True
        )
        assert "https://external.com" not in results

@pytest.mark.asyncio
async def test_crawl_exclude_patterns(mock_html_with_links):
    async def fake_fetch(url):
        return mock_html_with_links

    with patch.object(AsyncCrawler, 'fetch_url', new=fake_fetch):
        crawler = AsyncCrawler(max_concurrent=2)
        results = await crawler.crawl(
            start_urls=["http://test.com"],
            max_pages=10,
            max_depth=2,
            same_domain_only=False,
            exclude_patterns=["page2"]
        )
        for url in results:
            assert "page2" not in url

@pytest.mark.asyncio
async def test_crawl_include_patterns(mock_html_with_links):
    async def fake_fetch(url):
        return mock_html_with_links

    with patch.object(AsyncCrawler, 'fetch_url', new=fake_fetch):
        crawler = AsyncCrawler(max_concurrent=2)
        results = await crawler.crawl(
            start_urls=["http://test.com"],
            max_pages=10,
            max_depth=2,
            same_domain_only=False,
            include_patterns=["page1"]
        )
        for url in results:
            if "http://test.com/page2" in url:
                assert False, "page2 должен быть исключён"

@pytest.mark.asyncio
async def test_no_duplicates_visited():
    queue = CrawlerQueue()
    await queue.add_url("http://test.com")
    await queue.add_url("http://test.com")
    assert queue.size == 1
    url, _ = await queue.get_next()
    queue.mark_processed(url)
    await queue.add_url("http://test.com")
    assert queue.size == 0
    stats = queue.get_stats()
    assert stats['visited'] == 1
    assert stats['total_added'] == 1