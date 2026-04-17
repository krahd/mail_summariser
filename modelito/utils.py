"""
modelito/utils.py

Shared utility functions for the LLM provider library.
"""

import os
import logging
import time
import threading
import asyncio
from collections import deque
from typing import Any

def mask_api_key(key: str) -> str:
    if not key or len(key) < 8:
        return "***"
    return key[:3] + "..." + key[-3:]

def get_env_setting(name: str, default: Any = None) -> Any:
    return os.getenv(name, default)

def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('[%(levelname)s] %(name)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


class RateLimiter:
    """Simple token-bucket style rate limiter.

    - `max_calls` calls are allowed per `period` seconds.
    - `acquire()` blocks the current thread until a slot is available.
    - `acquire_async()` is an async-friendly wrapper.
    """

    def __init__(self, max_calls: int = 60, period: float = 60.0):
        self.max_calls = int(max_calls)
        self.period = float(period)
        self._lock = threading.Lock()
        self._calls = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        with self._lock:
            # evict old timestamps
            while self._calls and now - self._calls[0] >= self.period:
                self._calls.popleft()
            if len(self._calls) < self.max_calls:
                self._calls.append(now)
                return
            # need to wait until the oldest timestamp falls out of the window
            earliest = self._calls[0]
            wait = self.period - (now - earliest)
        time.sleep(max(0.0, wait))
        # after sleeping, try again (non-recursive)
        now = time.monotonic()
        with self._lock:
            while self._calls and now - self._calls[0] >= self.period:
                self._calls.popleft()
            self._calls.append(now)

    async def acquire_async(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.acquire)
