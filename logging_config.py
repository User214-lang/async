import logging
from logging.handlers import RotatingFileHandler
import sys

def setup_logging(
    level: int = logging.INFO,
    log_file: str = None,
    console: bool = True,
    format_str: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt: str = '%Y-%m-%d %H:%M:%S'
) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(format_str, datefmt=datefmt)

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)