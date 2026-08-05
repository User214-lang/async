import pytest
import asyncio
from queue_manager import CrawlerQueue

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
    #дубликат
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