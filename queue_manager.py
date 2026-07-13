import asyncio
import time
from typing import Optional, Dict, Set, Tuple
import logging

logger = logging.getLogger(__name__)


class CrawlerQueue:

    def __init__(self):
        self._queue = asyncio.PriorityQueue()
        self._visited: Set[str] = set()
        self._processed: Set[str] = set()
        self._failed: Dict[str, str] = {}
        self._pending: Set[str] = set()
        self._depth_map: Dict[str, int] = {}
        self._total_added = 0
        self._total_processed = 0
        self._total_failed = 0

    async def add_url(self, url: str, priority: int = 0, depth: int = 0) -> None:
        if url in self._visited:
            logger.debug(f"URL уже посещён: {url}")
            return
        if url in self._pending:
            logger.debug(f"URL уже в очереди: {url}")
            return

        timestamp = time.monotonic()
        await self._queue.put((priority, depth, timestamp, url))
        self._pending.add(url)
        self._depth_map[url] = depth
        self._total_added += 1
        logger.debug(f"URL добавлен (глубина {depth}, приоритет {priority}): {url}")

    async def get_next(self) -> Optional[Tuple[str, int]]:
        try:
            priority, depth, timestamp, url = await asyncio.wait_for(
                self._queue.get(), timeout=0.1
            )
            self._pending.discard(url)
            logger.debug(f"Извлечён URL: {url} (глубина {depth}, приоритет {priority})")
            return url, depth
        except asyncio.TimeoutError:
            return None

    def mark_processed(self, url: str) -> None:
        if url not in self._processed:
            self._processed.add(url)
            self._total_processed += 1
            self._visited.add(url)
            logger.debug(f"URL отмечен как обработанный: {url}")

    def mark_failed(self, url: str, error: str) -> None:
        if url not in self._failed:
            self._failed[url] = error
            self._total_failed += 1
            self._visited.add(url)
            logger.warning(f"URL отмечен как неудачный: {url}, ошибка: {error}")

    def is_visited(self, url: str) -> bool:
        return url in self._visited

    def get_stats(self) -> Dict[str, int]:
        return {
            'total_added': self._total_added,
            'total_processed': self._total_processed,
            'total_failed': self._total_failed,
            'pending': self._queue.qsize(),
            'visited': len(self._visited),
            'processed_count': len(self._processed),
            'failed_count': len(self._failed),
        }

    @property
    def is_empty(self) -> bool:
        return self._queue.empty()

    @property
    def size(self) -> int:
        return self._queue.qsize()