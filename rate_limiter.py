import asyncio
import time
import random
from typing import Dict, Optional

class RateLimiter:
    def __init__(
        self,
        requests_per_second: float = 1.0,
        per_domain: bool = True,
        min_delay: float = 0.5,
        jitter: float = 0.3,
        backoff_factor: float = 2.0,
        max_backoff: float = 60.0
    ):
        self.requests_per_second = requests_per_second
        self.per_domain = per_domain
        self.min_delay = min_delay
        self.jitter = jitter
        self.backoff_factor = backoff_factor
        self.max_backoff = max_backoff

        self._last_request_time: Dict[str, float] = {}
        self._backoff_multiplier: Dict[str, float] = {}
        self._global_last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self, domain: Optional[str] = None) -> None:
        async with self._lock:
            if self.per_domain and domain is None:
                raise ValueError("domain обязателен при per_domain=True")

            key = domain if self.per_domain else 'global'

            #Базовая задержка
            base_interval = 1.0 / self.requests_per_second
            #Минимальная задержка
            effective_min = max(self.min_delay, base_interval)
            #jitter
            jitter_val = random.uniform(0, self.jitter)
            #backoff
            backoff = self._backoff_multiplier.get(key, 1.0)
            #Итог
            delay = (effective_min + jitter_val) * backoff

            delay = min(delay, self.max_backoff)

            last = self._last_request_time.get(key, 0.0) if self.per_domain else self._global_last
            elapsed = time.monotonic() - last
            wait = delay - elapsed
            if wait > 0:
                await asyncio.sleep(wait)

            now = time.monotonic()
            if self.per_domain:
                self._last_request_time[key] = now
            else:
                self._global_last = now

    def record_failure(self, domain: str) -> None:
        key = domain if self.per_domain else 'global'
        current = self._backoff_multiplier.get(key, 1.0)
        new_backoff = min(current * self.backoff_factor, self.max_backoff / (1.0 / self.requests_per_second + self.min_delay))
        self._backoff_multiplier[key] = new_backoff

    def record_success(self, domain: str) -> None:
        key = domain if self.per_domain else 'global'
        if key in self._backoff_multiplier:
            self._backoff_multiplier[key] = 1.0