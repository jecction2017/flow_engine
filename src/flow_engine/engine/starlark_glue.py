"""Starlark evaluation, builtins, and process-pool worker entrypoint."""

from __future__ import annotations

import json
import re
import threading
from contextlib import contextmanager
from typing import Any, Iterator

import starlark as sl

from flow_engine.engine.context import ContextStack
from flow_engine.engine.exceptions import (
    BreakInterrupt,
    ContinueInterrupt,
    JumpTarget,
    TerminateInterrupt,
    starlark_to_python,
)

# ---------------------------------------------------------------------------
# Control-flow exception unwrapping
#
# The Starlark binding we use wraps every Python exception raised inside a
# registered builtin into `sl.StarlarkError`, discarding the original
# `__cause__` / `__context__`. Our flow-control builtins (`flow_jump`,
# `flow_continue`, `flow_break`, `flow_terminate`) therefore need to stash the
# original exception on a thread-local so the caller can re-raise the true
# type after `sl.eval` returns control.
# ---------------------------------------------------------------------------

_CF_LOCAL = threading.local()


def _cf_set(exc: BaseException) -> None:
    _CF_LOCAL.pending = exc


def _cf_pop() -> BaseException | None:
    exc = getattr(_CF_LOCAL, "pending", None)
    _CF_LOCAL.pending = None
    return exc


@contextmanager
def cf_guard() -> Iterator[None]:
    """Wrap a `sl.eval` call so flow-control builtins propagate as their
    original Python exception types instead of opaque `StarlarkError`s."""
    _CF_LOCAL.pending = None
    try:
        yield
    except sl.StarlarkError:
        pending = _cf_pop()
        if pending is not None:
            raise pending
        raise
    finally:
        _CF_LOCAL.pending = None


def eval_iterable_expr(expr: str, ctx: ContextStack) -> list[Any]:
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    return sdk_runtime.eval_iterable_expr(expr, ctx)


def _globals_extended() -> sl.Globals:
    return sl.Globals.extended_by([sl.LibraryExtension.Json])


def _http_request(url: str, method: str = "GET", body: str | None = None) -> dict[str, Any]:
    """Controlled HTTP helper (optional); kept minimal for sandboxed demos."""
    try:
        import urllib.request

        req = urllib.request.Request(url, method=method.upper(), data=body.encode() if body else None)
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
            return {"status": resp.status, "body": parsed}
    except Exception as exc:  # noqa: BLE001
        return {"status": -1, "error": str(exc)}


def _regex_match(pattern: str, text: str) -> bool:
    return re.search(pattern, text) is not None


def _attach_builtins(mod: sl.Module) -> None:
    mod.add_callable("http_request", _http_request)
    mod.add_callable("regex_match", _regex_match)

    def _jump(target: str) -> None:
        exc = JumpTarget(target)
        _cf_set(exc)
        raise exc

    def _flow_continue() -> None:
        exc = ContinueInterrupt()
        _cf_set(exc)
        raise exc

    def _flow_break() -> None:
        exc = BreakInterrupt()
        _cf_set(exc)
        raise exc

    def _terminate() -> None:
        exc = TerminateInterrupt()
        _cf_set(exc)
        raise exc

    mod.add_callable("flow_jump", _jump)
    mod.add_callable("flow_continue", _flow_continue)
    mod.add_callable("flow_break", _flow_break)
    mod.add_callable("flow_terminate", _terminate)


def inject_context_paths(mod: sl.Module, ctx: ContextStack, boundary_inputs: dict[str, str]) -> None:
    """boundary_inputs maps context path -> Starlark global name."""
    for path, var in boundary_inputs.items():
        mod[var] = ctx.get_path(path)


def inject_resolve(mod: sl.Module, ctx: ContextStack) -> None:
    mod.add_callable("resolve", lambda p: ctx.get_path(p))


def eval_condition(expr: str | None, ctx: ContextStack) -> bool:
    if not expr:
        return True
    mod = sl.Module()
    inject_resolve(mod, ctx)
    glb = _globals_extended()
    ast = sl.parse("cond.star", f"({expr})")
    with cf_guard():
        val = sl.eval(mod, ast, glb)
    return bool(val)


def run_starfile_script(
    script: str,
    *,
    extra_globals: dict[str, Any] | None = None,
) -> Any:
    mod = sl.Module()
    if extra_globals:
        for k, v in extra_globals.items():
            mod[k] = v
    glb = _globals_extended()
    ast = sl.parse("task.star", script)
    with cf_guard():
        return starlark_to_python(sl.eval(mod, ast, glb))


def run_task_script(
    script: str,
    ctx: ContextStack,
    boundary_inputs: dict[str, str],
) -> dict[str, Any]:
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    return sdk_runtime.eval_task_script(script, ctx, boundary_inputs)


def debug_task_script(
    script: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Task-node debug entrypoint: bind top-level keys of ``variables``
    directly as Starlark globals (no boundary mapping)."""
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    return sdk_runtime.debug_task_script(script, variables)


def run_hook_script(snippet: str | None, ctx: ContextStack, extra: dict[str, Any] | None = None) -> None:
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    return sdk_runtime.run_hook_script(snippet, ctx, extra)


def apply_outputs(
    result: dict[str, Any],
    outputs_map: dict[str, str],
    ctx: ContextStack,
) -> None:
    """outputs_map: starlark key (dotted) -> context path."""
    for key, path in outputs_map.items():
        val = _dig_key(result, key.split("."))
        ctx.set_path(path, val)


def _dig_key(obj: dict[str, Any], parts: list[str]) -> Any:
    cur: Any = obj
    for p in parts:
        if not isinstance(cur, dict):
            raise KeyError(parts)
        cur = cur[p]
    return cur


# --- Process pool payload (pickle-friendly) ---


def _attach_process_builtins(mod: sl.Module) -> None:
    """Process workers must not raise flow-control exceptions into the parent memory space."""
    mod.add_callable("http_request", _http_request)
    mod.add_callable("regex_match", _regex_match)


def process_starlark_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Executed inside a worker process; reconstructs minimal context from serialized inputs."""
    from flow_engine.starlark_sdk.python_builtin_impl import PYTHON_BUILTINS

    script = payload["script"]
    flat = payload["flat_inputs"]
    mod = sl.Module()
    for var, pyval in flat.items():
        mod[var] = pyval
    _attach_process_builtins(mod)
    for name, fn in PYTHON_BUILTINS.items():
        mod.add_callable(name, fn)
    glb = _globals_extended()
    ast = sl.parse("task.star", script)
    val = starlark_to_python(sl.eval(mod, ast, glb))
    if val is None:
        val = {}
    if not isinstance(val, dict):
        raise TypeError("task must return dict")
    return {"result": val}
