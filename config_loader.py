import yaml
import json
from typing import Dict, Any, Optional, List, Union
from crawler import AsyncCrawler
from storage import JsonStorage, CsvStorage, SqliteStorage, DataStorage

class ConfigLoader:

    @staticmethod
    def load_config(filepath: str) -> Dict[str, Any]:
        with open(filepath, 'r', encoding='utf-8') as f:
            if filepath.endswith('.json'):
                return json.load(f)
            else:
                return yaml.safe_load(f)

    @staticmethod
    def create_storage(config: Dict[str, Any]) -> Optional[DataStorage]:
        storage_cfg = config.get('storage', {})
        storage_type = storage_cfg.get('type')
        if not storage_type:
            return None
        if storage_type == 'json':
            return JsonStorage(
                filepath=storage_cfg.get('path', 'results.jsonl'),
                indent=storage_cfg.get('indent', None),
                buffer_size=storage_cfg.get('buffer_size', 10)
            )
        elif storage_type == 'csv':
            return CsvStorage(
                filepath=storage_cfg.get('path', 'results.csv'),
                encoding=storage_cfg.get('encoding', 'utf-8'),
                buffer_size=storage_cfg.get('buffer_size', 10)
            )
        elif storage_type == 'sqlite':
            return SqliteStorage(
                db_path=storage_cfg.get('path', 'results.db'),
                batch_size=storage_cfg.get('batch_size', 100)
            )
        else:
            raise ValueError(f"Unknown storage type: {storage_type}")

    @staticmethod
    def create_crawler_from_config(config: Dict[str, Any]) -> AsyncCrawler:
        crawler_params = {
            'max_concurrent': config.get('max_concurrent', 10),
            'timeout_total': config.get('timeout_total', 30),
            'timeout_connect': config.get('timeout_connect', 5),
            'timeout_read': config.get('timeout_read', 5),
            'timeout_increase_factor': config.get('timeout_increase_factor', 1.5),
            'max_timeout_total': config.get('max_timeout_total', 120),
            'max_timeout_connect': config.get('max_timeout_connect', 30),
            'max_timeout_read': config.get('max_timeout_read', 30),
            'limit_connections': config.get('limit_connections', 100),
            'limit_per_host': config.get('limit_per_host', 30),
            'requests_per_second': config.get('requests_per_second', 5.0),
            'per_domain_limit': config.get('per_domain_limit', 5),
            'min_delay': config.get('min_delay', 0.5),
            'jitter': config.get('jitter', 0.3),
            'backoff_factor': config.get('backoff_factor', 2.0),
            'max_backoff': config.get('max_backoff', 60.0),
            'user_agent': config.get('user_agent', 'AsyncCrawler/1.0'),
            'retry_max_attempts': config.get('retry_max_attempts', 3),
            'retry_backoff_factor': config.get('retry_backoff_factor', 2.0),
            'transient_retry_max': config.get('transient_retry_max'),
            'transient_retry_backoff': config.get('transient_retry_backoff'),
            'network_retry_max': config.get('network_retry_max'),
            'network_retry_backoff': config.get('network_retry_backoff'),
            'rate_limit_retry_max': config.get('rate_limit_retry_max'),
            'rate_limit_retry_backoff': config.get('rate_limit_retry_backoff'),
            'circuit_breaker_threshold': config.get('circuit_breaker_threshold', 5),
            'circuit_breaker_window': config.get('circuit_breaker_window', 60.0),
            'circuit_breaker_cooldown': config.get('circuit_breaker_cooldown', 30.0),
            'storage': config.get('storage') if isinstance(config.get('storage'), DataStorage) else ConfigLoader.create_storage(config)
        }
        if 'sitemap_url' in config:
            crawler_params['sitemap_url'] = config['sitemap_url']
        return AsyncCrawler(**crawler_params)

    

    @staticmethod
    def get_start_urls(config: Dict[str, Any]) -> List[str]:
        return config.get('start_urls', [])

    @staticmethod
    def get_filters(config: Dict[str, Any]) -> Dict[str, Any]:
        filters = config.get('filters', {})
        return {
            'same_domain_only': filters.get('same_domain_only', True),
            'exclude_patterns': filters.get('exclude_patterns'),
            'include_patterns': filters.get('include_patterns'),
            'max_pages': config.get('max_pages', 100),
            'max_depth': config.get('max_depth', 3),
        }