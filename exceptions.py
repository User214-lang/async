class CrawlerError(Exception):
    """Базовое исключение для всех ошибок краулера."""
    pass

class TransientError(CrawlerError):
    """Временная ошибка, которую стоит повторить (таймауты, 503, 429)."""
    pass

class PermanentError(CrawlerError):
    """Постоянная ошибка, повтор не поможет (404, 403, 401)."""
    pass

class NetworkError(CrawlerError):
    """Сетевая ошибка (DNS, соединение отказано)."""
    pass

class ParseError(CrawlerError):
    """Ошибка парсинга HTML."""
    pass

class RateLimitError(TransientError):
    """Ошибка для 429 Too Many Requests."""
    pass