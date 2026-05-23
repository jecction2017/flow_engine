"""SubscriptionSpec validation."""

from __future__ import annotations

import pytest

from flow_engine.runner.subscription.spec import ingress_restart_delay_s, load_subscription_spec


def test_ingress_restart_delay_exponential() -> None:
    assert ingress_restart_delay_s(15, 1) == 15.0
    assert ingress_restart_delay_s(15, 2) == 30.0
    assert ingress_restart_delay_s(15, 3) == 60.0


def test_load_subscription_spec_minimal() -> None:
    spec = load_subscription_spec(
        {
            "subscription": {
                "consumer_id": "memory.alerts.default",
            },
        }
    )
    assert spec.subscription.consumer_id == "memory.alerts.default"
    assert spec.dispatch.max_in_flight == 8
    assert spec.ingress_policy.max_restarts == 3
    assert spec.ingress_policy.restart_backoff_s == 15


def test_script_transform_requires_script() -> None:
    with pytest.raises(ValueError, match="parse.script"):
        load_subscription_spec(
            {
                "subscription": {
                    "consumer_id": "memory.alerts.default",
                },
                "parse": {"codec": "json", "transform": "script"},
            }
        )


def test_consumer_id_required() -> None:
    with pytest.raises(ValueError):
        load_subscription_spec(
            {
                "subscription": {
                    "topic": "t",
                    "group_id": "g",
                },
            }
        )
