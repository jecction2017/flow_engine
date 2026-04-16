from __future__ import annotations

from flow_engine.context import ContextStack
from flow_engine.starlark_sdk.registry_data import load_registry
from flow_engine.starlark_sdk.runtime import eval_task_script, runtime_stats, warmup_runtime


def test_registry_includes_declarative_python_builtins() -> None:
    reg = load_registry()
    names = {f["starlark_name"] for f in reg["python_functions"]}
    assert "dict_get" in names
    assert "lookup_query" in names


def test_runtime_warmup_and_eval() -> None:
    out = warmup_runtime(
        module_ids=["internal://lib/helpers.star"],
        script_samples=['load("internal://lib/helpers.star", "double_int")\n{"v": double_int(5)}'],
    )
    assert out["modules"]["requested"] == 1
    assert out["modules"]["loaded"] == 1

    ctx = ContextStack()
    result = eval_task_script('load("internal://lib/helpers.star", "double_int")\n{"v": double_int(6)}', ctx, {})
    assert result["v"] == 12

    stats = runtime_stats()
    assert "loader" in stats
    assert "ast" in stats
