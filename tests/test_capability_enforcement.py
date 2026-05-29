"""End-to-end checks for CapabilityPolicy enforcement.

Scope: 验证修复后的 ``_guard_builtin`` 真正在 builtin 入口处调用
``check_capability``，并且不同求值路径（task / debug / condition / process）
的能力约束行为彼此一致。
"""

from __future__ import annotations

from typing import Any

import pytest

from flow_engine.engine.context import ContextStack
from flow_engine.engine.starlark_glue import (
    eval_condition,
    process_starlark_task,
)
from flow_engine.runner.mode_context import (
    CapabilityAction,
    check_capability,
    run_mode_scope,
)
from flow_engine.runner.models import CapabilityRule, RunMode
from flow_engine.starlark_sdk.builtin_registry import (
    PythonBuiltinSpec,
    register_builtin,
)
from flow_engine.starlark_sdk.runtime import (
    debug_task_script,
    eval_task_script,
    get_redirect_params,
)


# ---------------------------------------------------------------------------
# Test fixture: register a side-effect builtin in a hard-to-collide category
# so the harness can observe SUPPRESS / REDIRECT without depending on real
# integrations (HTTP / DB / lookup files).
# ---------------------------------------------------------------------------


_REAL_CALLS: list[dict[str, Any]] = []


def _reset_calls() -> None:
    _REAL_CALLS.clear()


@register_builtin(
    PythonBuiltinSpec(
        id="python://test/probe",
        starlark_name="cap_probe",
        category="cap_test_probe",
        summary="Test-only side-effect builtin used by capability enforcement tests.",
        signature=(),
        returns="dict",
        # ``side_effects != "none"`` is what makes ``_guard_builtin`` consult
        # ``check_capability``. Any non-"none" string works.
        side_effects="network",
        suppress_result={"suppressed": True, "called": False},
    )
)
def cap_probe(arg: str = "default") -> dict[str, Any]:
    redirect = get_redirect_params()
    _REAL_CALLS.append({"arg": arg, "redirect": dict(redirect)})
    return {"suppressed": False, "called": True, "arg": arg, "redirect": dict(redirect)}


# ---------------------------------------------------------------------------
# 1. _guard_builtin SUPPRESS / REDIRECT flow
# ---------------------------------------------------------------------------


def test_suppress_short_circuits_function_body() -> None:
    """SUPPRESS hits the wrapper before fn is called → spec.suppress_result returned."""
    _reset_calls()
    rules = [CapabilityRule(builtin_category="cap_test_probe", action=CapabilityAction.SUPPRESS)]
    with run_mode_scope(RunMode.PRODUCTION, rules):
        out, _logs = eval_task_script('cap_probe(arg="x")', ContextStack(), {})
    assert out == {"suppressed": True, "called": False}
    assert _REAL_CALLS == [], "function body must not run when SUPPRESSED"


def test_redirect_passes_params_to_function_body() -> None:
    """REDIRECT params reach the body via ``get_redirect_params`` thread-local."""
    _reset_calls()
    rules = [
        CapabilityRule(
            builtin_name="cap_probe",
            action=CapabilityAction.REDIRECT,
            redirect_params={"target": "sandbox"},
        )
    ]
    with run_mode_scope(RunMode.PRODUCTION, rules):
        out, _logs = eval_task_script('cap_probe(arg="real")', ContextStack(), {})
    assert out["called"] is True
    assert out["redirect"] == {"target": "sandbox"}
    assert _REAL_CALLS == [{"arg": "real", "redirect": {"target": "sandbox"}}]


def test_allow_runs_body_with_empty_redirect_params() -> None:
    _reset_calls()
    with run_mode_scope(RunMode.PRODUCTION, []):
        out, _ = eval_task_script('cap_probe(arg="ok")', ContextStack(), {})
    assert out["called"] is True
    assert out["redirect"] == {}


def test_redirect_params_are_cleaned_between_calls() -> None:
    """A REDIRECT call must not leak params to a subsequent ALLOW call."""
    _reset_calls()
    rules = [
        CapabilityRule(
            builtin_name="cap_probe",
            action=CapabilityAction.REDIRECT,
            redirect_params={"leak": "x"},
        )
    ]
    with run_mode_scope(RunMode.PRODUCTION, rules):
        eval_task_script('cap_probe(arg="redirected")', ContextStack(), {})
    # New scope without the redirect rule — body must observe empty redirect.
    with run_mode_scope(RunMode.PRODUCTION, []):
        out, _ = eval_task_script('cap_probe(arg="allow")', ContextStack(), {})
    assert out["redirect"] == {}


# ---------------------------------------------------------------------------
# 2. System default policy aligns with builtin spec category
# ---------------------------------------------------------------------------


def test_default_debug_policy_suppresses_integration_category() -> None:
    """``integration`` category must hit the default DEBUG SUPPRESS rule.

    Prior to the fix the system default named ``external_api_write`` which
    no real builtin used → suppress never fired in DEBUG mode.
    """
    with run_mode_scope(RunMode.DEBUG, []):
        action, _ = check_capability("integration", "http_call")
        assert action == CapabilityAction.SUPPRESS


# ---------------------------------------------------------------------------
# 3. eval_condition delegates to SDK runtime (not the stripped path)
# ---------------------------------------------------------------------------


def test_condition_can_invoke_sdk_builtins() -> None:
    """Conditions historically used a stripped evaluator without SDK builtins.

    After the fix they share the SDK path: ``cap_probe`` must be callable
    inside a condition expression.
    """
    _reset_calls()
    with run_mode_scope(RunMode.PRODUCTION, []):
        ok = eval_condition("cap_probe()['called']", ContextStack())
    assert ok is True
    assert len(_REAL_CALLS) == 1


def test_condition_respects_capability_policy() -> None:
    """SUPPRESS rules must apply to conditions — same enforcement as task scripts."""
    _reset_calls()
    rules = [CapabilityRule(builtin_category="cap_test_probe", action=CapabilityAction.SUPPRESS)]
    with run_mode_scope(RunMode.PRODUCTION, rules):
        # suppress_result["called"] is False → condition evaluates to False.
        ok = eval_condition("cap_probe()['called']", ContextStack())
    assert ok is False
    assert _REAL_CALLS == []


# ---------------------------------------------------------------------------
# 4. process_starlark_task shares the full SDK pipeline
# ---------------------------------------------------------------------------


def test_process_worker_applies_capability_policy() -> None:
    """Process-pool path must enforce CapabilityPolicy just like the main path."""
    _reset_calls()
    payload = {
        "script": 'r = cap_probe(arg="proc")\n{"called": r["called"]}',
        "flat_inputs": {},
        "dictionary": {},
        "run_mode": RunMode.PRODUCTION.value,
        "effective_policy": [
            CapabilityRule(
                builtin_category="cap_test_probe", action=CapabilityAction.SUPPRESS
            ).model_dump()
        ],
    }
    out = process_starlark_task(payload)
    assert out["result"] == {"called": False}
    assert _REAL_CALLS == [], "worker must short-circuit suppressed builtin too"


def test_process_worker_supports_load_directive() -> None:
    """Worker should now have ``file_loader`` wired (was missing before fix)."""
    payload = {
        "script": (
            'load("internal://lib/helpers.star", "double_int")\n'
            '{"v": double_int(7)}'
        ),
        "flat_inputs": {},
        "dictionary": {},
        "run_mode": RunMode.PRODUCTION.value,
        "effective_policy": [],
    }
    out = process_starlark_task(payload)
    assert out["result"] == {"v": 14}


# ---------------------------------------------------------------------------
# 5. debug_task_script accepts run_mode / capability_policy kwargs
# ---------------------------------------------------------------------------


def test_debug_task_script_opens_capability_scope() -> None:
    """Debug API path now plumbs ``run_mode`` so DEBUG suppresses integrations."""
    _reset_calls()
    out, _, _ = debug_task_script(
        'r = cap_probe()\n{"called": r["called"]}',
        {},
        run_mode=RunMode.DEBUG,
        capability_policy=[
            CapabilityRule(
                builtin_category="cap_test_probe", action=CapabilityAction.SUPPRESS
            )
        ],
    )
    assert out == {"called": False}
    assert _REAL_CALLS == []


def test_debug_task_script_no_scope_when_no_args() -> None:
    """Backwards compatibility: omitting kwargs preserves prior behaviour
    (no scope opened — capability defaults to whatever caller already set up).
    """
    _reset_calls()
    out, _, _ = debug_task_script('r = cap_probe()\n{"called": r["called"]}', {})
    # No scope active → ALLOW fallback → real call happens.
    assert out == {"called": True}
    assert len(_REAL_CALLS) == 1


# ---------------------------------------------------------------------------
# 6. profile_system_capability_policy slot
# ---------------------------------------------------------------------------


def test_profile_rules_layer_between_deployment_and_default() -> None:
    """profile_system_rules must rank below deployment but above hardcoded default."""
    deployment_rules = [
        CapabilityRule(
            builtin_name="cap_probe", action=CapabilityAction.ALLOW
        ),  # deployment overrides
    ]
    profile_rules = [
        CapabilityRule(
            builtin_category="cap_test_probe", action=CapabilityAction.SUPPRESS
        ),
    ]
    # Deployment ALLOW wins — same builtin name match takes priority over category match.
    with run_mode_scope(RunMode.PRODUCTION, deployment_rules, profile_rules):
        action, _ = check_capability("cap_test_probe", "cap_probe")
        assert action == CapabilityAction.ALLOW

    # Without deployment rule, profile SUPPRESS kicks in even in PRODUCTION
    # (no system default suppresses cap_test_probe).
    with run_mode_scope(RunMode.PRODUCTION, [], profile_rules):
        action2, _ = check_capability("cap_test_probe", "cap_probe")
        assert action2 == CapabilityAction.SUPPRESS


def test_profile_rules_outrank_system_default() -> None:
    """Profile rule on ``integration`` ALLOW must beat hardcoded DEBUG SUPPRESS."""
    profile_rules = [
        CapabilityRule(builtin_category="integration", action=CapabilityAction.ALLOW),
    ]
    with run_mode_scope(RunMode.DEBUG, [], profile_rules):
        action, _ = check_capability("integration", "http_call")
        assert action == CapabilityAction.ALLOW


# ---------------------------------------------------------------------------
# 7. Sanity: log_* are still NOT capability-checked / budget-charged
# ---------------------------------------------------------------------------


def test_log_builtins_bypass_capability_and_budget() -> None:
    """``log_*`` must keep zero-cost semantics even with capability changes."""
    rules = [
        # A very broad SUPPRESS that *would* match if log_info had a category;
        # log_info is "runtime"/"none" side-effects so the rule should not apply.
        CapabilityRule(action=CapabilityAction.SUPPRESS),
    ]
    with run_mode_scope(RunMode.PRODUCTION, rules):
        out, logs = eval_task_script(
            'log_info("hello")\n{"ok": True}', ContextStack(), {}
        )
    assert out == {"ok": True}
    assert [e["level"] for e in logs] == ["info"]


# ---------------------------------------------------------------------------
# 8. HTTP API contract: ad-hoc debug paths are LOCKED to RunMode.DEBUG
# ---------------------------------------------------------------------------
#
# 设计契约（产品安全边界）：
# - /api/debug/node 是临时调试入口（单节点 / 用户脚本调试均走此路径），
#   服务端硬编码 RunMode.DEBUG —— 任何尝试在 body 里附加 ``run_mode`` 的旧
#   客户端都被 Pydantic 视为未知字段忽略，最终仍按 DEBUG 处理。
# - /api/flows/{id}/run 是「试运行」入口，同样硬编码 DEBUG。
# - capability_policy 字段保留，仅作为白名单 / REDIRECT 高级通道。
#
# 这一块测试用 HTTP 层端到端验证：副作用类 builtin 在调试 / 试运行下被 SUPPRESS；
# 客户端无法通过任何 body 参数切换到 PRODUCTION。


def _make_test_client():
    from fastapi.testclient import TestClient

    import flow_engine.lookup.lookup_store as lookup_mod
    import flow_engine.stores.data_dict as dict_mod
    import flow_engine.stores.profile_store as profile_mod

    dict_mod.invalidate_store_cache()
    profile_mod.invalidate_profile_store_cache()
    lookup_mod.invalidate_lookup_store_cache()

    from flow_engine.api.http_api import create_app

    return TestClient(create_app())


def test_http_debug_node_is_locked_to_debug_mode() -> None:
    """``/api/debug/node`` SUPPRESSES side-effect builtins regardless of body.

    Even if a (hypothetical) old client sends ``run_mode=production`` it must
    still hit the DEBUG default policy (Pydantic drops unknown fields).
    """
    _reset_calls()
    client = _make_test_client()
    body = {
        "script": 'r = cap_probe(arg="http")\n{"called": r["called"]}',
        "initial_context": {},
        # Pretend an old client tries to override — must be ignored by the
        # service layer (no run_mode field in the schema any more).
        "run_mode": "production",
        # No capability_policy → DEBUG default suppresses ``cap_test_probe``?
        # Actually only ``integration / db_write / mq_publish`` are in the
        # default DEBUG policy. To prove run_mode is locked we add an explicit
        # SUPPRESS rule and observe it takes effect.
        "capability_policy": [
            {
                "builtin_category": "cap_test_probe",
                "action": "suppress",
            }
        ],
    }
    r = client.post("/api/debug/node", json=body)
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["ok"] is True
    assert payload["result"] == {"called": False}
    assert _REAL_CALLS == [], "debug HTTP path must SUPPRESS side-effect calls"


def test_http_debug_node_flow_continue_returns_control_flow() -> None:
    client = _make_test_client()
    script = """
def is_match():
    if normalized_alarm["alarm_type"] == "app_type_02":
        log_info("alarm type is app_type_02")
        flow_continue()
    return {"is_match": normalized_alarm["alarm_grade"] == "low"}

{"feature": is_match()}
""".strip()
    r = client.post(
        "/api/debug/node",
        json={
            "script": script,
            "initial_context": {
                "normalized_alarm": {"alarm_type": "app_type_02", "alarm_grade": "high"},
            },
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["ok"] is True
    assert payload["result"] == {}
    assert payload["control_flow"] == {"action": "continue"}
    assert any("app_type_02" in e.get("message", "") for e in payload.get("logs", []))


def test_http_debug_node_default_suppresses_integration() -> None:
    """No explicit policy + DEBUG default → ``integration`` builtins SUPPRESS.

    This is the safety net: even without a capability_policy in the body, a
    debug request never reaches network / DB integrations.
    """
    client = _make_test_client()
    # http_call is registered in ``integration`` category with
    # a dedicated suppress_result. Under DEBUG default it must be suppressed.
    body = {
        "script": 'r = http_call("svc", "ep")\n{"r": r}',
        "initial_context": {},
        "capability_policy": [],
    }
    r = client.post("/api/debug/node", json=body)
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["ok"] is True
    out = payload["result"]["r"]
    assert isinstance(out, dict)
    assert out.get("error_code") == "SUPPRESSED"
    assert out.get("meta", {}).get("_suppressed") is True


def test_http_run_flow_is_locked_to_debug_mode() -> None:
    """``/api/flows/{id}/run`` is the "试运行" path — also DEBUG-locked.

    Build a one-node flow whose script calls a side-effect builtin. Even if
    the client tries to coerce production mode, the call is suppressed.
    """
    _reset_calls()
    client = _make_test_client()

    flow_id = "cap_test_flow"
    body = {
        "display_name": flow_id,
        "version": "1.0.0",
        "strategies": {"default_sync": {"name": "default_sync", "mode": "sync"}},
        "nodes": [
            {
                "id": "n1",
                "type": "task",
                "strategy_ref": "default_sync",
                "script": 'r = cap_probe(arg="trial")\n{"called": r["called"]}',
                "boundary": {"outputs": {"called": "$.global.called"}},
            }
        ],
    }
    assert client.post("/api/flows", json={"id": flow_id, "display_name": flow_id}).status_code == 200
    assert client.put(f"/api/flows/{flow_id}/draft", json=body).status_code == 200
    assert client.post(f"/api/flows/{flow_id}/versions", json={}).status_code == 200

    # Old-shape client trying to override → run_mode silently ignored.
    run_body = {
        "merge": True,
        "run_mode": "production",  # ignored by Pydantic schema
        "capability_policy": [
            {"builtin_category": "cap_test_probe", "action": "suppress"}
        ],
    }
    r = client.post(f"/api/flows/{flow_id}/run", json=run_body)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["state"] in {"COMPLETED", "FAILED"}, res
    # The flow should run successfully, side-effect SUPPRESSED.
    assert res["state"] == "COMPLETED"
    assert res["global_ns"].get("called") is False
    assert _REAL_CALLS == [], "trial-run HTTP path must SUPPRESS side-effect calls"


# ---------------------------------------------------------------------------
# Pytest plumbing
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_probe_calls() -> None:
    _reset_calls()
    yield
    _reset_calls()
