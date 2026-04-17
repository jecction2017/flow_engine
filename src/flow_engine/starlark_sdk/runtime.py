"""Task / hook / condition evaluation with load() + SDK builtins."""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from typing import Any

import starlark as sl

from flow_engine.engine.context import ContextStack
from flow_engine.engine.exceptions import starlark_to_python
from flow_engine.starlark_sdk.loader import build_file_loader, dialect_with_load, loader_stats, warmup_modules
from flow_engine.starlark_sdk.python_builtin_impl import PYTHON_BUILTINS


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


class _ExecBudget:
    def __init__(self) -> None:
        self.max_python_calls = max(1, int(os.environ.get("FLOW_ENGINE_STARLARK_MAX_PY_CALLS", "1000")))
        self.max_exec_ms = max(10, int(os.environ.get("FLOW_ENGINE_STARLARK_MAX_EXEC_MS", "5000")))
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


_EXEC_BUDGET_LOCAL = threading.local()


def _active_budget() -> _ExecBudget | None:
    return getattr(_EXEC_BUDGET_LOCAL, "budget", None)


@contextmanager
def _budget_scope() -> Any:
    b = _ExecBudget()
    b.start()
    _EXEC_BUDGET_LOCAL.budget = b
    try:
        yield b
    finally:
        _EXEC_BUDGET_LOCAL.budget = None


def _guard_builtin(name: str, fn: Any) -> Any:
    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        b = _active_budget()
        if b is not None:
            b.before_builtin_call(name)
        out = fn(*args, **kwargs)
        if b is not None:
            b.after_builtin_call(name)
        return out

    return _wrapped


def _attach_sdk_python(mod: sl.Module) -> None:
    for name, fn in PYTHON_BUILTINS.items():
        mod.add_callable(name, _guard_builtin(name, fn))


def _prepare_module(mod: sl.Module, ctx: ContextStack, boundary_inputs: dict[str, str]) -> None:
    from flow_engine.engine.starlark_glue import _attach_builtins, inject_context_paths, inject_resolve

    inject_context_paths(mod, ctx, boundary_inputs)
    inject_resolve(mod, ctx)
    _attach_builtins(mod)
    _attach_sdk_python(mod)


def eval_task_script(
    script: str,
    ctx: ContextStack,
    boundary_inputs: dict[str, str],
) -> dict[str, Any]:
    from flow_engine.engine.starlark_glue import cf_guard

    with _budget_scope():
        mod = sl.Module()
        _prepare_module(mod, ctx, boundary_inputs)
        file_loader, _cache = build_file_loader()
        glb = _globals_main()
        ast = _parse_cached("task.star", script)
        with cf_guard():
            val = sl.eval(mod, ast, glb, file_loader=file_loader)
    val = starlark_to_python(val)
    if val is None:
        return {}
    if not isinstance(val, dict):
        raise TypeError(f"Task script must evaluate to a dict, got {type(val).__name__}")
    return val


def eval_condition(expr: str | None, ctx: ContextStack) -> bool:
    if not expr:
        return True
    mod = sl.Module()
    from flow_engine.engine.starlark_glue import _attach_builtins, cf_guard, inject_resolve

    inject_resolve(mod, ctx)
    _attach_sdk_python(mod)
    _attach_builtins(mod)
    glb = _globals_main()
    ast = _parse_cached("cond.star", f"({expr})")
    file_loader, _ = build_file_loader()
    with cf_guard():
        val = sl.eval(mod, ast, glb, file_loader=file_loader)
    return bool(val)


def eval_iterable_expr(expr: str, ctx: ContextStack) -> list[Any]:
    mod = sl.Module()
    from flow_engine.engine.starlark_glue import _attach_builtins, cf_guard, inject_resolve

    inject_resolve(mod, ctx)
    _attach_sdk_python(mod)
    _attach_builtins(mod)
    glb = _globals_main()
    ast = _parse_cached("iter.star", f"({expr})")
    file_loader, _ = build_file_loader()
    with cf_guard():
        val = sl.eval(mod, ast, glb, file_loader=file_loader)
    return list(val)


def run_hook_script(snippet: str | None, ctx: ContextStack, extra: dict[str, Any] | None = None) -> None:
    if not snippet:
        return
    mod = sl.Module()
    from flow_engine.engine.starlark_glue import _attach_builtins, cf_guard, inject_resolve

    inject_resolve(mod, ctx)
    if extra:
        for k, v in extra.items():
            mod[k] = v
    _attach_builtins(mod)
    _attach_sdk_python(mod)
    glb = _globals_main()
    ast = _parse_cached("hook.star", snippet)
    file_loader, _ = build_file_loader()
    with cf_guard():
        sl.eval(mod, ast, glb, file_loader=file_loader)


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
