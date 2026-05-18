"""Correlation ID for integration calls within a flow run."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator
from uuid import uuid4

_correlation_id: ContextVar[str | None] = ContextVar("flow_engine_integration_correlation_id", default=None)


def get_integration_correlation_id() -> str:
    cur = _correlation_id.get()
    if cur:
        return cur
    return "unknown"


@contextmanager
def integration_correlation_scope(correlation_id: str | None = None) -> Iterator[None]:
    token = _correlation_id.set(correlation_id or str(uuid4()))
    try:
        yield
    finally:
        _correlation_id.reset(token)
