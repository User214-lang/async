import asyncio
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class SemaphoreManager:

    def __init__(self, global_limit: int = 20, per_domain_limit: int = 5):
        self.global_limit = global_limit
        self.per_domain_limit = per_domain_limit
        self._global_semaphore = asyncio.Semaphore(global_limit)
        self._domain_semaphores: Dict[str, asyncio.Semaphore] = {}
        self._active_global = 0
        self._active_per_domain: Dict[str, int] = {}

    async def acquire(self, domain: str) -> None:
        await self._global_semaphore.acquire()
        self._active_global += 1
        if domain not in self._domain_semaphores:
            self._domain_semaphores[domain] = asyncio.Semaphore(self.per_domain_limit)
            self._active_per_domain[domain] = 0

        await self._domain_semaphores[domain].acquire()
        self._active_per_domain[domain] += 1

        logger.debug(f"Семафоры для домена {domain}. "
                     f"Глобально активно: {self._active_global}, "
                     f"На домене: {self._active_per_domain[domain]}")

    def release(self, domain: str) -> None:
        if domain in self._domain_semaphores:
            self._domain_semaphores[domain].release()
            self._active_per_domain[domain] -= 1
            if self._active_per_domain[domain] == 0:
                pass

        self._global_semaphore.release()
        self._active_global -= 1

        logger.debug(f"Освобождены семафоры для домена {domain}. "
                     f"Глобально активно: {self._active_global}, "
                     f"На домене: {self._active_per_domain.get(domain, 0)}")

    def get_active_stats(self) -> Dict:
        return {
            'active_global': self._active_global,
            'active_per_domain': self._active_per_domain.copy(),
            'global_limit': self.global_limit,
            'per_domain_limit': self.per_domain_limit,
        }

    def reset_domain_semaphores(self) -> None:
        self._domain_semaphores.clear()
        self._active_per_domain.clear()