import json
import csv
import logging
import aiofiles
import aiosqlite
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import asyncio
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class DataStorage(ABC):

    @abstractmethod
    async def save(self, data: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass


class JsonStorage(DataStorage):

    def __init__(
        self,
        filepath: str,
        mode: str = 'a',
        indent: int = None,
        encoding: str = 'utf-8',
        buffer_size: int = 10
    ):
        self.filepath = filepath
        self.mode = mode
        self.indent = indent
        self.encoding = encoding
        self.buffer_size = buffer_size
        self._lock = asyncio.Lock()
        self._buffer: List[str] = []

    async def save(self, data: Dict[str, Any]) -> None:
        if 'crawled_at' not in data:
            data['crawled_at'] = datetime.now().isoformat()
        line = json.dumps(data, ensure_ascii=False, indent=self.indent) + '\n'
        async with self._lock:
            self._buffer.append(line)
            if len(self._buffer) >= self.buffer_size:
                await self._flush()

    async def _flush(self) -> None:
        if not self._buffer:
            return
        async with aiofiles.open(self.filepath, self.mode, encoding=self.encoding) as f:
            await f.writelines(self._buffer)
        self._buffer.clear()

    async def close(self) -> None:
        if self._buffer:
            await self._flush()


class CsvStorage(DataStorage):

    def __init__(
        self,
        filepath: str,
        fieldnames: Optional[List[str]] = None,
        encoding: str = 'utf-8',
        buffer_size: int = 10
    ):
        self.filepath = filepath
        self.encoding = encoding
        self.buffer_size = buffer_size
        self._lock = asyncio.Lock()
        self._buffer: List[Dict[str, Any]] = []
        self._is_initialized = False
        self.fieldnames = fieldnames or [
            'url', 'title', 'text', 'links', 'metadata',
            'crawled_at', 'status_code', 'content_type',
            'text_length', 'images_count', 'headings', 'error'
        ]

    async def save(self, data: Dict[str, Any]) -> None:
        async with self._lock:
            self._buffer.append(data)
            if len(self._buffer) >= self.buffer_size:
                await self._flush()

    def _write_csv_sync(self):
        #Синхронная запись CSV, вызывается из отдельного потока
        with open(self.filepath, 'a', newline='', encoding=self.encoding) as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            if not self._is_initialized:
                if not os.path.exists(self.filepath) or os.path.getsize(self.filepath) == 0:
                    writer.writeheader()
                self._is_initialized = True
            rows = []
            for data in self._buffer:
                row = {}
                for k in self.fieldnames:
                    val = data.get(k, '')
                    if k == 'links' and isinstance(val, list):
                        val = json.dumps(val, ensure_ascii=False)
                    elif k == 'metadata' and isinstance(val, dict):
                        val = json.dumps(val, ensure_ascii=False)
                    elif k == 'headings' and isinstance(val, dict):
                        val = json.dumps(val, ensure_ascii=False)
                    row[k] = val
                rows.append(row)
            writer.writerows(rows)

    async def _flush(self) -> None:
        if not self._buffer:
            return
        await asyncio.to_thread(self._write_csv_sync)
        self._buffer.clear()

    async def close(self) -> None:
        if self._buffer:
            await self._flush()


class SqliteStorage(DataStorage):

    def __init__(
        self,
        db_path: str,
        table_name: str = 'crawled_data',
        batch_size: int = 100
    ):
        self.db_path = db_path
        self.table_name = table_name
        self.batch_size = batch_size
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
        self._buffer: List[Dict[str, Any]] = []

    async def _ensure_connection(self) -> None:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            await self._conn.execute(f'''
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    title TEXT,
                    text TEXT,
                    text_length INTEGER,
                    links TEXT,
                    images TEXT,
                    headings TEXT,
                    metadata TEXT,
                    error TEXT,
                    crawled_at TEXT,
                    status_code INTEGER,
                    content_type TEXT,
                    saved_at REAL
                )
            ''')
            await self._conn.execute(f'''
                CREATE INDEX IF NOT EXISTS idx_url ON {self.table_name}(url)
            ''')
            await self._conn.commit()

    async def _flush(self) -> None:
        if not self._buffer:
            return
        sql = f'''
            INSERT INTO {self.table_name}
            (url, title, text, text_length, links, images, headings, metadata,
             error, crawled_at, status_code, content_type, saved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        rows = []
        for data in self._buffer:
            rows.append((
                data.get('url', ''),
                data.get('title', ''),
                data.get('text', ''),
                data.get('text_length', 0),
                json.dumps(data.get('links', []), ensure_ascii=False),
                json.dumps(data.get('images', []), ensure_ascii=False),
                json.dumps(data.get('headings', {}), ensure_ascii=False),
                json.dumps(data.get('metadata', {}), ensure_ascii=False),
                data.get('error', ''),
                data.get('crawled_at', datetime.now().isoformat()),
                data.get('status_code', 0),
                data.get('content_type', ''),
                data.get('_saved_at', asyncio.get_event_loop().time())
            ))
        await self._conn.executemany(sql, rows)
        await self._conn.commit()
        self._buffer.clear()

    async def save(self, data: Dict[str, Any]) -> None:
        await self._ensure_connection()
        data.setdefault('_saved_at', asyncio.get_event_loop().time())
        data.setdefault('crawled_at', datetime.now().isoformat())
        async with self._lock:
            self._buffer.append(data)
            if len(self._buffer) >= self.batch_size:
                await self._flush()

    async def close(self) -> None:
        if self._buffer:
            async with self._lock:
                await self._flush()
        if self._conn:
            await self._conn.close()
            self._conn = None