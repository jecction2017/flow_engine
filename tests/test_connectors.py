"""Tests for connector core, protection, and registry."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from flow_engine.connectors.backends.elasticsearch.auth import build_client_auth
from flow_engine.connectors.config import (
    AuthSpec,
    ElasticsearchConfig,
    ProtectionSpec,
)
from flow_engine.connectors.protection.circuit_breaker import CircuitBreaker
from flow_engine.connectors.protection.pipeline import ProtectionPipeline, RequestContext
from flow_engine.connectors.protection.rate_limit import RateLimiter
from flow_engine.connectors.registry import ConnectorRegistry, reset_registry_for_tests
from flow_engine.stores.data_dict import dictionary_scope


def test_elasticsearch_config_parse() -> None:
    cfg = ElasticsearchConfig.model_validate(
        {
            "defaults": {"protection": {"max_rps": 10}},
            "instances": {"main": {"hosts": ["http://localhost:9200"]}},
        }
    )
    assert cfg.instances["main"].hosts == ["http://localhost:9200"]
    assert cfg.defaults.protection.max_rps == 10


def test_auth_basic() -> None:
    kw = build_client_auth(AuthSpec(type="basic", username="u", password="p"))
    assert kw["basic_auth"] == ("u", "p")


def test_circuit_breaker_opens() -> None:
    cb = CircuitBreaker(failure_threshold=2, open_sec=60.0)
    cb.before_call()
    cb.record_failure()
    cb.before_call()
    cb.record_failure()
    with pytest.raises(RuntimeError, match="CIRCUIT_OPEN"):
        cb.before_call()


def test_rate_limiter_blocks_burst() -> None:
    rl = RateLimiter(max_rps=1.0)
    rl.acquire()
    with pytest.raises(RuntimeError, match="CONNECTOR_RATE_LIMIT"):
        rl.acquire()


def test_registry_bind_instances() -> None:
    reset_registry_for_tests()
    reg = ConnectorRegistry()
    fake_client = MagicMock()
    fake_client.search.return_value = {"hits": {"hits": []}}

    from flow_engine.connectors.backends.elasticsearch import backend as es_backend

    original_create = es_backend.create_client

    def _fake_create(spec, *, request_timeout_sec: float):  # noqa: ARG001
        return fake_client

    es_backend.create_client = _fake_create
    try:
        dictionary = {
            "middleware": {
                "elasticsearch": {
                    "instances": {
                        "main": {"hosts": ["http://localhost:9200"], "auth": {"type": "none"}},
                    }
                }
            }
        }
        with dictionary_scope(dictionary):
            handle = reg.get("elasticsearch", "main")
            result = handle.execute("search", index="logs-*", body=None, query=None, size=10)
        assert result["ok"] is True
        fake_client.search.assert_called_once()
    finally:
        es_backend.create_client = original_create
        reg.close_all()
        reset_registry_for_tests()


def test_bind_retries_when_hash_matches_but_handles_empty() -> None:
    reset_registry_for_tests()
    reg = ConnectorRegistry()
    dictionary = {
        "middleware": {
            "elasticsearch": {
                "instances": {
                    "main": {"hosts": ["http://localhost:9200"], "auth": {"type": "none"}},
                }
            }
        }
    }
    reg.bind(dictionary, profile="default")
    reg._handles.clear()  # noqa: SLF001 simulate stale empty bind
    with dictionary_scope(dictionary):
        reg.bind(dictionary, profile="default")
        assert reg.list_instances("elasticsearch") == ["main"]
    reg.close_all()
    reset_registry_for_tests()


def test_circuit_breaker_skips_connector_error_failures() -> None:
    spec = ProtectionSpec(circuit_failure_threshold=2, circuit_open_sec=60.0)
    pipe = ProtectionPipeline(spec, request_timeout_sec=5.0)
    ctx = RequestContext(instance_id="x", operation="search")
    from flow_engine.connectors.errors import ConnectorError

    for _ in range(3):

        def fail_validation() -> None:
            raise ConnectorError("bad index", code="INVALID_INDEX")

        with pytest.raises(ConnectorError):
            pipe.run(ctx, fail_validation)
    # Should not open circuit for validation-only failures.
    pipe.run(ctx, lambda: "ok")


def test_protection_pipeline_timeout() -> None:
    spec = ProtectionSpec(max_in_flight=2, max_rps=1000)
    pipe = ProtectionPipeline(spec, request_timeout_sec=0.001)
    ctx = RequestContext(instance_id="x", operation="search")

    def slow() -> str:
        import time

        time.sleep(0.05)
        return "ok"

    with pytest.raises(TimeoutError):
        pipe.run(ctx, slow)
