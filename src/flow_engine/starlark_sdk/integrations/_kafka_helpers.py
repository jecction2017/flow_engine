"""Shared helpers for Kafka Starlark builtins."""

from __future__ import annotations

from typing import Any

from flow_engine.connectors.config_kafka import parse_consumer_id
from flow_engine.connectors.errors import ConnectorError, err_envelope
from flow_engine.connectors.registry import get_registry


def cap_kafka_timeout_ms(requested_ms: int, *, reserve_ms: int = 400) -> int:
    """Fit Kafka poll timeout inside active Starlark eval budget (debug / task scripts)."""
    from flow_engine.starlark_sdk.runtime import remaining_budget_ms

    remaining = remaining_budget_ms()
    if remaining is None:
        return max(100, requested_ms)
    cap = max(100, remaining - reserve_ms)
    return min(max(100, requested_ms), cap)


def _ensure_registry_bound() -> None:
    from flow_engine.stores.data_dict import active_dictionary, tree_copy
    from flow_engine.stores.profile_store import active_profile

    reg = get_registry()
    if reg.list_instances("kafka"):
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


def run_kafka_operation(
    consumer_id: str | None,
    producer_id: str | None,
    operation: str,
    **params: Any,
) -> dict[str, Any]:
    reg = get_registry()
    _ensure_registry_bound()
    if not reg.kafka_available:
        inst = consumer_id or producer_id or "kafka"
        return err_envelope(
            "INTEGRATION_UNAVAILABLE",
            reg.integration_unavailable_message("kafka"),
            instance=inst,
        )
    cluster_id: str | None = None
    try:
        if consumer_id:
            cluster_id, _, _ = parse_consumer_id(consumer_id)
            params["consumer_id"] = consumer_id
        elif producer_id:
            cluster_id, _, _ = parse_consumer_id(producer_id)
            params["producer_id"] = producer_id
        else:
            return err_envelope("INVALID_REQUEST", "consumer_id or producer_id required")
        handle = reg.get("kafka", cluster_id)
    except ConnectorError as exc:
        return err_envelope(exc.code, str(exc), instance=cluster_id or "kafka")
    except Exception as exc:  # noqa: BLE001
        return err_envelope("INSTANCE_NOT_FOUND", str(exc), instance=cluster_id or "kafka")
    return handle.execute(operation, **params)
