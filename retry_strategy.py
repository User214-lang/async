import asyncio
import logging
import time
from exceptions import PermanentError, TransientError, NetworkError, RateLimitError

logger = logging.getLogger(__name__)


class RetryStrategy:
    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        transient_max_retries: int = None,
        transient_backoff_factor: float = None,
        network_max_retries: int = None,
        network_backoff_factor: float = None,
        rate_limit_max_retries: int = None,
        rate_limit_backoff_factor: float = None,
        retry_on: tuple = None
    ):
        self.default_max_retries = max_retries
        self.default_backoff_factor = backoff_factor

        self.transient_max_retries = transient_max_retries or max_retries
        self.transient_backoff_factor = transient_backoff_factor or backoff_factor
        self.network_max_retries = network_max_retries or max_retries
        self.network_backoff_factor = network_backoff_factor or backoff_factor
        self.rate_limit_max_retries = rate_limit_max_retries or max_retries
        self.rate_limit_backoff_factor = rate_limit_backoff_factor or backoff_factor

        self._attempts = 0
        self._attempt_details = []
        self._successful_retries = 0
        self._total_retry_time = 0.0

        if retry_on is None:
            self.retry_on = (TransientError, NetworkError, RateLimitError)
        else:
            self.retry_on = retry_on

    async def execute_with_retry(self, func, *args, **kwargs):
        attempt = 0
        current_max_retries = self.default_max_retries
        current_backoff_factor = self.default_backoff_factor
        error_type_set = False
        self._attempt_details = []
        self._attempts = 0

        while True:
            self._attempts += 1
            attempt += 1
            attempt_start = time.monotonic()
            delay = 0

            try:
                result = await func(*args, **kwargs)
                if attempt > 1:
                    self._successful_retries += 1
                    self._total_retry_time += time.monotonic() - attempt_start
                self._attempt_details.append({
                    'attempt': attempt,
                    'error': None,
                    'error_type': None,
                    'delay': 0,
                    'timestamp': attempt_start,
                    'success': True
                })
                return result
            except Exception as e:
                delay = 0
                if attempt < current_max_retries:
                    delay = current_backoff_factor ** attempt
                self._attempt_details.append({
                    'attempt': attempt,
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'delay': delay,
                    'timestamp': attempt_start,
                    'success': False
                })

                if isinstance(e, PermanentError):
                    raise
                if not isinstance(e, self.retry_on):
                    raise

                if not error_type_set:
                    if isinstance(e, RateLimitError):
                        current_max_retries = self.rate_limit_max_retries
                        current_backoff_factor = self.rate_limit_backoff_factor
                    elif isinstance(e, TransientError):
                        current_max_retries = self.transient_max_retries
                        current_backoff_factor = self.transient_backoff_factor
                    elif isinstance(e, NetworkError):
                        current_max_retries = self.network_max_retries
                        current_backoff_factor = self.network_backoff_factor
                    error_type_set = True

                if attempt >= current_max_retries:
                    logger.error(
                        f"Превышено максимальное число попыток ({current_max_retries}) для {type(e).__name__}: {e}"
                    )
                    raise

                delay = current_backoff_factor ** attempt
                logger.warning(
                    f"Попытка {attempt} не удалась ({e}). Повтор через {delay} сек"
                )
                await asyncio.sleep(delay)

    def get_retry_stats(self) -> dict:
        return {
            'successful_retries': self._successful_retries,
            'total_retry_time': self._total_retry_time,
            'attempt_details': self._attempt_details,
            'total_attempts': self._attempts
        }

    @property
    def attempts(self) -> int:
        return self._attempts