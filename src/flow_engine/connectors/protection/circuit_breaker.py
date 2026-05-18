"""Simple circuit breaker per instance."""

from __future__ import annotations

import threading
import time


class CircuitBreaker:
    def __init__(self, failure_threshold: int, open_sec: float) -> None:
        self._failure_threshold = max(1, failure_threshold)
        self._open_sec = max(1.0, open_sec)
        self._failures = 0
        self._open_until = 0.0
        self._lock = threading.Lock()

    def before_call(self) -> None:
        with self._lock:
            if time.monotonic() < self._open_until:
                raise RuntimeError("CIRCUIT_OPEN")

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._failure_threshold:
                self._open_until = time.monotonic() + self._open_sec
                self._failures = 0
