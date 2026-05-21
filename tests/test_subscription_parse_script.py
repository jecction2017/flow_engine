"""Subscription parse.script (Starlark transform)."""

from __future__ import annotations

import json

from flow_engine.connectors.backends.kafka.messages import BusMessage
from flow_engine.runner.subscription.message_parse import build_trigger_context
from flow_engine.runner.subscription.spec import ParseSection, SubscriptionSection


def test_build_trigger_context_script_extracts_alert() -> None:
    alert = {"id": "ALT-2", "severity": "HIGH"}
    msg = BusMessage(
        topic="alerts",
        partition=1,
        offset=42,
        key=None,
        value=json.dumps({"alert": alert, "extra": "x"}).encode(),
    )
    sub = SubscriptionSection(consumer_id="memory.alerts.default")
    script = (
        'payload\n\n'
        '{"alert": payload["alert"] if "alert" in payload else payload}'
    )
    ctx = build_trigger_context(
        msg,
        subscription=sub,
        parse=ParseSection(transform="script", script=script),
        correlation_id="corr-script",
        run_mode="production",
        capability_policy=[],
    )
    assert ctx["alert"] == alert
    assert ctx["event_meta"]["offset"] == 42
    assert ctx["event_meta"]["correlation_id"] == "corr-script"
