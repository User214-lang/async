# Асинхронный веб-краулер

Расширяемый асинхронный краулер на Python с поддержкой конкурентности, очередей, rate limiting, robots.txt, автоматических повторов, сохранения данных и продвинутой статистики.

Запуск краулера:
python crawler_cli.py --urls https://example.com https://httpbin.org --max-pages 20 --output results.json

Запуск с конфиг файлом:
python crawler_cli.py --config config.yaml --output results.json

Запуск демонстрации работы:
python demo/final_demo_crawler.py - комплексный пример с конфигурацией, логированием, статистикой и экспортом отчётов.
python demo_retry.py – демонстрирует автоматические повторы и классификацию ошибок.
python demo_storage.py – показывает сохранение в JSON, CSV и SQLite.
python demo_sitemap.py – загрузка URL из sitemap.xml.

Запуск тестов:
pytest -v tests.py
