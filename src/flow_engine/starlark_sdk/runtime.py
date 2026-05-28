"""Task / hook / condition evaluation with load() + SDK builtins."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

import copy as _copy

import starlark as sl

from flow_engine.engine.context import ContextStack
from flow_engine.engine.exceptions import (
    BreakInterrupt,
    ContinueInterrupt,
    JumpTarget,
    TerminateInterrupt,
    flow_control_descriptor,
    starlark_to_python,
)
from flow_engine.starlark_sdk.builtin_registry import (
    ATTACH_CONTEXT,
    ATTACH_FLOW_CONTROL,
    PythonBuiltinSpec,
    list_registered_builtins,
)
from flow_engine.starlark_sdk.loader import build_file_loader, dialect_with_load, loader_stats, warmup_modules


def _globals_main() -> sl.Globals:
    return sl.Globals.extended_by([sl.LibraryExtension.Json])


_AST_CACHE_MAX = max(32, int(os.environ.get("FLOW_ENGINE_STARLARK_AST_CACHE_SIZE", "2048")))
_AST_CACHE_LOCK = threading.RLock()
_AST_CACHE: OrderedDict[str, Any] = OrderedDict()
_AST_HITS = 0
_AST_MISSES = 0


def _ast_cache_key(label: str, script: str) -> str:
    _ = label
    return script


def _parse_cached(label: str, script: str) -> Any:
    global _AST_HITS, _AST_MISSES
    key = _ast_cache_key(label, script)
    with _AST_CACHE_LOCK:
        ast = _AST_CACHE.get(key)
        if ast is not None:
            _AST_HITS += 1
            _AST_CACHE.move_to_end(key)
            return ast
        _AST_MISSES += 1
    ast = sl.parse(label, script, dialect=dialect_with_load())
    with _AST_CACHE_LOCK:
        _AST_CACHE[key] = ast
        if len(_AST_CACHE) > _AST_CACHE_MAX:
            _AST_CACHE.popitem(last=False)
    return ast


def validate_script_syntax(label: str, script: str) -> None:
    """Validate Starlark syntax by parsing only (no execution)."""
    sl.parse(label, script, dialect=dialect_with_load())


class _ExecBudget:
    def __init__(self) -> None:
        self.max_python_calls = max(1, int(os.environ.get("FLOW_ENGINE_STARLARK_MAX_PY_CALLS", "1000")))
        self.max_exec_ms = max(10, int(os.environ.get("FLOW_ENGINE_STARLARK_MAX_EXEC_MS", "30000")))
        self._deadline = 0.0
        self._py_calls = 0

    def start(self) -> None:
        self._deadline = time.monotonic() + (self.max_exec_ms / 1000.0)
        self._py_calls = 0

    def before_builtin_call(self, name: str) -> None:
        if time.monotonic() > self._deadline:
            raise TimeoutError(f"starlark budget timeout before calling builtin: {name}")
        self._py_calls += 1
        if self._py_calls > self.max_python_calls:
            raise RuntimeError(f"starlark python builtin call limit exceeded: {self.max_python_calls}")

    def after_builtin_call(self, name: str) -> None:
        if time.monotonic() > self._deadline:
            raise TimeoutError(f"starlark budget timeout after calling builtin: {name}")

    def remaining_ms(self) -> int:
        """Milliseconds left in this eval budget (0 if expired)."""
        return max(0, int((self._deadline - time.monotonic()) * 1000))


_EXEC_BUDGET_LOCAL = threading.local()


def _active_budget() -> _ExecBudget | None:
    return getattr(_EXEC_BUDGET_LOCAL, "budget", None)


def remaining_budget_ms() -> int | None:
    """Remaining Starlark eval time in ms, or None outside a budget scope."""
    b = _active_budget()
    if b is None:
        return None
    return b.remaining_ms()


@contextmanager
def _budget_scope() -> Any:
    b = _ExecBudget()
    b.start()
    _EXEC_BUDGET_LOCAL.budget = b
    try:
        yield b
    finally:
        _EXEC_BUDGET_LOCAL.budget = None


# ---------------------------------------------------------------------------
# In-script logging (log / log_info / log_warn / log_error)
#
# A `LogCollector` is pushed onto a thread-local before every script eval.
# The `log*` builtins append entries to the active collector; after eval
# completes the caller reads `.entries()` and surfaces them via the API.
# The scope does NOT cross threads – process-pool workers start their own
# scope in :func:`process_starlark_task` and ship results back verbatim.
# ---------------------------------------------------------------------------


LOG_LEVELS = ("debug", "info", "warn", "error")
_DEFAULT_LEVEL = "info"
_LOG_MAX_ENTRIES = max(1, int(os.environ.get("FLOW_ENGINE_STARLARK_LOG_MAX_ENTRIES", "500")))
_LOG_MAX_MSG = max(64, int(os.environ.get("FLOW_ENGINE_STARLARK_LOG_MAX_MSG", "2048")))


@dataclass
class LogEntry:
    level: str
    message: str
    ts_ms: int
    source: str
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "level": self.level,
            "message": self.message,
            "ts_ms": self.ts_ms,
            "source": self.source,
        }
        if self.truncated:
            d["truncated"] = True
        return d


class LogCollector:
    """Thread-local sink backing the `log*` Starlark builtins.

    Entries are bounded by ``FLOW_ENGINE_STARLARK_LOG_MAX_ENTRIES`` (total
    count) and each message by ``FLOW_ENGINE_STARLARK_LOG_MAX_MSG`` (chars).
    Excess count beyond the cap is dropped but flagged on the last kept
    entry via ``truncated=True`` so the UI can render an ellipsis marker.
    """

    def __init__(self, source: str) -> None:
        self._source = source
        self._entries: list[LogEntry] = []
        self._t0 = time.monotonic()
        self._dropped = 0

    @property
    def source(self) -> str:
        return self._source

    def set_source(self, source: str) -> None:
        self._source = source

    def append(self, level: str, message: str) -> None:
        lvl = level.lower() if isinstance(level, str) else _DEFAULT_LEVEL
        if lvl not in LOG_LEVELS:
            lvl = _DEFAULT_LEVEL
        if len(message) > _LOG_MAX_MSG:
            message = message[: _LOG_MAX_MSG - 1] + "…"
        ts_ms = max(0, int((time.monotonic() - self._t0) * 1000))
        if len(self._entries) >= _LOG_MAX_ENTRIES:
            self._dropped += 1
            if self._entries:
                self._entries[-1].truncated = True
            return
        self._entries.append(
            LogEntry(level=lvl, message=message, ts_ms=ts_ms, source=self._source)
        )

    def entries(self) -> list[LogEntry]:
        return list(self._entries)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._entries]


_LOG_LOCAL = threading.local()


def _active_collector() -> LogCollector | None:
    return getattr(_LOG_LOCAL, "collector", None)


@contextmanager
def log_scope(source: str) -> Iterator[LogCollector]:
    """Push a fresh `LogCollector` for the duration of a script eval.

    Nested scopes temporarily shadow the outer collector; the outer one is
    restored on exit so concurrently nested `eval_condition` calls inside a
    hook don't silently swallow their parent's logs.
    """
    prev = getattr(_LOG_LOCAL, "collector", None)
    coll = LogCollector(source)
    _LOG_LOCAL.collector = coll
    try:
        yield coll
    finally:
        _LOG_LOCAL.collector = prev


def _format_log_arg(val: Any) -> str:
    """Render a single Starlark/Python value to a printable string.

    Containers are dumped as compact JSON (``default=str`` for non-JSON
    types) so ``log_info("payload=", data)`` stays readable for dict/list
    inputs without forcing users to call ``json.encode`` themselves.
    """
    if isinstance(val, str):
        return val
    if val is None or isinstance(val, (bool, int, float)):
        return str(val)
    if isinstance(val, (dict, list, tuple)):
        try:
            return json.dumps(starlark_to_python(val), ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return repr(val)
    return str(val)


def _format_log_args(args: tuple[Any, ...]) -> str:
    if not args:
        return ""
    return " ".join(_format_log_arg(a) for a in args)


def _make_log_builtin(fixed_level: str | None = None) -> Any:
    """Return a Starlark builtin that forwards to the active collector.

    When ``fixed_level`` is set (e.g. ``log_warn``) the ``level`` kwarg is
    ignored so callers can't accidentally downgrade a warning by passing
    ``level="info"``.
    """

    def _log(*args: Any, level: str = _DEFAULT_LEVEL) -> None:
        coll = _active_collector()
        if coll is None:
            return None
        lvl = fixed_level or level
        coll.append(lvl, _format_log_args(args))
        return None

    return _log


def runtime_log(*args: Any, level: str = _DEFAULT_LEVEL) -> None:
    """Entry point used by declaratively registered `log` builtin."""
    coll = _active_collector()
    if coll is None:
        return None
    coll.append(level, _format_log_args(args))
    return None


def runtime_log_info(*args: Any) -> None:
    """Entry point used by declaratively registered `log_info` builtin."""
    coll = _active_collector()
    if coll is None:
        return None
    coll.append("info", _format_log_args(args))
    return None


def runtime_log_warn(*args: Any) -> None:
    """Entry point used by declaratively registered `log_warn` builtin."""
    coll = _active_collector()
    if coll is None:
        return None
    coll.append("warn", _format_log_args(args))
    return None


def runtime_log_error(*args: Any) -> None:
    """Entry point used by declaratively registered `log_error` builtin."""
    coll = _active_collector()
    if coll is None:
        return None
    coll.append("error", _format_log_args(args))
    return None


def runtime_log_debug(*args: Any) -> None:
    """Entry point used by declaratively registered `log_debug` builtin."""
    coll = _active_collector()
    if coll is None:
        return None
    coll.append("debug", _format_log_args(args))
    return None


# ---------------------------------------------------------------------------
# Capability-aware builtin guard
#
# `_guard_builtin` enforces TWO orthogonal constraints in one wrapper:
#  1. Per-eval execution budget (time / call count).
#  2. CapabilityPolicy: SUPPRESS short-circuits with the spec's
#     ``suppress_result`` (still counted against the budget so a runaway
#     loop can't infinite-loop on a suppressed call); REDIRECT forwards
#     ``redirect_params`` to the function body via thread-local — only
#     builtins that need to *change behaviour* on redirect read it via
#     :func:`get_redirect_params`. ALLOW / "none"-side-effect builtins
#     skip the capability lookup entirely (zero overhead).
#
# Why thread-local for redirect params (not arg passing): preserves the
# Starlark callable signature so user code stays identical regardless of
# whether the function happened to be redirected.
# ---------------------------------------------------------------------------


_REDIRECT_PARAMS_LOCAL = threading.local()


def get_redirect_params() -> dict[str, Any]:
    """Return REDIRECT params for the currently-executing builtin call.

    Returns ``{}`` for ALLOW / SUPPRESS / non-side-effect builtins. Only
    valid during the synchronous body of a guarded builtin call.
    """
    return getattr(_REDIRECT_PARAMS_LOCAL, "params", {}) or {}


def _guard_builtin(name: str, fn: Any, spec: PythonBuiltinSpec | None = None) -> Any:
    has_side_effect = bool(spec is not None and spec.side_effects and spec.side_effects != "none")
    suppress_result = spec.suppress_result if spec is not None else None
    category = spec.category if spec is not None else ""

    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        from flow_engine.runner.mode_context import CapabilityAction, check_capability

        b = _active_budget()
        if b is not None:
            b.before_builtin_call(name)

        if has_side_effect:
            action, redirect_params = check_capability(category, name)
            if action == CapabilityAction.SUPPRESS:
                # Defensive copy so user code can't mutate the shared
                # ``suppress_result`` literal stored on the spec.
                if isinstance(suppress_result, (dict, list)):
                    out = _copy.deepcopy(suppress_result)
                else:
                    out = suppress_result
                if b is not None:
                    b.after_builtin_call(name)
                return out
            _REDIRECT_PARAMS_LOCAL.params = redirect_params if action == CapabilityAction.REDIRECT else {}
        else:
            _REDIRECT_PARAMS_LOCAL.params = {}

        try:
            out = fn(*args, **kwargs)
        finally:
            _REDIRECT_PARAMS_LOCAL.params = {}
        if b is not None:
            b.after_builtin_call(name)
        return out

    return _wrapped


_LOG_BUILTINS = frozenset({"log", "log_info", "log_warn", "log_error", "log_debug"})


def _attach_sdk_python(mod: sl.Module) -> None:
    # Use dynamic registry snapshot so all @register_builtin functions,
    # including runtime-provided log builtins, are attached uniformly.
    # Importing module here guarantees decorators have populated registry
    # even when runtime is used outside HTTP API bootstrap.
    from flow_engine.starlark_sdk import python_builtin_impl as _python_builtin_impl  # noqa: F401
    from flow_engine.starlark_sdk import runtime_builtins as _runtime_builtins  # noqa: F401
    from flow_engine.starlark_sdk import integrations as _integrations  # noqa: F401
    from flow_engine.starlark_sdk import builtins as _builtins  # noqa: F401

    for entry in list_registered_builtins():
        spec = entry.spec
        name = spec.starlark_name
        if spec.attach_mode == ATTACH_CONTEXT:
            continue
        fn = entry.fn
        if spec.attach_mode == ATTACH_FLOW_CONTROL:
            mod.add_callable(name, fn)
        elif name in _LOG_BUILTINS:
            # Side-effect-free accumulators; skip budget/capability wrapper.
            mod.add_callable(name, fn)
        else:
            mod.add_callable(name, _guard_builtin(name, fn, spec))


def _prepare_module(mod: sl.Module, ctx: ContextStack, boundary_inputs: dict[str, str]) -> None:
    from flow_engine.engine.starlark_glue import inject_context_paths, inject_resolve

    inject_context_paths(mod, ctx, boundary_inputs)
    inject_resolve(mod, ctx)
    _attach_sdk_python(mod)


def eval_task_script(
    script: str,
    ctx: ContextStack,
    boundary_inputs: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Execute a production task script.

    Returns ``(result_dict, log_entries)`` where ``log_entries`` is a list
    of serialized :class:`LogEntry` dicts captured during evaluation. The
    orchestrator attaches them to the owning node's ``NodeRunInfo.logs``.
    """
    from flow_engine.engine.starlark_glue import cf_guard

    with _budget_scope(), log_scope("task") as coll:
        mod = sl.Module()
        _prepare_module(mod, ctx, boundary_inputs)
        file_loader, _cache = build_file_loader()
        glb = _globals_main()
        ast = _parse_cached("task.star", script)
        with cf_guard():
            val = sl.eval(mod, ast, glb, file_loader=file_loader)
        logs = coll.as_dicts()
    val = starlark_to_python(val)
    if val is None:
        return {}, logs
    if not isinstance(val, dict):
        raise TypeError(f"Task script must evaluate to a dict, got {type(val).__name__}")
    return val, logs


def debug_task_script(
    script: str,
    variables: dict[str, Any] | None = None,
    *,
    run_mode: Any = None,
    capability_policy: Any = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    """Debug-only evaluation for a task node.

    Unlike :func:`eval_task_script`, this path **does not** perform boundary
    input mapping. Every top-level key of ``variables`` is bound directly as a
    Starlark global so the script can reference them by name. A lightweight
    ``ContextStack`` backed by the same dict is also provided so helpers such
    as ``resolve("$.key")`` continue to work identically to production runs.

    ``run_mode`` and ``capability_policy`` activate a ``run_mode_scope`` so
    capability constraints take effect for the duration of evaluation. Both
    default to ``None``: callers (HTTP debug endpoints, process worker)
    pass them explicitly when needed; non-passing callers preserve the
    pre-existing behaviour (no scope opened — capability defaults to whatever
    is already active in the calling context, or PRODUCTION when none is).

    Returns ``(result_dict, log_entries, control_flow)`` where ``control_flow``
    is ``None`` on normal completion, or a descriptor such as
    ``{"action": "continue"}`` when a flow-control builtin interrupts
    evaluation (mirrors orchestrator handling in production runs).
    """
    from contextlib import nullcontext

    from flow_engine.engine.starlark_glue import cf_guard, inject_resolve
    from flow_engine.runner.mode_context import run_mode_scope
    from flow_engine.runner.models import CapabilityRule, RunMode

    vars_map: dict[str, Any] = dict(variables or {})
    ctx = ContextStack(global_ns=vars_map)

    if run_mode is None and capability_policy is None:
        scope_cm: Any = nullcontext()
    else:
        mode = run_mode if isinstance(run_mode, RunMode) else (
            RunMode(run_mode) if run_mode is not None else RunMode.DEBUG
        )
        rules: list[CapabilityRule] = []
        for r in capability_policy or []:
            if isinstance(r, CapabilityRule):
                rules.append(r)
            else:
                rules.append(CapabilityRule.model_validate(r))
        scope_cm = run_mode_scope(mode, rules)

    with scope_cm, _budget_scope(), log_scope("task") as coll:
        mod = sl.Module()
        for name, value in vars_map.items():
            mod[name] = value
        inject_resolve(mod, ctx)
        _attach_sdk_python(mod)
        file_loader, _cache = build_file_loader()
        glb = _globals_main()
        ast = _parse_cached("debug_task.star", script)
        control_flow: dict[str, Any] | None = None
        try:
            with cf_guard():
                val = sl.eval(mod, ast, glb, file_loader=file_loader)
        except (ContinueInterrupt, BreakInterrupt, TerminateInterrupt, JumpTarget) as exc:
            control_flow = flow_control_descriptor(exc)
            val = None
        logs = coll.as_dicts()
    if control_flow is not None:
        return {}, logs, control_flow
    val = starlark_to_python(val)
    if val is None:
        return {}, logs, None
    if not isinstance(val, dict):
        raise TypeError(f"Debug task script must evaluate to a dict, got {type(val).__name__}")
    return val, logs, None


def eval_transform_script(
    script: str,
    variables: dict[str, Any],
    *,
    run_mode: Any = None,
    capability_policy: Any = None,
) -> dict[str, Any]:
    """Map inbound record to trigger_context via user Starlark (subscription parse.script)."""
    result, _logs, control_flow = debug_task_script(
        script,
        variables,
        run_mode=run_mode,
        capability_policy=capability_policy,
    )
    if control_flow is not None:
        raise TypeError(
            f"transform script must return a dict, got flow control {control_flow!r}"
        )
    return result


def eval_key_expr(
    expr: str,
    ctx: ContextStack,
    boundary_inputs: dict[str, str],
) -> str:
    """Evaluate ``expr`` with boundary inputs bound and coerce result to ``str``.

    Used by ``record_replay`` mock to compute a cache key. Logs emitted by the
    expression are intentionally dropped: they belong to no node phase. The
    runtime budget is shared with regular task scripts so a runaway key
    expression cannot evade enforcement.
    """
    from flow_engine.engine.starlark_glue import cf_guard, inject_context_paths, inject_resolve

    with _budget_scope(), log_scope("key_expr"):
        mod = sl.Module()
        inject_context_paths(mod, ctx, boundary_inputs)
        inject_resolve(mod, ctx)
        _attach_sdk_python(mod)
        file_loader, _ = build_file_loader()
        glb = _globals_main()
        ast = _parse_cached("key_expr.star", f"({expr})")
        with cf_guard():
            val = sl.eval(mod, ast, glb, file_loader=file_loader)
    val = starlark_to_python(val)
    if val is None:
        return ""
    return str(val)


def eval_condition(expr: str | None, ctx: ContextStack) -> bool:
    if not expr:
        return True
    mod = sl.Module()
    from flow_engine.engine.starlark_glue import cf_guard, inject_resolve

    inject_resolve(mod, ctx)
    _attach_sdk_python(mod)
    glb = _globals_main()
    ast = _parse_cached("cond.star", f"({expr})")
    file_loader, _ = build_file_loader()
    # Condition logs are intentionally dropped: the scope exists only so
    # `log_*` calls don't fail, but attributing them to a node is ambiguous
    # (a condition is evaluated BEFORE the node enters STAGING).
    with log_scope("condition"), cf_guard():
        val = sl.eval(mod, ast, glb, file_loader=file_loader)
    return bool(val)


_CTX_PATH_RE = re.compile(r"^\s*(\$(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\s*$")


def _normalize_iterable_expr(expr: str) -> str:
    """Accept a pure context-path (``$.a.b``) shorthand alongside full Starlark.

    If ``expr`` is a bare ``$.<path>`` string (the same notation used everywhere
    else in the engine for context addressing), rewrite it to the canonical
    ``resolve("$.<path>")`` Starlark call. Any other expression is returned
    unchanged and parsed as-is.
    """
    m = _CTX_PATH_RE.match(expr)
    if m is not None:
        return f'resolve("{m.group(1)}")'
    return expr


def eval_iterable_expr(expr: str, ctx: ContextStack) -> list[Any]:
    mod = sl.Module()
    from flow_engine.engine.starlark_glue import cf_guard, inject_resolve

    inject_resolve(mod, ctx)
    _attach_sdk_python(mod)
    glb = _globals_main()
    normalized = _normalize_iterable_expr(expr)
    try:
        ast = _parse_cached("iter.star", f"({normalized})")
    except sl.StarlarkError as err:
        if "$" in expr:
            raise ValueError(
                "Loop iterable must be a Starlark expression; to reference a "
                'context path use resolve("$.path") (e.g. '
                'resolve("$.global.items")). Got: ' + expr
            ) from err
        raise
    file_loader, _ = build_file_loader()
    # Iterable-expression logs are dropped for the same reason as condition
    # logs: no well-defined node they belong to.
    with log_scope("iterable"), cf_guard():
        val = sl.eval(mod, ast, glb, file_loader=file_loader)
    return list(val)


def run_hook_script(
    snippet: str | None,
    ctx: ContextStack,
    extra: dict[str, Any] | None = None,
    *,
    source: str = "hook",
) -> list[dict[str, Any]]:
    """Execute a hook snippet and return any logs it emitted.

    ``source`` is carried into each produced :class:`LogEntry` so the UI
    can label which hook phase (`pre_exec`, `post_exec`, `on_iteration_*`,
    `on_start`, `on_complete`, `on_failure`) the entry came from.
    """
    if not snippet:
        return []
    mod = sl.Module()
    from flow_engine.engine.starlark_glue import cf_guard, inject_resolve

    inject_resolve(mod, ctx)
    if extra:
        for k, v in extra.items():
            mod[k] = v
    _attach_sdk_python(mod)
    glb = _globals_main()
    ast = _parse_cached("hook.star", snippet)
    file_loader, _ = build_file_loader()
    with log_scope(source) as coll, cf_guard():
        sl.eval(mod, ast, glb, file_loader=file_loader)
    return coll.as_dicts()


def warmup_runtime(module_ids: list[str], script_samples: list[str] | None = None) -> dict[str, Any]:
    """Proactively populate module and AST caches for hot paths."""
    m = warmup_modules(module_ids)
    compiled = 0
    if script_samples:
        for i, src in enumerate(script_samples):
            _parse_cached(f"warmup_{i}.star", src)
            compiled += 1
    return {"modules": m, "compiled_scripts": compiled}


def runtime_stats() -> dict[str, Any]:
    with _AST_CACHE_LOCK:
        total = _AST_HITS + _AST_MISSES
        ast_hit_ratio = (_AST_HITS / total) if total else 0.0
        ast_data = {
            "cached_asts": len(_AST_CACHE),
            "hits": _AST_HITS,
            "misses": _AST_MISSES,
            "hit_ratio": round(ast_hit_ratio, 4),
            "capacity": _AST_CACHE_MAX,
        }
    return {
        "loader": loader_stats(),
        "ast": ast_data,
        "limits": {
            "max_python_calls": _ExecBudget().max_python_calls,
            "max_exec_ms": _ExecBudget().max_exec_ms,
        },
    }
