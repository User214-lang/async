#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
import argparse
import json
import re
from typing import Dict, Any, Optional, Union, List
from crawler import AsyncCrawler
from config_loader import ConfigLoader
from logging_config import setup_logging
from storage import DataStorage, JsonStorage, CsvStorage, SqliteStorage
from demo.demo_storage import MultiStorage
import logging
import aiohttp

logger = logging.getLogger(__name__)


MODES = {
    'test': {
        'description': 'httpbin',
        'depth': 2,
        'concurrent': 10,
        'requests_per_second': 5.0,
        'min_delay': 0.2,
        'jitter': 0.1,
        'same_domain_only': True,
    },
    'real': {
        'description': 'quotes.toscrape.com, books.toscrape.com)',
        'depth': 4,
        'concurrent': 5,
        'requests_per_second': 3.0,
        'min_delay': 0.3,
        'jitter': 0.15,
        'same_domain_only': True,
    },
    'deep': {
        'description': 'Обход 3000стр',
        'depth': 6,
        'concurrent': 5,
        'requests_per_second': 2.0,
        'min_delay': 0.5,
        'jitter': 0.2,
        'same_domain_only': False,
    },
    'stress': {
        'description': 'Стресс-тест: комбинация обоих',
        'depth': 5,
        'concurrent': 8,
        'requests_per_second': 10.0,
        'min_delay': 0.1,
        'jitter': 0.05,
        'same_domain_only': False,
    },
    'sitemap': {
        'description': 'Загрузка URL из sitemap.xml указанного сайта',
        'depth': 3,
        'concurrent': 5,
        'requests_per_second': 3.0,
        'min_delay': 0.3,
        'jitter': 0.1,
        'same_domain_only': False,
    },
}


def resolve_path(filename: str) -> str:
    out_dir = "results"
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, filename)

def generate_urls(base_url: str, count: int) -> list:
    endpoints = [
        "/status/200", "/status/404", "/status/500", "/status/503",
        "/status/429", "/get", "/delay/1", "/delay/2",
        "/html", "/forms/post", "/bytes/1024",
        "/links/10/0", "/links/5/0", "/links/10/1",
    ]
    urls = []
    for i in range(count):
        endpoint = endpoints[i % len(endpoints)]
        urls.append(f"{base_url}{endpoint}?seq={i}")
    return urls

def get_real_sites_urls() -> List[str]:
    return [
        "https://quotes.toscrape.com",
        "https://quotes.toscrape.com/tag/love/",
        "https://quotes.toscrape.com/tag/inspirational/",
        "https://quotes.toscrape.com/tag/life/",
        "https://quotes.toscrape.com/tag/humor/",
        "https://quotes.toscrape.com/tag/books/",
        "https://books.toscrape.com",
        "https://books.toscrape.com/catalogue/category/books/travel_2/index.html",
        "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html",
        "https://books.toscrape.com/catalogue/category/books/historical-fiction_4/index.html",
        "https://books.toscrape.com/catalogue/category/books/sequential-art_5/index.html",
        "https://books.toscrape.com/catalogue/category/books/classics_6/index.html",
        "https://httpbin.org/html",
        "https://httpbin.org/links/10/0",
    ]

def get_deep_crawl_urls() -> List[str]:
    urls = []
    urls.extend([
        #quotes.toscrape.com - цитаты, теги, авторы
        "https://quotes.toscrape.com",
        "https://quotes.toscrape.com/tag/love/",
        "https://quotes.toscrape.com/tag/inspirational/",
        "https://quotes.toscrape.com/tag/life/",
        "https://quotes.toscrape.com/tag/humor/",
        "https://quotes.toscrape.com/tag/books/",
        "https://quotes.toscrape.com/tag/friendship/",
        "https://quotes.toscrape.com/tag/truth/",
        "https://quotes.toscrape.com/author/Albert-Einstein/",
        "https://quotes.toscrape.com/author/Mark-Twain/",
        # books.toscrape.com - книги в категориях
        "https://books.toscrape.com",
        "https://books.toscrape.com/catalogue/category/books/travel_2/index.html",
        "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html",
        "https://books.toscrape.com/catalogue/category/books/classics_6/index.html",
        "https://books.toscrape.com/catalogue/category/books/romance_8/index.html",
        "https://books.toscrape.com/catalogue/category/books/fiction_10/index.html",
        "https://books.toscrape.com/catalogue/category/books/fantasy_19/index.html",
        "https://books.toscrape.com/catalogue/category/books/science_22/index.html",
    ])

    # 404 без повторов
    for i in range(20):
        urls.append(f"https://httpbin.org/status/404?seq={i}")
    # 500 с экспоненциальным backoff
    for i in range(15):
        urls.append(f"https://httpbin.org/status/500?seq={i}")
    # 503 с повторами
    for i in range(15):
        urls.append(f"https://httpbin.org/status/503?seq={i}")
    # 429 с увеличенным backoff
    for i in range(10):
        urls.append(f"https://httpbin.org/status/429?seq={i}")
    # Таймауты
    for i in range(5):
        urls.append(f"https://httpbin.org/delay/15?seq={i}")
    # Успешные страницы со ссылками
    for i in range(10):
        urls.append(f"https://httpbin.org/links/10/0?seq={i}")
    # Успешные с разной задержкой
    for i in range(10):
        urls.append(f"https://httpbin.org/delay/1?seq={i}")
    for i in range(10):
        urls.append(f"https://httpbin.org/delay/2?seq={i}")

    #Несуществующий домен для DNS-ошибки
    urls.append("https://this-domain-definitely-does-not-exist-12345.com")
    urls.append("https://nonexistent-test-domain-98765.com/page")

    return urls

def get_stress_urls(pages: int) -> List[str]:
    urls = get_real_sites_urls()
    for i in range(min(pages // 2, 500)):
        urls.append(f"https://httpbin.org/links/10/0?seq={i}")
        urls.append(f"https://httpbin.org/links/5/0?seq={i}")
        urls.append(f"https://httpbin.org/links/10/1?seq={i}")
    return urls

async def load_sitemap_urls(sitemap_url: str, max_urls: int = 1000) -> List[str]:
    logger.info(f"Загрузка sitemap из {sitemap_url}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(sitemap_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.error(f"Не удалось загрузить sitemap: {resp.status}")
                    return []
                text = await resp.text()
        urls = re.findall(r'<loc>([^<]+)</loc>', text)
        urls = urls[:max_urls]
        logger.info(f"Загружено {len(urls)} URL из sitemap")
        return urls
    except Exception as e:
        logger.error(f"Ошибка парсинга sitemap: {e}")
        return []

async def main():
    parser = argparse.ArgumentParser(description="Финальная демонстрация краулера")
    parser.add_argument(
    "--mode",
    choices=list(MODES.keys()),
    default='real',
    help="Режим: test (быстрый), real (~500 стр), deep (3000+ стр), stress, sitemap"
    )

    parser.add_argument("--pages", type=int, default=500, help="Количество страниц для загрузки")
    parser.add_argument("--depth", type=int, default=None, help="Глубина обхода (переопределяет значение режима)")
    parser.add_argument("--concurrent", type=int, default=None, help="Конкурентность (переопределяет значение режима)")
    parser.add_argument("--sitemap-url", help="URL файла sitemap.xml (для режима sitemap)")
    parser.add_argument("--urls", nargs="+", help="Стартовые URL (опционально, переопределяет режим)")
    args = parser.parse_args()

    os.makedirs("results", exist_ok=True)

    if args.urls:
        start_urls = args.urls
        mode_name = 'custom'
    elif args.mode == 'test':
        start_urls = generate_urls("https://httpbin.org", args.pages)
        mode_name = 'test'
    elif args.mode == 'real':
        start_urls = get_real_sites_urls()
        mode_name = 'real'
    elif args.mode == 'deep':
        start_urls = get_deep_crawl_urls()
        mode_name = 'deep'
    elif args.mode == 'stress':
        start_urls = get_stress_urls(args.pages)
        mode_name = 'stress'
    elif args.mode == 'sitemap':
        if not args.sitemap_url:
            print("ОШИБКА: Для режима sitemap укажите --sitemap-url")
            return
        start_urls = await load_sitemap_urls(args.sitemap_url, max_urls=args.pages)
        if not start_urls:
            print("ОШИБКА: Не удалось загрузить URL из sitemap")
            return
        mode_name = 'sitemap'
    else:
        start_urls = generate_urls("https://httpbin.org", args.pages)
        mode_name = 'test'

    config_path = "config.yaml"
    if os.path.exists(config_path):
        config = ConfigLoader.load_config(config_path)
    else:
        config = {
            'max_concurrent': 5,
            'requests_per_second': 5.0,
            'min_delay': 0.2,
            'jitter': 0.1,
            'user_agent': 'MyCrawler/3.0',
            'timeout_read': 15,
            'timeout_connect': 8,
            'timeout_total': 30,
            'max_pages': args.pages,
            'max_depth': 3,
            'filters': {'same_domain_only': False},
            'storage': {
                'type': 'sqlite',
                'path': 'results/crawler_results.db',
                'batch_size': 20
            },
            'logging': {
                'level': 'INFO',
                'file': 'results/crawler.log',
                'console': True
            },
            'respect_robots': True,
            'retry_max_attempts': 3,
        }

    if 'storage' in config and config.get('storage') and 'path' in config['storage']:
        config['storage']['path'] = resolve_path(config['storage']['path'].replace('results/', ''))

    if 'logging' in config and config.get('logging') and 'file' in config['logging']:
        config['logging']['file'] = resolve_path(config['logging']['file'].replace('results/', ''))

    json_storage = JsonStorage(resolve_path("results.jsonl"), indent=None, buffer_size=10)
    csv_storage = CsvStorage(resolve_path("results.csv"), buffer_size=10)
    sqlite_storage = SqliteStorage(resolve_path("results.db"), batch_size=20)
    multi_storage = MultiStorage([json_storage, csv_storage, sqlite_storage])

    if mode_name in MODES:
        mode_cfg = MODES[mode_name]
    else:
        mode_cfg = MODES['real']

    crawler_kwargs = {
        'max_concurrent': args.concurrent or mode_cfg['concurrent'],
        'requests_per_second': mode_cfg['requests_per_second'],
        'min_delay': mode_cfg['min_delay'],
        'jitter': mode_cfg['jitter'],
        'user_agent': config.get('user_agent', 'MyCrawler/3.0'),
        'timeout_read': 10 if mode_name == 'deep' else config.get('timeout_read', 15),
        'timeout_connect': config.get('timeout_connect', 8),
        'timeout_total': config.get('timeout_total', 30),
        'respect_robots': config.get('respect_robots', True),
        'retry_max_attempts': config.get('retry_max_attempts', 3),
        'circuit_breaker_threshold': 50 if mode_name == 'deep' else 10,
        'per_domain_limit': 5,
        'storage': multi_storage,
    }
    crawler = AsyncCrawler(**crawler_kwargs)

    effective_depth = args.depth if args.depth is not None else mode_cfg['depth']
    effective_same_domain = mode_cfg['same_domain_only']

    print(f"  Режим: {mode_name.upper()}")
    if mode_name in MODES:
        print(f"  Описание: {MODES[mode_name]['description']}")
    print(f"  Стартовых URL: {len(start_urls)}")
    print(f"  Макс. страниц: {args.pages}")
    print(f"  Глубина: {effective_depth}")
    print(f"  Конкурентность: {crawler_kwargs['max_concurrent']}")
    print(f"  Частота запросов: {crawler_kwargs['requests_per_second']} req/s")
    print(f"  Same domain only: {effective_same_domain}")

    async with crawler:
        results = await crawler.crawl(
            start_urls=start_urls,
            max_pages=args.pages,
            max_depth=effective_depth,
            same_domain_only=effective_same_domain,
        )

    output_data = []
    for url, content in results.items():
        if content.startswith("ERROR:"):
            output_data.append({"url": url, "error": content})
        else:
            output_data.append({"url": url, "html": content[:500]})
    with open(resolve_path("final_results.json"), "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    crawler.stats.export_to_json(resolve_path("stats.json"))
    crawler.stats.export_to_html_report(resolve_path("report.html"))

    crawler.stats.print_stats()

    print(f"  Обработано {len(results)} страниц")
    print(f"  Данные сохранены в папку results/:")
    print(f"    - results.jsonl (JSON Lines)")
    print(f"    - results.csv")
    print(f"    - results.db (SQLite)")
    print(f"    - final_results.json (краткий отчёт)")
    print(f"    - stats.json (статистика)")
    print(f"    - report.html (HTML-отчёт)")
    print(f"    - crawler.log (логи)")

    await crawler.close()


if __name__ == "__main__":
    asyncio.run(main())