import time
import logging
from collections import deque
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CircuitBreakerOpenError(Exception):
    #Исключение, выбрасывается при попытке запроса к заблокированному домену
    pass


class CircuitBreaker:
    
    def __init__(
        self,
        error_threshold: int = 5,
        time_window: float = 60.0,
        cooldown: float = 30.0
    ):
        self.error_threshold = error_threshold
        self.time_window = time_window
        self.cooldown = cooldown
        self._errors = deque()
        self._state = 'closed'
        self._open_until = 0.0

    def record_success(self) -> None:
        pass

    def record_failure(self) -> None:
        #Запись ошибки
        now = time.monotonic()
        self._errors.append(now)
        self._clean_old_errors(now)
        if len(self._errors) >= self.error_threshold:
            self._open_until = now + self.cooldown
            self._state = 'open'
            logger.warning(f"Circuit breaker перешёл в OPEN для домена (ошибок: {len(self._errors)})")

    def _clean_old_errors(self, now: float) -> None:
        #Удаление записи старше n
        cutoff = now - self.time_window
        while self._errors and self._errors[0] < cutoff:
            self._errors.popleft()

    def is_allowed(self) -> bool:
        if self._state == 'closed':
            return True
        #OPEN
        if time.monotonic() >= self._open_until:
            self._state = 'closed'
            self._errors.clear()
            logger.info("Circuit breaker восстановлен (переход в CLOSED)")
            return True
        return False

    def get_state(self) -> str:
        return self._state

class CircuitBreakerManager:
    def __init__(
        self,
        error_threshold: int = 5,
        time_window: float = 60.0,
        cooldown: float = 30.0
    ):
        self.error_threshold = error_threshold
        self.time_window = time_window
        self.cooldown = cooldown
        self._breakers: Dict[str, CircuitBreaker] = {}

    def get_breaker(self, domain: str) -> CircuitBreaker:
        if domain not in self._breakers:
            self._breakers[domain] = CircuitBreaker(
                error_threshold=self.error_threshold,
                time_window=self.time_window,
                cooldown=self.cooldown
            )
        return self._breakers[domain]

    def record_success(self, domain: str) -> None:
        breaker = self.get_breaker(domain)
        breaker.record_success()

    def record_failure(self, domain: str) -> None:
        breaker = self.get_breaker(domain)
        breaker.record_failure()

    def is_allowed(self, domain: str) -> bool:
        breaker = self.get_breaker(domain)
        return breaker.is_allowed()