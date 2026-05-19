"""Smoke tests for the order_fulfillment_canary example flow."""

from __future__ import annotations

from pathlib import Path

import pytest

from flow_engine.engine.loader import load_flow_from_yaml
from flow_engine.engine.models import FlowState, NodeState
from flow_engine.engine.orchestrator import FlowRuntime
from flow_engine.lookup.lookup_service import put_table
from flow_engine.stores.profile_store import profile_scope

FLOWS_DIR = Path(__file__).resolve().parents[1] / "examples"

_CANARY_DICTIONARY = {
    "business": {
        "order": {
            "tax_rate": 0.08,
            "free_shipping_threshold": 200.0,
            "standard_shipping_fee": 12.0,
            "vip_shipping_fee": 0.0,
        }
    }
}


def _flow() -> object:
    return load_flow_from_yaml(FLOWS_DIR / "order_fulfillment_canary.yaml")


_CUSTOMERS_SCHEMA = {
    "type": "object",
    "properties": {
        "customer_id": {"type": "string"},
        "name": {"type": "string"},
        "tier": {"type": "string"},
        "risk_score": {"type": "number"},
    },
}

_PRODUCTS_SCHEMA = {
    "type": "object",
    "properties": {
        "sku": {"type": "string"},
        "name": {"type": "string"},
        "stock": {"type": "number"},
    },
}


def _seed_lookup_tables() -> None:
    with profile_scope("default"):
        put_table(
            "customers",
            {
                "schema": _CUSTOMERS_SCHEMA,
                "rows": [
                    {
                        "customer_id": "CUST-100",
                        "name": "Alice",
                        "tier": "gold",
                        "risk_score": 10,
                    },
                    {
                        "customer_id": "CUST-200",
                        "name": "Bob",
                        "tier": "standard",
                        "risk_score": 55,
                    },
                ],
            },
        )
        put_table(
            "products",
            {
                "schema": _PRODUCTS_SCHEMA,
                "rows": [
                    {"sku": "SKU-A", "name": "Widget", "stock": 100},
                    {"sku": "SKU-B", "name": "Gadget", "stock": 5},
                ],
            },
        )


@pytest.mark.asyncio
async def test_order_fulfillment_canary_happy_path() -> None:
    _seed_lookup_tables()
    res = await FlowRuntime(_flow(), dictionary=_CANARY_DICTIONARY).run()
    assert res.state == FlowState.COMPLETED, res.message
    g = res.context.global_ns

    assert g["fulfillment"]["status"] == "FULFILLED"
    assert g["fulfillment"]["order_id"] == "ORD-DEMO-001"
    assert g["fulfillment"]["payment_ref"] == "PAY-ORD-DEMO-001"
    assert g["fulfillment"]["customer_tier"] == "gold"
    assert g["fulfillment"]["shipping_mode"] == "express"
    assert g["line_totals"]["subtotal"] == pytest.approx(320.0)
    assert len(g["line_totals"]["rows"]) == 2

    # 320 * 0.08 tax, 15% gold VIP discount, 0 express shipping
    assert g["pricing"]["tax"] == pytest.approx(25.6)
    assert g["pricing"]["discount"] == pytest.approx(48.0)
    assert g["pricing"]["grand_total"] == pytest.approx(594.6)

    assert res.node_state["standard_shipping"] == NodeState.SKIPPED
    assert res.node_state["vip_shipping"] == NodeState.SUCCESS
    assert res.node_state["recover_discount"] != NodeState.SUCCESS
    assert res.context.frames == []


@pytest.mark.asyncio
async def test_order_fulfillment_canary_rejects_high_risk() -> None:
    _seed_lookup_tables()
    flow = _flow()
    flow.initial_context = {
        "order": {
            "id": "ORD-REJECT-001",
            "customer_id": "CUST-200",
            "amount": 50.0,
            "vip": False,
            "apply_risky_discount": False,
            "line_items": [{"sku": "SKU-A", "qty": 1, "unit_price": 50.0}],
        },
        "enrichment": {"inventory": {}, "fraud": {}, "promo": {}},
        "line_totals": {"rows": [], "subtotal": 0},
        "pricing": {"tax": 0, "shipping": 0, "discount": 0, "grand_total": 0},
    }
    res = await FlowRuntime(flow, dictionary=_CANARY_DICTIONARY).run()
    assert res.state == FlowState.COMPLETED
    assert res.context.global_ns["fulfillment"]["status"] == "REJECTED"
    assert res.context.global_ns["gate"]["passed"] is False


@pytest.mark.asyncio
async def test_order_fulfillment_canary_recovers_discount() -> None:
    _seed_lookup_tables()
    flow = _flow()
    flow.initial_context = {
        "order": {
            "id": "ORD-RECOVER-001",
            "customer_id": "CUST-100",
            "amount": 100.0,
            "vip": True,
            "apply_risky_discount": True,
            "line_items": [{"sku": "SKU-A", "qty": 2, "unit_price": 50.0}],
        },
        "enrichment": {"inventory": {}, "fraud": {}, "promo": {}},
        "line_totals": {"rows": [], "subtotal": 0},
        "pricing": {"tax": 0, "shipping": 0, "discount": 0, "grand_total": 0},
    }
    res = await FlowRuntime(flow, dictionary=_CANARY_DICTIONARY).run()
    assert res.state == FlowState.COMPLETED
    g = res.context.global_ns
    assert g["pricing"]["recovered"] is True
    assert g["pricing"]["discount"] == pytest.approx(15.0)  # 100 * 0.15
    assert res.node_state["recover_discount"] == NodeState.SUCCESS
    assert res.node_state["apply_flash_discount"] != NodeState.SUCCESS
