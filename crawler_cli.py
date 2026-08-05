#!/usr/bin/env python3

import asyncio
import argparse
import sys
import json
from typing import List, Optional
from crawler import AsyncCrawler
from config_loader import ConfigLoader
from logging_config import setup_logging
import logging
import os

def resolve_output_path(filename: str) -> str:
    #Вспомогательная функция для сохранения html в /results
    if not filename:
        return filename
    if os.sep in filename or os.path.isabs(filename):
        return filename
    out_dir = "results"
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, filename)

def parse_args():
    parser = argparse.ArgumentParser(
        description="Асинхронный веб-краулер с поддержкой конфигурации и расширенной статистики"
    )
    
    parser.add_argument(
        '--urls',
        nargs='+',
        help='Стартовые url'
    )
    parser.add_argument(
        '--max-pages',
        type=int,
        default=100,
        help='Макс число страниц для загрузки'
    )
    parser.add_argument(
        '--max-depth',
        type=int,
        default=3,
        help='Макс глубина обхода'
    )
    parser.add_argument(
        '--output'
    )
    
    parser.add_argument(
        '--config',
        help='Путь к конфиг файлу'
    )
    
    parser.add_argument(
        '--rate-limit',
        type=float,
        help='Лимит запросов в секунду (requests_per_second)'
    )
    parser.add_argument(
        '--max-concurrent',
        type=int,
        help='Максимальное количество одновременных запросов'
    )
    parser.add_argument(
        '--respect-robots',
        action='store_true',
        default=True
    )
    parser.add_argument(
        '--no-respect-robots',
        action='store_false',
        dest='respect_robots',
        help='Отключить robots.txt'
    )
    
    parser.add_argument(
        '--same-domain',
        action='store_true',
        default=True,
        help='Ограничить обход только доменами стартовых url'
    )
    parser.add_argument(
        '--no-same-domain',
        action='store_false',
        dest='same_domain',
        help='Разрешить переход на внешние домены'
    )
    parser.add_argument(
        '--exclude',
        nargs='+',
        help='Исключить url, содержащие указанные подстроки'
    )
    parser.add_argument(
        '--include',
        nargs='+',
        help='Включать только url, содержащие указанные подстроки'
    )
    
    parser.add_argument(
        '--stats-json',
        help='Сохранить статистику в JSON файл'
    )
    parser.add_argument(
        '--stats-html',
        help='Сохранить статистику в HTML отчёт'
    )

    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Уровень логирования (по умолчанию: INFO)'
    )
    
    parser.add_argument(
        '--log-file',
        help='Путь к файлу лога'
    )

    return parser.parse_args()



async def main():
    args = parse_args()

    if args.output:
        args.output = resolve_output_path(args.output)
    if args.stats_json:
        args.stats_json = resolve_output_path(args.stats_json)
    if args.stats_html:
        args.stats_html = resolve_output_path(args.stats_html)
    if args.log_file:
        args.log_file = resolve_output_path(args.log_file)

    log_level = args.log_level
    log_file = args.log_file

    if args.config:
        config = ConfigLoader.load_config(args.config)
        log_cfg = config.get('logging', {})
        if log_level is None:
            log_level = log_cfg.get('level', 'INFO')
        if log_file is None:
            log_file = log_cfg.get('file')
            if log_file:
                log_file = resolve_output_path(log_file)

        crawler = ConfigLoader.create_crawler_from_config(config)
        start_urls = ConfigLoader.get_start_urls(config)
        filters = ConfigLoader.get_filters(config)
        max_pages = filters['max_pages']
        max_depth = filters['max_depth']
        same_domain_only = filters['same_domain_only']
        exclude_patterns = filters['exclude_patterns']
        include_patterns = filters['include_patterns']
    else:
        if not args.urls:
            print("Ошибка: укажите --urls или --config", file=sys.stderr)
            sys.exit(1)

        start_urls = args.urls
        max_pages = args.max_pages
        max_depth = args.max_depth
        same_domain_only = args.same_domain
        exclude_patterns = args.exclude
        include_patterns = args.include

        crawler_kwargs = {
            'max_concurrent': args.max_concurrent or 10,
            'requests_per_second': args.rate_limit or 5.0,
            'respect_robots': args.respect_robots
        }
        crawler = AsyncCrawler(**crawler_kwargs)

    setup_logging(level=getattr(logging, log_level.upper()), log_file=log_file)

    print(f"Запуск краулера с {len(start_urls)} стартовыми URL...")
    async with crawler:
        results = await crawler.crawl(
            start_urls=start_urls,
            max_pages=max_pages,
            max_depth=max_depth,
            same_domain_only=same_domain_only,
            exclude_patterns=exclude_patterns,
            include_patterns=include_patterns
        )

    if args.output:
        output_data = []
        for url, content in results.items():
            if content.startswith("ERROR:"):
                output_data.append({"url": url, "error": content})
            else:
                output_data.append({"url": url, "html": content[:1000]})
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Результаты сохранены в {args.output}")

    if args.stats_json:
        crawler.stats.export_to_json(args.stats_json)
    if args.stats_html:
        crawler.stats.export_to_html_report(args.stats_html)

    print(f"Обработано {len(results)} страниц")
    crawler.stats.print_stats()


if __name__ == "__main__":
    asyncio.run(main())