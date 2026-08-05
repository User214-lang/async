import os
os.makedirs("results", exist_ok=True)

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import csv
import aiosqlite
from crawler import AsyncCrawler
from storage import JsonStorage, CsvStorage, SqliteStorage, DataStorage
from typing import List


class MultiStorage(DataStorage):

    def __init__(self, storages: List[DataStorage]):
        self.storages = storages

    async def save(self, data: dict) -> None:
        for s in self.storages:
            await s.save(data)

    async def close(self) -> None:
        for s in self.storages:
            await s.close()


async def main():
    
    print("Демонстрация сохранения данных в json, csv, sqlite")
    
    json_storage = JsonStorage("results/results.jsonl", buffer_size=5, indent = None)
    csv_storage = CsvStorage("results/results.csv", buffer_size=5)
    sqlite_storage = SqliteStorage("results/results.db", batch_size=5)
    multi_storage = MultiStorage([json_storage, csv_storage, sqlite_storage])

    crawler = AsyncCrawler(
        max_concurrent=2,
        storage=multi_storage,
        requests_per_second=2.0,
        min_delay=0.2,
        timeout_total=10,
        retry_max_attempts=2
    )

    start_urls = [
        "https://httpbin.org/status/200",
        "https://httpbin.org/status/404",
        "https://example.com"
    ]
    print("\nЗапуск краулинга...")
    await crawler.crawl(start_urls=start_urls, max_pages=3, max_depth=1)
    await crawler.close()
    print("Краулинг завершён, данные сохранены.\n")

    print("\nЧтение данных...")

    print("\nJSON (последние 3 записи)")
    try:
        with open("results.jsonl", "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines[-3:]:
                data = json.loads(line)
                print(f"URL: {data.get('url')}")
                print(f"  Заголовок: {data.get('title', '')}")
                print(f"  Статус: {data.get('status_code')}")
                print()
    except Exception as e:
        print(f"Ошибка чтения JSON: {e}")

    print("\nCSV (последние 3 записи)")
    try:
        with open("results.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            for row in rows[-3:]:
                print(f"URL: {row.get('url')}")
                print(f"  Заголовок: {row.get('title', '')}")
                print(f"  Статус: {row.get('status_code')}")
                print()
    except Exception as e:
        print(f"Ошибка чтения CSV: {e}")

    print("\nSQLite (последние 3 записи)")
    try:
        async with aiosqlite.connect("results.db") as conn:
            cursor = await conn.execute(
                "SELECT url, title, status_code FROM crawled_data ORDER BY id DESC LIMIT 3"
            )
            rows = await cursor.fetchall()
            for row in rows:
                print(f"URL: {row[0]}")
                print(f"  Заголовок: {row[1]}")
                print(f"  Статус: {row[2]}")
                print()
    except Exception as e:
        print(f"Ошибка чтения SQLite: {e}")


if __name__ == "__main__":
    asyncio.run(main())
