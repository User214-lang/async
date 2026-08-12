from typing import Dict, Any, Optional, Union
import logging
from crawler import AsyncCrawler
from config_loader import ConfigLoader
from logging_config import setup_logging
from storage import DataStorage

logger = logging.getLogger(__name__)


class AdvancedCrawler:

    def __init__(
        self,
        config: Union[str, Dict[str, Any]],
        override_params: Optional[Dict[str, Any]] = None
    ):
        self.config = self._load_config(config)
        self.override_params = override_params or {}

        self._setup_logging()
        self.storage = self._create_storage()
        self.crawler = self._create_crawler()
        self._finished = False

    def _load_config(self, config: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        if isinstance(config, dict):
            return config
        return ConfigLoader.load_config(config)

    def _setup_logging(self) -> None:
        log_cfg = self.config.get('logging', {})
        level_name = log_cfg.get('level', 'INFO').upper()
        level = getattr(logging, level_name, logging.INFO)
        log_file = log_cfg.get('file')
        console = log_cfg.get('console', True)
        setup_logging(level=level, log_file=log_file, console=console)

    def _create_storage(self) -> Optional[DataStorage]:
        storage_cfg = self.config.get('storage')
        if not storage_cfg:
            return None
        return ConfigLoader.create_storage(self.config)

    def _create_crawler(self) -> AsyncCrawler:
        params = self.config.copy()
        if self.override_params:
            params.update(self.override_params)
        params['storage'] = self.storage
        return ConfigLoader.create_crawler_from_config(params)

    async def run(self, **kwargs) -> Dict[str, str]:
        start_urls = kwargs.pop('start_urls', None) or self.config.get('start_urls', [])
        max_pages = kwargs.pop('max_pages', None) or self.config.get('max_pages', 100)
        max_depth = kwargs.pop('max_depth', None) or self.config.get('max_depth', 3)
        same_domain_only = kwargs.pop('same_domain_only', None)
        if same_domain_only is None:
            same_domain_only = self.config.get('filters', {}).get('same_domain_only', True)
        exclude_patterns = kwargs.pop('exclude_patterns', None) or self.config.get('filters', {}).get('exclude_patterns')
        include_patterns = kwargs.pop('include_patterns', None) or self.config.get('filters', {}).get('include_patterns')

        logger.info(f"Запуск краулинга с {len(start_urls)} стартовыми URL...")
        async with self.crawler:
            results = await self.crawler.crawl(
                start_urls=start_urls,
                max_pages=max_pages,
                max_depth=max_depth,
                same_domain_only=same_domain_only,
                exclude_patterns=exclude_patterns,
                include_patterns=include_patterns,
                **kwargs
            )
        self._finished = True
        return results

    def export_results(self, output_file: str = None) -> None:
        if not self._finished:
            logger.warning("Краулинг ещё не завершён, статистика может быть неполной.")
        if output_file:
            self.crawler.stats.export_to_json(output_file)
            logger.info(f"Результаты сохранены в {output_file}")

    def export_report(self, report_file: str = "report.html") -> None:
        if not self._finished:
            logger.warning("Краулинг ещё не завершён, отчёт может быть неполным.")
        self.crawler.stats.export_to_html_report(report_file)

    def print_stats(self) -> None:
        if not self._finished:
            logger.warning("Краулинг ещё не завершён, статистика может быть неполной.")
        self.crawler.stats.print_stats()

    @property
    def stats(self):
        return self.crawler.stats if self.crawler else None

    @classmethod
    def from_config(cls, config_path: str, override_params: Optional[Dict[str, Any]] = None) -> "AdvancedCrawler":
        return cls(config_path, override_params)

    async def crawl(self, **kwargs) -> Dict[str, str]:
        return await self.run(**kwargs)

    def get_stats(self) -> Dict[str, Any]:
        if not self._finished:
            logger.warning("Краулинг ещё не завершён, статистика может быть неполной.")
        stats = self.crawler.stats.get_stats() if self.crawler else {}
        return {
            'total_pages': stats.get('total_processed', 0),
            'successful': stats.get('successful_requests', 0),
            'failed': stats.get('failed_requests', 0),
            'duration': stats.get('duration', 0.0),
            'average_speed': stats.get('average_speed', 0.0),
            'status_code_distribution': stats.get('status_code_distribution', {}),
            'top_domains': stats.get('top_domains', [])
        }

    def export_to_html_report(self, filename: str = "report.html") -> None:
        self.export_report(filename)

    async def close(self) -> None:
        if hasattr(self.crawler, '_session') and self.crawler._session:
            await self.crawler._session.close()
            logger.info("Сессия закрыта")
        if hasattr(self.crawler, 'storage') and self.crawler.storage:
            await self.crawler.storage.close()
