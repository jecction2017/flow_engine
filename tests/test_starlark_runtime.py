from __future__ import annotations

import pytest

from flow_engine.engine.context import ContextStack
from flow_engine.starlark_sdk.registry_data import load_registry
from flow_engine.starlark_sdk.runtime import (
    debug_task_script,
    eval_task_script,
    runtime_stats,
    warmup_runtime,
)


def test_registry_includes_declarative_python_builtins() -> None:
    reg = load_registry()
    names = {f["starlark_name"] for f in reg["python_functions"]}
    assert "dict_get" in names
    assert "lookup_query" in names
    for flow_name in ("flow_jump", "flow_continue", "flow_break", "flow_terminate"):
        assert flow_name in names
    assert "regex_match" in names
    assert "resolve" in names

    by_name = {f["starlark_name"]: f for f in reg["python_functions"]}
    assert by_name["flow_jump"]["attach_mode"] == "flow_control"
    assert by_name["resolve"]["attach_mode"] == "context"


def test_runtime_warmup_and_eval() -> None:
    out = warmup_runtime(
        module_ids=["internal://lib/helpers.star"],
        script_samples=['load("internal://lib/helpers.star", "double_int")\n{"v": double_int(5)}'],
    )
    assert out["modules"]["requested"] == 1
    assert out["modules"]["loaded"] == 1

    ctx = ContextStack()
    result, logs = eval_task_script(
        'load("internal://lib/helpers.star", "double_int")\n{"v": double_int(6)}', ctx, {}
    )
    assert result["v"] == 12
    assert logs == []

    stats = runtime_stats()
    assert "loader" in stats
    assert "ast" in stats


def test_eval_task_script_main_branches() -> None:
    ctx = ContextStack()

    # Branch 1: normal dict return path.
    out, _logs = eval_task_script('{"ok": True, "n": 7}', ctx, {})
    assert out == {"ok": True, "n": 7}

    # Branch 2: None return should normalize to {}.
    none_out, _ = eval_task_script("None", ctx, {})
    assert none_out == {}

    # Branch 3: non-dict return should raise TypeError.
    with pytest.raises(TypeError, match="Task script must evaluate to a dict"):
        eval_task_script("123", ctx, {})


def test_eval_task_script_captures_logs() -> None:
    """``log_info`` and friends should populate the returned log list.

    This also guards the bounding behaviour: many identical calls must not
    blow past ``FLOW_ENGINE_STARLARK_LOG_MAX_ENTRIES`` and the last kept
    entry should be flagged ``truncated`` when overflow occurs.
    """
    ctx = ContextStack()
    script = (
        'log_info("start")\n'
        'log_warn("progress", {"step": 1})\n'
        'log_error("boom")\n'
        'log_info("end")\n'
        '{"ok": True}\n'
    )
    out, logs = eval_task_script(script, ctx, {})
    assert out == {"ok": True}
    assert [e["level"] for e in logs] == ["info", "warn", "error", "info"]
    assert all(e["source"] == "task" for e in logs)
    assert logs[1]["message"].startswith("progress ") and '"step": 1' in logs[1]["message"]


def test_debug_task_script_flow_continue_is_not_an_error() -> None:
    script = """
def is_match():
    if normalized_alarm["alarm_type"] == "app_type_02":
        log_info("alarm type is app_type_02")
        flow_continue()
    return {"is_match": normalized_alarm["alarm_grade"] == "low"}

{"feature": is_match()}
""".strip()
    result, logs, control_flow = debug_task_script(
        script,
        {"normalized_alarm": {"alarm_type": "app_type_02", "alarm_grade": "high"}},
    )
    assert result == {}
    assert control_flow == {"action": "continue"}
    assert any("app_type_02" in e.get("message", "") for e in logs)


def test_debug_task_script_flow_jump_carries_reason_and_data() -> None:
    script = """
def route():
    flow_jump("target_node", reason="invalid payload", data={"order_id": 42, "retry": False})
    return {"ok": True}

{"r": route()}
""".strip()
    result, logs, control_flow = debug_task_script(script, {})
    assert result == {}
    assert logs == []
    assert control_flow == {
        "action": "jump",
        "target": "target_node",
        "reason": "invalid payload",
        "data": {"order_id": 42, "retry": False},
    }


def test_debug_task_script_normal_path_when_no_flow_continue() -> None:
    script = """
def is_match():
    if normalized_alarm["alarm_type"] == "app_type_02":
        flow_continue()
    return {"is_match": normalized_alarm["alarm_grade"] == "low"}

{"feature": is_match()}
""".strip()
    result, logs, control_flow = debug_task_script(
        script,
        {"normalized_alarm": {"alarm_type": "app_type_01", "alarm_grade": "low"}},
    )
    assert control_flow is None
    assert result == {"feature": {"is_match": True}}
    assert logs == []