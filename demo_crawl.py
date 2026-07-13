import asyncio
import json
from crawler import AsyncCrawler

async def main():
    async with AsyncCrawler(max_concurrent=5) as crawler:
        results = await crawler.crawl(
            start_urls=["https://example.com"],
            max_pages=20,
            max_depth=2,
            same_domain_only=True
        )

        output = []
        for url, content in results.items():
            if content.startswith("ERROR:"):
                output.append({"url": url, "error": content})
            else:
                output.append({"url": url, "html": content[:1000]})

        with open("crawl_results.json", "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\nРезультаты в crawl_results.json. Всего страниц: {len(results)}")

if __name__ == "__main__":
    asyncio.run(main())