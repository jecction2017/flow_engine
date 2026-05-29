"""Shared helpers for HTTP Starlark builtins."""

from __future__ import annotations

from typing import Any

from flow_engine.connectors.registry import get_registry


def _ensure_registry_bound() -> None:
    """Re-bind from active dictionary (or profile tree) if handles are missing."""
    from flow_engine.stores.data_dict import active_dictionary, tree_copy
    from flow_engine.stores.profile_store import active_profile

    reg = get_registry()
    if reg.list_instances("http"):
        return
    tree = active_dictionary()
    profile: str | None = None
    try:
        profile = active_profile()
    except Exception:  # noqa: BLE001
        pass
    if tree is None:
        tree = tree_copy(profile)
    reg.bind(tree, profile=profile)


def run_http_operation(instance: str, operation: str, **params: Any) -> dict[str, Any]:
    reg = get_registry()
    _ensure_registry_bound()
    if not reg.http_available:
        return {
            "success": False,
            "data": None,
            "error_msg": reg.integration_unavailable_message("http"),
            "error_code": "INTEGRATION_UNAVAILABLE",
            "status_code": None,
            "cost_ms": 0.0,
            "meta": {"instance": instance},
        }
    try:
        handle = reg.get("http", instance)
    except Exception as exc:  # noqa: BLE001
        from flow_engine.connectors.errors import ConnectorError

        if isinstance(exc, ConnectorError):
            return {
                "success": False,
                "data": None,
                "error_msg": str(exc),
                "error_code": exc.code,
                "status_code": None,
                "cost_ms": 0.0,
                "meta": {"instance": instance},
            }
        return {
            "success": False,
            "data": None,
            "error_msg": str(exc),
            "error_code": "INSTANCE_NOT_FOUND",
            "status_code": None,
            "cost_ms": 0.0,
            "meta": {"instance": instance},
        }
    return handle.execute(operation, **params)
