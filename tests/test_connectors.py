"""Tests for connector core, protection, and registry."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from flow_engine.connectors.backends.elasticsearch.auth import build_client_auth
from flow_engine.connectors.config import (
    AuthSpec,
    ElasticsearchConfig,
    ProtectionSpec,
)
from flow_engine.connectors.config_http import parse_http_config
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


def test_http_config_parse_and_priority_fields() -> None:
    cfg = parse_http_config(
        {
            "defaults": {"protection": {"max_rps": 5}},
            "instances": {
                "main": {
                    "base": {"request_timeout_sec": 8.0, "retries": 1},
                    "services": {
                        "user": {
                            "base_url": "https://api.example.com",
                            "common_headers": {"X-Service": "user"},
                            "auth_provider": "iam_default",
                            "endpoints": {
                                "get_user": {
                                    "path": "/v1/users/{user_id}",
                                    "method": "get",
                                    "extra_headers": {"X-Endpoint": "get_user"},
                                }
                            },
                        }
                    },
                    "auth_providers": {
                        "iam_default": {
                            "type": "iam",
                            "token_url": "https://iam.example.com/oauth/token",
                            "client_id": "cid",
                            "client_secret": "csecret",
                        }
                    },
                }
            },
        }
    )
    assert cfg is not None
    assert cfg.defaults.protection.max_rps == 5
    inst = cfg.instances["main"]
    assert inst.base.request_timeout_sec == 8.0
    assert inst.base.retries == 1
    assert inst.services["user"].endpoints["get_user"].method == "GET"


def test_auth_basic() -> None:
    kw = build_client_auth(AuthSpec(type="basic", username="u", password="p"))
    assert kw["http_auth"] == ("u", "p")


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


class _FakeResponse:
    def __init__(self, *, status: int, body: str, content_type: str = "application/json") -> None:
        self.status = status
        self._body = body.encode("utf-8")
        self.headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None


def test_http_registry_bind_and_call_success(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_registry_for_tests()
    reg = ConnectorRegistry()
    captured: dict[str, str] = {}

    def _fake_urlopen(req, timeout=0, context=None):  # noqa: ANN001, ARG001
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["header_x"] = dict(req.header_items()).get("X-req", "")
        body = json.dumps({"ok": True, "uid": "42"})
        return _FakeResponse(status=200, body=body)

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    dictionary = {
        "middleware": {
            "http": {
                "instances": {
                    "main": {
                        "base": {"request_timeout_sec": 5.0},
                        "services": {
                            "user_service": {
                                "base_url": "https://api.example.com",
                                "endpoints": {
                                    "get_user": {
                                        "path": "/v1/users/{user_id}",
                                        "method": "GET",
                                        "query_defaults": {"include": "profile"},
                                    }
                                },
                            }
                        },
                    }
                }
            }
        }
    }
    with dictionary_scope(dictionary):
        handle = reg.get("http", "main")
        out = handle.execute(
            "call",
            service_name="user_service",
            endpoint_name="get_user",
            path_params={"user_id": "42"},
            header_params={"X-Req": "1"},
            query_params={"verbose": "true"},
        )
    reg.close_all()
    reset_registry_for_tests()
    assert out["success"] is True
    assert out["data"]["uid"] == "42"
    assert captured["method"] == "GET"
    assert "include=profile" in captured["url"]
    assert "verbose=true" in captured["url"]
    assert captured["header_x"] == "1"


def test_http_iam_auth_uses_token_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_registry_for_tests()
    reg = ConnectorRegistry()
    token_calls = {"n": 0}
    api_auth_headers: list[str] = []

    def _fake_urlopen(req, timeout=0, context=None):  # noqa: ANN001, ARG001
        if "iam.example.com" in req.full_url:
            token_calls["n"] += 1
            return _FakeResponse(status=200, body=json.dumps({"access_token": "token-1", "expires_in": 3600}))
        api_auth_headers.append(req.headers.get("Authorization", ""))
        return _FakeResponse(status=200, body=json.dumps({"ok": True}))

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    dictionary = {
        "middleware": {
            "http": {
                "instances": {
                    "main": {
                        "services": {
                            "svc": {
                                "base_url": "https://api.example.com",
                                "auth_provider": "iam_default",
                                "endpoints": {"ping": {"path": "/ping", "method": "GET"}},
                            }
                        },
                        "auth_providers": {
                            "iam_default": {
                                "type": "iam",
                                "token_url": "https://iam.example.com/oauth/token",
                                "client_id": "cid",
                                "client_secret": "sec",
                            }
                        },
                    }
                }
            }
        }
    }
    with dictionary_scope(dictionary):
        handle = reg.get("http", "main")
        out1 = handle.execute("call", service_name="svc", endpoint_name="ping")
        out2 = handle.execute("call", service_name="svc", endpoint_name="ping")
    reg.close_all()
    reset_registry_for_tests()
    assert out1["success"] is True and out2["success"] is True
    assert token_calls["n"] == 1
    assert api_auth_headers == ["Bearer token-1", "Bearer token-1"]


def test_http_auth_provider_not_implemented(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_registry_for_tests()
    reg = ConnectorRegistry()

    def _fake_urlopen(req, timeout=0, context=None):  # noqa: ANN001, ARG001
        return _FakeResponse(status=200, body=json.dumps({"ok": True}))

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    dictionary = {
        "middleware": {
            "http": {
                "instances": {
                    "main": {
                        "services": {
                            "svc": {
                                "base_url": "https://api.example.com",
                                "auth_provider": "soa_auth",
                                "endpoints": {"ping": {"path": "/ping", "method": "GET"}},
                            }
                        },
                        "auth_providers": {"soa_auth": {"type": "soa"}},
                    }
                }
            }
        }
    }
    with dictionary_scope(dictionary):
        handle = reg.get("http", "main")
        out = handle.execute("call", service_name="svc", endpoint_name="ping")
    reg.close_all()
    reset_registry_for_tests()
    assert out["success"] is False
    assert out["error_code"] == "AUTH_NOT_IMPLEMENTED"
