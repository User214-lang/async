import asyncio
from crawler import AsyncCrawler

async def demo_parser():
    urls = [
        "https://example.com",
        "https://httpbin.org/get",
        "https://httpbin.org/delay/1",
        "https://httpbin.org/status/404",
        "https://httpbin.org/status/500",
        "https://non-existent-domain-12345.com",
    ]

    all_results = []
    total_links = 0
    total_text_length = 0
    total_images = 0

    async with AsyncCrawler(max_concurrent=3) as crawler:
        for url in urls:
            data = await crawler.fetch_and_parse(url)

            if 'error' in data:
                print(f"Ошибка загрузки {url}: {data['error']}")
                continue

            result = {
                "url": data['url'],
                "title": data['title'],
                "text_length": len(data['text']),
                "links_count": len(data['links']),
                "links": data['links'][:5],
                "images_count": len(data['images'])
            }
            print(result)

            total_links += len(data['links'])
            total_text_length += len(data['text'])
            total_images += len(data['images'])
            all_results.append(result)

    print(f"Всего обработано: {len(all_results)} страниц")
    print(f"Всего ссылок: {total_links}")
    print(f"Всего изображений: {total_images}")
    print(f"Общая длина текста: {total_text_length} символов")

if __name__ == "__main__":
    asyncio.run(demo_parser())