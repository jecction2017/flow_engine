"""Elasticsearch Python client API compatibility (7.x vs 8.x)."""

from __future__ import annotations

from typing import Any, Callable


def call_client(method: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Invoke client method; retry with ``body=`` if ``document=`` is rejected (ES 7.x)."""
    try:
        return method(*args, **kwargs)
    except TypeError:
        if "document" in kwargs:
            body = kwargs.pop("document")
            kwargs["body"] = body
            return method(*args, **kwargs)
        raise
