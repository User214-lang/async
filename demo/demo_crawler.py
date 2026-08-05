import asyncio
import time
from crawler import AsyncCrawler


async def demo():
    urls = [
        "https://example.com",
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/2",
        "https://httpbin.org/status/404",
        "https://httpbin.org/status/500",
        "https://httpbin.org/get",
        "https://httpbin.org/bytes/1024",
        "https://non-existent-domain-12345.com",
    ]

    start = time.time()
    async with AsyncCrawler(max_concurrent=5) as crawler:
        results = await crawler.fetch_urls(urls)
    elapsed_parallel = time.time() - start

    print(f"\nВремя параллельной загрузки: {elapsed_parallel:.2f} с")
    print("\nРезультаты:")
    for url, content in results.items():
        if content.startswith("ERROR:"):
            print(f"{url} -> {content} NO")
        else:
            print(f"{url} -> размер: {len(content)} байт")

    valid_urls = [u for u in urls if not u.startswith("https://non-existent") and "status/4" not in u and "status/5" not in u][:3]
    if valid_urls:
        
        #Сравнение с последовательной загрузкой
        start_seq = time.time()
        async with AsyncCrawler(max_concurrent=1) as seq_crawler:
            seq_results = await seq_crawler.fetch_urls(valid_urls)
        elapsed_seq = time.time() - start_seq

        print(f"Время последовательной загрузки: {elapsed_seq:.2f} с")
        print(f"Время параллельной загрузки (всех URL): {elapsed_parallel:.2f} с")
        print(f"Ускорение: {elapsed_seq / elapsed_parallel:.2f}x")
    else:
        print("\nНет валидных URL для сравнения с последовательной загрузкой.")


if __name__ == "__main__":
    asyncio.run(demo())