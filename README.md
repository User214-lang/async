# Асинхронный веб-краулер

Расширяемый асинхронный краулер на Python с поддержкой конкурентности, очередей с приоритетами,
rate limiting, robots.txt, автоматических повторов, сохранения данных и продвинутой статистики.

---

- **Асинхронность** — `asyncio` + `aiohttp`, одновременная обработка множества страниц
- **Rate limiting** — ограничение частоты запросов для каждого домена
- **Robots.txt** — автоматический парсинг правил и соблюдение `Crawl-delay`
- **Автоматические повторы** — экспоненциальный backoff с классификацией ошибок
- **Circuit Breaker** — автоматическая временная блокировка проблемных доменов
- **Очередь с приоритетами** — умное планирование обхода и ограничение глубины
- **Хранилища** — сохранение результатов в JSON (JSONL), CSV и SQLite с буферизацией
- **Адаптивные таймауты** — автоматическое увеличение таймаутов при повторах
- **Ротация User-Agent** — поддержка нескольких User-Agent
- **Статистика и отчёты** — скорость, задержки, ошибки, экспорт отчётов в JSON

---

# Пример работы на ~3000 стр.

Команда запуска:

```bash
python demo/final_demo_crawler.py --mode deep --pages 3000 --depth 6
```

Логи: [`results.log`](results/results.log)

Результат: [`report.html`](results/report.html)

Папка с результатами: [`results/`](results/)

---

## Установка

1. Клонируйте репозиторий и перейдите в папку проекта:

```bash
git clone https://github.com/User214-lang/async
cd async
```

2. Установите зависимости:

```bash
pip install requirements.txt
```

---

## Быстрый старт

Запуск краулера с указанием URL:

```bash
python crawler_cli.py --urls https://example.com https://httpbin.org --max-pages 20 --output results.json
```

Запуск с конфигурационным файлом:

```bash
python crawler_cli.py --config config.yaml --output results.json
```

---

## Демонстрации

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

## Конфигурация

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

## Хранилища

| Класс | Формат | Особенности |
|-------|--------|-------------|
| `JsonStorage` | `.jsonl` | Одна JSON-запись на строку, буферизация |
| `CsvStorage` | `.csv` | Автозаголовок, сериализация списков и словарей |
| `SqliteStorage` | `.db` | Пакетные вставки, индекс по URL |

---

## 🗂️ Структура проекта

```text
async-crawler/
├── crawler.py              # Ядро: класс AsyncCrawler, оркестрация обхода
├── crawler_cli.py          # CLI-интерфейс на argparse
├── parser.py               # Парсинг HTML через BeautifulSoup
├── queue_manager.py        # Очередь URL с приоритетами (PriorityQueue)
├── semaphore_manager.py    # Семафоры: глобальный + per-domain
├── rate_limiter.py         # Rate limiting с jitter и backoff
├── robots_parser.py        # Парсинг robots.txt и Crawl-delay
├── retry_strategy.py       # Повторы с экспоненциальным backoff
├── circuit_breaker.py      # Circuit Breaker для блокировки доменов
├── exceptions.py           # Иерархия кастомных исключений
├── storage.py              # Хранилища: JSON, CSV, SQLite
├── config_loader.py        # Загрузка и валидация YAML-конфига
├── crawler_stats.py        # Сбор статистики и экспорт отчётов
├── logging_config.py       # Настройка логирования
├── sitemap_parser.py       # Парсинг sitemap.xml
├── config.yaml             # Пример конфигурации
├── requirements.txt        # Зависимости проекта
├── tests.py                # Тесты (pytest)
├── demo/                   # Демонстрационные скрипты
│   ├── final_demo_crawler.py
│   ├── demo_retry.py
│   ├── demo_storage.py
│   ├── demo_crawl.py
│   ├── demo_crawler.py
│   ├── demo_crawler_advanced.py
│   └── demo_parser.py
├── results/                # Актуальные результаты краулинга
│   ├── crawler.log
│   ├── final_results.json
│   ├── report.html
│   ├── result.json
│   ├── results.csv
│   ├── results.db
│   ├── results.jsonl
│   └── stats.json
└── archive/
```

---

## Тесты

```bash
pytest -v tests.py
```
