# 🕷️ Асинхронный веб-краулер

Расширяемый асинхронный краулер на Python с поддержкой конкурентности, очередей с приоритетами,
rate limiting, robots.txt, автоматических повторов, сохранения данных и продвинутой статистики.

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![aiohttp](https://img.shields.io/badge/aiohttp-3.x-brightgreen.svg)
![pytest](https://img.shields.io/badge/pytest-31%20passed-success.svg)
![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)

---

## 📋 Содержание

- [Возможности](#возможности)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [Демонстрации](#демонстрации)
- [Использование в коде](#использование-в-коде)
- [Конфигурация](#конфигурация)
- [Классификация ошибок](#классификация-ошибок)
- [Хранилища](#хранилища)
- [Структура проекта](#структура-проекта)
- [Тесты](#тесты)

---

## ✨ Возможности

- ⚡ **Асинхронность** — `asyncio` + `aiohttp`, одновременная обработка множества страниц
- 🚦 **Rate limiting** — ограничение частоты запросов для каждого домена
- 🤖 **Robots.txt** — автоматический парсинг правил и соблюдение `Crawl-delay`
- 🔁 **Автоматические повторы** — экспоненциальный backoff с классификацией ошибок
- 🛡️ **Circuit Breaker** — автоматическая временная блокировка проблемных доменов
- 📊 **Очередь с приоритетами** — умное планирование обхода и ограничение глубины
- 💾 **Хранилища** — сохранение результатов в JSON (JSONL), CSV и SQLite с буферизацией
- ⏱️ **Адаптивные таймауты** — автоматическое увеличение таймаутов при повторах
- 🎭 **Ротация User-Agent** — поддержка нескольких User-Agent
- 📈 **Статистика и отчёты** — скорость, задержки, ошибки, экспорт отчётов в JSON

---

## 📦 Установка

1. Клонируйте репозиторий и перейдите в папку проекта:

```bash
git clone https://github.com/your-username/async-crawler.git
cd async-crawler
```

2. Создайте и активируйте виртуальное окружение:

```bash
python -m venv .venv
source .venv/bin/activate    # Linux / macOS
.venv\Scripts\activate       # Windows
```

3. Установите зависимости:

```bash
pip install aiohttp beautifulsoup4 lxml aiosqlite aiofiles pyyaml pytest pytest-asyncio
```

---

## 🚀 Быстрый старт

Запуск краулера с указанием URL:

```bash
python crawler_cli.py --urls https://example.com https://httpbin.org --max-pages 20 --output results.json
```

Запуск с конфигурационным файлом:

```bash
python crawler_cli.py --config config.yaml --output results.json
```

---

## 🎬 Демонстрации

| Скрипт | Что демонстрирует |
|--------|-------------------|
| `demo/final_demo_crawler.py` | Комплексный пример: конфигурация, логирование, статистика, экспорт отчётов |
| `demo/demo_retry.py` | Автоматические повторы и классификацию ошибок |
| `demo/demo_storage.py` | Сохранение результатов в JSON, CSV и SQLite |
| `demo/demo_sitemap.py` | Загрузку URL из `sitemap.xml` |

```bash
python demo/final_demo_crawler.py
python demo/demo_retry.py
python demo/demo_storage.py
python demo/demo_sitemap.py
```

---

## 💻 Использование в коде

```python
import asyncio
from crawler import AsyncCrawler
from storage import JsonStorage

async def main():
    storage = JsonStorage("results.jsonl", buffer_size=10)

    async with AsyncCrawler(max_concurrent=5, storage=storage) as crawler:
        await crawler.crawl(
            start_urls=["https://example.com"],
            max_pages=50,
            max_depth=2,
            same_domain_only=True
        )

asyncio.run(main())
```

---

## ⚙️ Конфигурация

Ключи `config.yaml` соответствуют параметрам конструктора `AsyncCrawler`:

```yaml
max_concurrent: 10          # максимум одновременных запросов
requests_per_second: 5.0    # лимит запросов в секунду (per-domain)
retry_max_attempts: 3       # максимум повторов для временных ошибок
timeout_total: 30           # общий таймаут запроса, сек
```

Основные параметры:

| Параметр | По умолчанию | Описание |
|----------|:------------:|----------|
| `max_concurrent` | `10` | Максимум одновременных запросов |
| `timeout_total` / `connect` / `read` | `30 / 5 / 5` | Таймауты (сек), растут при повторах |
| `requests_per_second` | `5.0` | Лимит частоты запросов по доменам |
| `per_domain_limit` | `5` | Лимит одновременных запросов к одному домену |
| `retry_max_attempts` | `3` | Максимум повторов |
| `circuit_breaker_threshold` | `5` | Порог ошибок для блокировки домена |
| `storage` | `None` | Хранилище результатов |
| `save_retry_attempts` | `3` | Повторы при ошибке сохранения |

---

## 🧯 Классификация ошибок

| Ошибка | Когда возникает | Поведение |
|--------|-----------------|-----------|
| `TransientError` | 5xx ошибки сервера | Повтор, экспоненциальный backoff |
| `RateLimitError` | 429 Too Many Requests | Повтор с увеличенным backoff |
| `NetworkError` | Таймауты, DNS, разрывы соединения | Повтор |
| `PermanentError` | 4xx ошибки клиента | Без повторов |

---

## 💾 Хранилища

| Класс | Формат | Особенности |
|-------|--------|-------------|
| `JsonStorage` | `.jsonl` | Одна JSON-запись на строку, буферизация |
| `CsvStorage` | `.csv` | Автозаголовок, сериализация списков и словарей |
| `SqliteStorage` | `.db` | Пакетные вставки, индекс по URL |

---

## 🗂️ Структура проекта

```
async-crawler/
├── crawler.py            # Основной класс AsyncCrawler
├── crawler_cli.py        # CLI-интерфейс
├── parser.py             # Парсинг HTML (BeautifulSoup)
├── queue_manager.py      # Очередь URL с приоритетами
├── semaphore_manager.py  # Ограничение конкурентности
├── rate_limiter.py       # Rate limiting по доменам
├── robots_parser.py      # Парсинг и соблюдение robots.txt
├── retry_strategy.py     # Повторы с экспоненциальным backoff
├── circuit_breaker.py    # Circuit Breaker
├── exceptions.py         # Иерархия ошибок
├── storage.py            # Хранилища: JSON, CSV, SQLite
├── config.yaml           # Пример конфигурации
├── tests.py              # Тесты (pytest)
└── demo/
    ├── final_demo_crawler.py
    ├── demo_retry.py
    ├── demo_storage.py
    └── demo_sitemap.py
```

---

## 🧪 Тесты

```bash
pytest -v tests.py
```
