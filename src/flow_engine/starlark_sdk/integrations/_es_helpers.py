"""Shared helpers for Elasticsearch Starlark builtins."""

from __future__ import annotations

from typing import Any

from flow_engine.connectors.errors import err_envelope
from flow_engine.connectors.registry import get_registry


def run_es_operation(instance: str, operation: str, **params: Any) -> dict[str, Any]:
    reg = get_registry()
    if not reg.elasticsearch_available:
        return err_envelope(
            "INTEGRATION_UNAVAILABLE",
            "elasticsearch package not installed; install flow-engine[integrations]",
            instance=instance,
        )
    try:
        handle = reg.get("elasticsearch", instance)
    except Exception as exc:  # noqa: BLE001
        from flow_engine.connectors.errors import ConnectorError

        if isinstance(exc, ConnectorError):
            return err_envelope(exc.code, str(exc), instance=instance)
        return err_envelope("INSTANCE_NOT_FOUND", str(exc), instance=instance)
    return handle.execute(operation, **params)
