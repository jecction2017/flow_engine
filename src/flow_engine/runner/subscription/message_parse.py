"""Decode bus messages and map to trigger_context via user-defined context_mapping."""

from __future__ import annotations

import json
from typing import Any, Literal

from flow_engine.runner.context_mapping import apply_context_mapping
from flow_engine.connectors.backends.kafka.messages import BusMessage
from flow_engine.runner.subscription.spec import ParseSection, SubscriptionSection

Codec = Literal["json"]


def decode_message_payload(msg: BusMessage, codec: Codec) -> dict[str, Any]:
    """Turn raw message bytes into a mapping record for ``apply_context_mapping``."""
    if codec != "json":
        raise ValueError(f"unsupported message codec: {codec!r}")
    try:
        payload = json.loads(msg.value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"message value is not valid UTF-8 JSON: {e}") from e
    if isinstance(payload, dict):
        return payload
    return {"payload": payload}


def build_event_meta(
    msg: BusMessage,
    subscription: SubscriptionSection,
    correlation_id: str,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    cluster_id = subscription.consumer_id.split(".", 1)[0]
    return {
        "consumer_id": subscription.consumer_id,
        "cluster_id": cluster_id,
        "topic": msg.topic,
        "partition": msg.partition,
        "offset": msg.offset,
        "message_id": f"{msg.topic}:{msg.partition}:{msg.offset}",
        "correlation_id": correlation_id,
        "ingest_ts": datetime.now(timezone.utc).isoformat(),
    }


def build_trigger_context(
    msg: BusMessage,
    *,
    subscription: SubscriptionSection,
    parse: ParseSection,
    correlation_id: str,
    run_mode: str | None = None,
    capability_policy: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """User transform (mapping or script) + platform ``event_meta``."""
    codec = parse.codec or "json"
    record = decode_message_payload(msg, codec)
    if parse.transform == "script":
        from flow_engine.starlark_sdk.runtime import eval_transform_script

        user_ctx = eval_transform_script(
            str(parse.script or ""),
            {"payload": record},
            run_mode=run_mode,
            capability_policy=capability_policy,
        )
    else:
        user_ctx = apply_context_mapping(record, parse.mapping)
    if not isinstance(user_ctx, dict):
        raise TypeError("parse transform must produce a dict")
    return {
        **user_ctx,
        "event_meta": build_event_meta(msg, subscription, correlation_id),
    }
