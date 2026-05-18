"""Connector-layer errors and result envelopes."""

from __future__ import annotations

from typing import Any

from flow_engine.connectors.correlation import get_integration_correlation_id


class ConnectorError(Exception):
    """Base error for connector configuration or runtime failures."""

    def __init__(self, message: str, *, code: str = "CONNECTOR_ERROR") -> None:
        super().__init__(message)
        self.code = code


def ok_envelope(
    data: Any,
    *,
    instance: str,
    took_ms: float | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"instance": instance}
    if took_ms is not None:
        meta["took_ms"] = took_ms
    if extra_meta:
        meta.update(extra_meta)
    return {"ok": True, "data": data, "meta": meta}


def err_envelope(
    code: str,
    message: str,
    *,
    instance: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "correlation_id": get_integration_correlation_id(),
    }
    if details:
        error["details"] = details
    out: dict[str, Any] = {"ok": False, "error": error}
    if instance is not None:
        out["meta"] = {"instance": instance}
    return out
