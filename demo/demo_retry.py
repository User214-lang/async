import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import time
from crawler import AsyncCrawler

async def main():
    print("Демонстрация обработки ошибок и автоматических повторов")
    

    crawler = AsyncCrawler(
        max_concurrent=3,
        requests_per_second=2.0,
        min_delay=0.2,
        jitter=0.1,
        timeout_total=10,
        timeout_read=3,
        timeout_connect=3,
        retry_max_attempts=4,
        retry_backoff_factor=2.0,
        transient_retry_max=4,
        network_retry_max=3,
        rate_limit_retry_max=5,
        rate_limit_retry_backoff=3.0,
        circuit_breaker_threshold=3,
        circuit_breaker_window=30,
        circuit_breaker_cooldown=20
    )

    urls = [
    "https://tools-httpstatus.pickup-services.com/200",              # OK
    "https://tools-httpstatus.pickup-services.com/404",              # Not Found
    "https://tools-httpstatus.pickup-services.com/500",              # Server Error
    "https://tools-httpstatus.pickup-services.com/503",              # Service Unavailable
    "https://tools-httpstatus.pickup-services.com/429",              # Too Many Requests
    "https://tools-httpstatus.pickup-services.com/200?sleep=2000",   # Задержка 2 сек
    "https://tools-httpstatus.pickup-services.com/200?sleep=5000",   # Задержка 5 сек
    "https://this-domain-definitely-does-not-exist-12345.com",       # DNS ошибка
]

    print(f"Загрузка {len(urls)} URL с различными типами ошибок...\n")

    start_time = time.monotonic()
    async with crawler:
        results = await crawler.fetch_urls(urls)
    elapsed = time.monotonic() - start_time

    print("\nРезультаты загрузки:")
    for url, content in results.items():
        if content.startswith("ERROR:"):
            print(f"  ERROR {url}: {content[:100]}...")
        else:
            print(f"  OK {url}: размер {len(content)} байт")

    print("Статистика ошибок из краулера")
    print(f"Всего успешных запросов: {crawler.total_requests}")
    print(f"Всего ошибок: {len(crawler.failed_urls)}")
    print(f"Блокировано robots.txt: {crawler.blocked_by_robots}\n")

    print("\nДетальная статистика по типам ошибок")
    if crawler.error_stats:
        print("\nРаспределение ошибок по типам:")
        for err_type, count in sorted(crawler.error_stats.items(), key=lambda x: -x[1]):
            print(f"  {err_type}: {count}")

    if crawler.permanent_error_urls:
        print(f"\nURL с постоянными ошибками (не будут повторяться):\n")
        for url in crawler.permanent_error_urls:
            print(f"  - {url}")

    print("\nСтатистика повторов из RetryStrategy")
    retry_stats = crawler.retry_strategy.get_retry_stats()
    print(f"\nСтатистика повторов:")
    print(f"  Успешных повторов: {retry_stats['successful_retries']}")
    total_retries = retry_stats['total_attempts'] - crawler.total_requests
    print(f"  Всего попыток (включая первые): {retry_stats['total_attempts']}")
    avg_retry_time = retry_stats['total_retry_time'] / retry_stats['successful_retries'] if retry_stats['successful_retries'] > 0 else 0
    print(f"  Среднее время на успешный повтор: {avg_retry_time:.2f}с")

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_urls": len(urls),
        "successful_requests": crawler.total_requests,
        "failed_requests": len(crawler.failed_urls),
        "error_stats": crawler.error_stats,
        "permanent_error_urls": list(crawler.permanent_error_urls),
        "retry_stats": retry_stats,
        "blocked_by_robots": crawler.blocked_by_robots,
        "results": results
    }

    import os
    os.makedirs("results", exist_ok=True)
    with open("error_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nОтчёт об ошибках сохранён в error_report.json")

if __name__ == "__main__":
    asyncio.run(main())