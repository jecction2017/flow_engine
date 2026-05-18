"""Starlark evaluation, builtins, and process-pool worker entrypoint."""

from __future__ import annotations

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


def _regex_match(pattern: str, text: str) -> bool:
    return re.search(pattern, text) is not None


def _attach_builtins(mod: sl.Module) -> None:
    # ``http_request`` is now registered through ``@register_builtin`` in
    # ``python_builtin_impl`` so it goes through ``_guard_builtin`` (budget
    # + capability). It is attached uniformly via ``_attach_sdk_python``.
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
    """Delegate to the SDK runtime.

    The SDK path attaches the full SDK builtin set (``dict_get``,
    ``lookup_query``, ``log_*`` …), enables the AST cache, and applies the
    same ``_guard_builtin`` capability/budget enforcement used for task
    scripts. Keeping condition evaluation on a stripped-down path here
    diverged from hooks / iterables and broke capability constraints.
    """
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    return sdk_runtime.eval_condition(expr, ctx)


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
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Execute a task script and return ``(result, logs)``."""
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    return sdk_runtime.eval_task_script(script, ctx, boundary_inputs)


def eval_key_expr(
    expr: str,
    ctx: ContextStack,
    boundary_inputs: dict[str, str],
) -> str:
    """Evaluate ``expr`` with boundary inputs bound, coerce to ``str``.

    Used by ``record_replay`` mock to compute a cache key. Boundary inputs are
    bound by their Starlark variable name (the value side of ``boundary.inputs``)
    so the expression looks identical to the wrapped task script.
    """
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    return sdk_runtime.eval_key_expr(expr, ctx, boundary_inputs)


def debug_task_script(
    script: str,
    variables: dict[str, Any] | None = None,
    *,
    run_mode: Any = None,
    capability_policy: Any = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Task-node debug entrypoint: bind top-level keys of ``variables``
    directly as Starlark globals (no boundary mapping).

    ``run_mode`` / ``capability_policy`` are forwarded to the SDK runtime
    so HTTP debug endpoints can opt into a capability scope (e.g. DEBUG
    suppresses ``integration`` writes by default). Returns ``(result, logs)``.
    """
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    from flow_engine.connectors.registry import get_registry
    from flow_engine.stores.data_dict import active_dictionary
    from flow_engine.stores.profile_store import active_profile

    tree = active_dictionary()
    if tree is not None:
        try:
            pid = active_profile()
        except Exception:  # noqa: BLE001
            pid = None
        get_registry().bind(tree, profile=pid)

    return sdk_runtime.debug_task_script(
        script,
        variables,
        run_mode=run_mode,
        capability_policy=capability_policy,
    )


def run_hook_script(
    snippet: str | None,
    ctx: ContextStack,
    extra: dict[str, Any] | None = None,
    *,
    source: str = "hook",
) -> list[dict[str, Any]]:
    """Run a hook script and return its captured log entries.

    ``source`` labels each resulting entry so the orchestrator can
    attribute them to ``pre_exec`` / ``post_exec`` / ``on_iteration_*`` /
    ``on_start`` / ``on_complete`` / ``on_failure``.
    """
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    return sdk_runtime.run_hook_script(snippet, ctx, extra, source=source)


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


def process_starlark_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Executed inside a worker process; reconstructs minimal context from
    serialized inputs. Captures log entries and ships them back across the
    IPC boundary so the orchestrator can attach them to the owning node.

    Payload schema:
        script:           str
        inputs:           dict[str, str] (informational; not used here)
        flat_inputs:      dict[str, Any] (already resolved values bound as Starlark globals)
        dictionary:       dict[str, Any] (resolved data dictionary)
        run_mode:         str (RunMode value), optional, default 'production'
        effective_policy: list[dict] (CapabilityRule json), optional, default []

    Implementation note:
        Delegates to ``sdk_runtime.debug_task_script`` so the worker shares
        the **same** evaluation pipeline as the main process: budget scope,
        ``cf_guard`` (flow-control exception unwrap), file loader for
        ``load()``, and ``_guard_builtin`` capability + budget wrapper. A
        previous version attached builtins directly via ``add_callable``,
        which silently bypassed the budget cap, capability policy, and
        flow-control machinery.
    """
    from flow_engine.runner.mode_context import run_mode_scope
    from flow_engine.runner.models import CapabilityRule, RunMode
    from flow_engine.starlark_sdk import runtime as sdk_runtime
    from flow_engine.stores.data_dict import dictionary_scope

    script = payload["script"]
    flat = dict(payload["flat_inputs"])
    run_mode = RunMode(payload.get("run_mode", RunMode.PRODUCTION.value))
    effective_policy = [
        CapabilityRule.model_validate(r) for r in payload.get("effective_policy", [])
    ]

    from flow_engine.connectors.registry import get_registry

    with run_mode_scope(run_mode, effective_policy):
        with dictionary_scope(payload.get("dictionary") or {}):
            get_registry().bind(payload.get("dictionary") or {})
            result, logs = sdk_runtime.debug_task_script(script, flat)
    return {"result": result, "logs": logs}
