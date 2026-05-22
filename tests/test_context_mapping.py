"""Shared context_mapping semantics."""

from flow_engine.runner.context_mapping import apply_context_mapping


def test_script_mode_returns_dict() -> None:
    row = {"id": "A1", "severity": "HIGH"}
    out = apply_context_mapping(
        row,
        {"mode": "script", "script": "payload"},
        run_mode="debug",
    )
    assert out == row


def test_rules_maps_to_dotted_paths() -> None:
    row = {"id": "A1", "severity": "HIGH"}
    out = apply_context_mapping(
        row,
        {
            "mode": "rules",
            "rules": [
                {"source": "id", "target": "alert.id"},
                {"source": "severity", "target": "alert.severity"},
            ],
        },
    )
    assert out["alert"]["id"] == "A1"
    assert out["alert"]["severity"] == "HIGH"


def test_build_trigger_context_spread_alert() -> None:
    from flow_engine.connectors.backends.kafka.messages import BusMessage
    from flow_engine.runner.subscription.message_parse import build_trigger_context
    from flow_engine.runner.subscription.spec import ParseSection, SubscriptionSection

    alert = {"id": "ALT-1", "indicators": []}
    import json

    msg = BusMessage(
        topic="alerts",
        partition=0,
        offset=1,
        key=None,
        value=json.dumps({"alert": alert}).encode(),
    )
    sub = SubscriptionSection(consumer_id="memory.alerts.default")
    ctx = build_trigger_context(
        msg,
        subscription=sub,
        parse=ParseSection(mapping={"mode": "spread"}),
        correlation_id="corr-1",
    )
    assert ctx["alert"] == alert
    assert ctx["event_meta"]["topic"] == "alerts"
    assert ctx["event_meta"]["correlation_id"] == "corr-1"
