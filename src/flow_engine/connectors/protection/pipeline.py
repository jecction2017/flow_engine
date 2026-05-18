"""Composable protection pipeline for sync connector calls."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, TypeVar

from flow_engine.connectors.config import ProtectionSpec
from flow_engine.connectors.protection.circuit_breaker import CircuitBreaker
from flow_engine.connectors.protection.concurrency import ConcurrencyGate
from flow_engine.connectors.protection.rate_limit import RateLimiter

T = TypeVar("T")


@dataclass
class RequestContext:
    instance_id: str
    operation: str
    started_at: float = field(default_factory=time.monotonic)


class ProtectionPipeline:
    def __init__(self, spec: ProtectionSpec, *, request_timeout_sec: float) -> None:
        self.spec = spec
        self.request_timeout_sec = request_timeout_sec
        self._concurrency = ConcurrencyGate(spec.max_in_flight)
        self._rate = RateLimiter(spec.max_rps)
        self._circuit = CircuitBreaker(spec.circuit_failure_threshold, spec.circuit_open_sec)

    @contextmanager
    def call(self, ctx: RequestContext) -> Iterator[None]:
        self._circuit.before_call()
        try:
            self._rate.acquire()
        except RuntimeError as exc:
            if str(exc) == "CONNECTOR_RATE_LIMIT":
                raise
            raise
        self._concurrency.acquire()
        try:
            yield
            self._circuit.record_success()
        except RuntimeError as exc:
            if str(exc) in {"CONNECTOR_CONCURRENCY_LIMIT", "CONNECTOR_RATE_LIMIT", "CIRCUIT_OPEN"}:
                raise
            self._circuit.record_failure()
            raise
        except Exception as exc:
            # Validation / policy errors must not trip the cluster circuit breaker.
            from flow_engine.connectors.errors import ConnectorError

            if not isinstance(exc, ConnectorError):
                self._circuit.record_failure()
            raise
        finally:
            self._concurrency.release()

    def run(self, ctx: RequestContext, fn: Callable[[], T]) -> T:
        deadline = time.monotonic() + self.request_timeout_sec
        with self.call(ctx):
            result = fn()
            if time.monotonic() > deadline:
                raise TimeoutError(f"connector timeout after {self.request_timeout_sec}s")
            return result

    def cap_size(self, size: int | None) -> int:
        if size is None:
            return self.spec.max_result_docs
        return min(max(1, size), self.spec.max_result_docs)

    def cap_scroll_pages(self, pages: int | None) -> int:
        if pages is None:
            return self.spec.max_scroll_pages
        return min(max(1, pages), self.spec.max_scroll_pages)
