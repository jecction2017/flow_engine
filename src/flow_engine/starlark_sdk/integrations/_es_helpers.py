"""Shared helpers for Elasticsearch Starlark builtins."""

from __future__ import annotations

from typing import Any

from flow_engine.connectors.errors import err_envelope
from flow_engine.connectors.registry import get_registry


def _ensure_registry_bound() -> None:
    """Re-bind from active dictionary (or profile tree) if handles are missing."""
    from flow_engine.stores.data_dict import active_dictionary, tree_copy
    from flow_engine.stores.profile_store import active_profile

    reg = get_registry()
    if reg.list_instances("elasticsearch"):
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


def run_es_operation(instance: str, operation: str, **params: Any) -> dict[str, Any]:
    reg = get_registry()
    _ensure_registry_bound()
    if not reg.elasticsearch_available:
        return err_envelope(
            "INTEGRATION_UNAVAILABLE",
            reg.integration_unavailable_message(),
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
