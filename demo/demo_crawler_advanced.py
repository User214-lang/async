import asyncio
from crawler import AsyncCrawler

async def main():
    print("Краулер с robots.txt, rate limiting и статистика")

    crawler = AsyncCrawler(
        max_concurrent=3,
        requests_per_second=2.0,
        min_delay=0.5,
        jitter=0.3,
        user_agent="MyBot/1.0",
        timeout_read=5,
        timeout_connect=5
    )

    start_urls = ["https://httpbin.org"]

    async with crawler:
        await crawler.crawl(
            start_urls=start_urls,
            max_pages=5,
            max_depth=1,
            same_domain_only=True
        )

    print("Итоговая статистика:")
    print(f"Успешно обработано страниц: {len(crawler.processed_urls)}")
    print(f"Ошибок: {len(crawler.failed_urls)}")
    print(f"Блокировано robots.txt: {crawler.blocked_by_robots}")
    if crawler.total_requests > 0:
        avg_delay = crawler.total_time / crawler.total_requests
        print(f"Средняя задержка на успешный запрос: {avg_delay:.2f} с")
    else:
        print("Успешных запросов не было, средняя задержка не определена")

if __name__ == "__main__":
    asyncio.run(main())