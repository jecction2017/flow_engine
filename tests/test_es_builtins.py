"""Tests for Elasticsearch Starlark builtins and capability policy."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from flow_engine.connectors.registry import ConnectorRegistry, reset_registry_for_tests
from flow_engine.runner.mode_context import RunMode, run_mode_scope
from flow_engine.starlark_sdk.builtin_registry import builtin_map
from flow_engine.starlark_sdk.integrations import elasticsearch_builtins  # noqa: F401
from flow_engine.starlark_sdk.integrations import business  # noqa: F401
from flow_engine.starlark_sdk.registry_data import load_registry
from flow_engine.stores.data_dict import dictionary_scope


def test_registry_lists_es_builtins() -> None:
    reg = load_registry()
    names = {f["starlark_name"] for f in reg["python_functions"]}
    assert "es_search" in names
    assert "es_mget" in names
    assert "es_count" in names
    assert "es_scroll" in names
    assert "user_create" in names


def test_es_search_with_mock_client() -> None:
    reset_registry_for_tests()
    reg = ConnectorRegistry()
    fake_client = MagicMock()
    fake_client.search.return_value = {"hits": {"hits": [{"_id": "1"}]}}

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
            reg.bind(dictionary)
            fn = builtin_map()["es_search"]
            out = fn("main", "logs-*", None, None, 5)
        assert out["ok"] is True
        assert out["data"]["hits"]["hits"]
    finally:
        es_backend.create_client = original_create
        reg.close_all()
        reset_registry_for_tests()


def test_debug_suppresses_es_search() -> None:
    from flow_engine.engine.context import ContextStack
    from flow_engine.starlark_sdk.runtime import eval_task_script

    with run_mode_scope(RunMode.DEBUG):
        result, _ = eval_task_script(
            'es_search("main", "idx")',
            ContextStack(),
            {},
        )
    assert isinstance(result, dict)
    assert result.get("_suppressed") is True


def test_debug_suppresses_user_create() -> None:
    from flow_engine.engine.context import ContextStack
    from flow_engine.starlark_sdk.runtime import eval_task_script

    with run_mode_scope(RunMode.DEBUG):
        result, _ = eval_task_script(
            'user_create("main", {"user_id": "u1", "name": "n"})',
            ContextStack(),
            {},
        )
    assert isinstance(result, dict)
    assert result.get("_suppressed") is True


def test_operations_reject_script() -> None:
    from flow_engine.connectors.backends.elasticsearch import operations as es_ops
    from flow_engine.connectors.errors import ConnectorError

    client = MagicMock()
    with pytest.raises(ConnectorError) as exc_info:
        es_ops.search(
            client,
            index="i",
            body={"script": {"source": "1"}},
            query=None,
            size=10,
            allowed_patterns=None,
        )
    assert exc_info.value.code == "SCRIPT_FORBIDDEN"
