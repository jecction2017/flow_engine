"""SubscriptionSpec validation."""

from __future__ import annotations

import pytest

from flow_engine.runner.subscription.spec import load_subscription_spec


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
