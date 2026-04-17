"""
modelito/scheduler.py

Lightweight scheduled task runner for periodic digests. This is intentionally
minimal and dependency-free; for production use, consider APScheduler.
"""

import threading
import time
from typing import Callable, Dict, Optional, Any

from .utils import setup_logger

_logger = setup_logger("modelito.scheduler")


class ScheduledDigestManager:
    """Manage background periodic jobs.

    schedule_digest starts a daemon thread which invokes the provided callable
    at roughly the given interval (in seconds). Jobs are identified by name.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def schedule_digest(self, name: str, func: Callable, interval_seconds: int, args: Optional[tuple] = None, kwargs: Optional[dict] = None) -> None:
        args = args or ()
        kwargs = kwargs or {}

        stop_event = threading.Event()

        def runner() -> None:
            _logger.info("Scheduled job %s starting, interval=%s", name, interval_seconds)
            while not stop_event.is_set():
                start = time.time()
                try:
                    func(*args, **kwargs)
                except Exception as exc:  # broad catch intentional to keep scheduler running
                    _logger.exception("Scheduled job %s failed: %s", name, exc)
                elapsed = time.time() - start
                wait = max(0, interval_seconds - elapsed)
                stop_event.wait(wait)
            _logger.info("Scheduled job %s stopped", name)

        thread = threading.Thread(target=runner, daemon=True, name=f"scheduled-{name}")
        with self._lock:
            if name in self._jobs:
                raise ValueError(f"Job with name '{name}' already scheduled")
            self._jobs[name] = {"thread": thread, "stop": stop_event}
            thread.start()

    def unschedule(self, name: str) -> None:
        with self._lock:
            job = self._jobs.get(name)
            if not job:
                return
            job["stop"].set()
            job["thread"].join(timeout=5.0)
            del self._jobs[name]

    def list_jobs(self) -> list:
        with self._lock:
            return list(self._jobs.keys())


# Module-level singleton for convenience
manager = ScheduledDigestManager()
