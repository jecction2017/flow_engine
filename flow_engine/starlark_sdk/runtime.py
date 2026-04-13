"""Task / hook / condition evaluation with load() + SDK builtins."""

from __future__ import annotations

from typing import Any

import starlark as sl

from flow_engine.context import ContextStack
from flow_engine.exceptions import starlark_to_python
from flow_engine.starlark_sdk.loader import build_file_loader, dialect_with_load
from flow_engine.starlark_sdk.python_builtin_impl import PYTHON_BUILTINS


def _globals_main() -> sl.Globals:
    return sl.Globals.extended_by([sl.LibraryExtension.Json])


def _attach_sdk_python(mod: sl.Module) -> None:
    for name, fn in PYTHON_BUILTINS.items():
        mod.add_callable(name, fn)


def _prepare_module(mod: sl.Module, ctx: ContextStack, boundary_inputs: dict[str, str]) -> None:
    from flow_engine.starlark_glue import _attach_builtins, inject_context_paths, inject_resolve

    inject_context_paths(mod, ctx, boundary_inputs)
    inject_resolve(mod, ctx)
    _attach_builtins(mod)
    _attach_sdk_python(mod)


def eval_task_script(
    script: str,
    ctx: ContextStack,
    boundary_inputs: dict[str, str],
) -> dict[str, Any]:
    mod = sl.Module()
    _prepare_module(mod, ctx, boundary_inputs)
    file_loader, _cache = build_file_loader()
    glb = _globals_main()
    ast = sl.parse("task.star", script, dialect=dialect_with_load())
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
    from flow_engine.starlark_glue import inject_resolve

    inject_resolve(mod, ctx)
    _attach_sdk_python(mod)
    from flow_engine.starlark_glue import _attach_builtins

    _attach_builtins(mod)
    glb = _globals_main()
    ast = sl.parse("cond.star", f"({expr})", dialect=dialect_with_load())
    file_loader, _ = build_file_loader()
    val = sl.eval(mod, ast, glb, file_loader=file_loader)
    return bool(val)


def eval_iterable_expr(expr: str, ctx: ContextStack) -> list[Any]:
    mod = sl.Module()
    from flow_engine.starlark_glue import inject_resolve

    inject_resolve(mod, ctx)
    _attach_sdk_python(mod)
    from flow_engine.starlark_glue import _attach_builtins

    _attach_builtins(mod)
    glb = _globals_main()
    ast = sl.parse("iter.star", f"({expr})", dialect=dialect_with_load())
    file_loader, _ = build_file_loader()
    val = sl.eval(mod, ast, glb, file_loader=file_loader)
    return list(val)


def run_hook_script(snippet: str | None, ctx: ContextStack, extra: dict[str, Any] | None = None) -> None:
    if not snippet:
        return
    mod = sl.Module()
    from flow_engine.starlark_glue import inject_resolve

    inject_resolve(mod, ctx)
    if extra:
        for k, v in extra.items():
            mod[k] = v
    from flow_engine.starlark_glue import _attach_builtins

    _attach_builtins(mod)
    _attach_sdk_python(mod)
    glb = _globals_main()
    ast = sl.parse("hook.star", snippet, dialect=dialect_with_load())
    file_loader, _ = build_file_loader()
    sl.eval(mod, ast, glb, file_loader=file_loader)
