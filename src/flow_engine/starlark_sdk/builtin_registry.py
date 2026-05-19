"""Declarative registry for Python callables exposed to Starlark."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable


@dataclass(frozen=True)
class BuiltinArgSpec:
    name: str
    type: str
    required: bool = True


# How a registered callable is bound into a Starlark module at eval time:
# - guarded: capability + budget wrapper (default for side-effect builtins)
# - direct: attach as-is (log*, no budget/capability)
# - flow_control: raises flow interrupts; uses cf_guard unwrap (no capability)
# - context: documented in registry only; inject_resolve binds per ContextStack
ATTACH_GUARDED = "guarded"
ATTACH_DIRECT = "direct"
ATTACH_FLOW_CONTROL = "flow_control"
ATTACH_CONTEXT = "context"


@dataclass(frozen=True)
class PythonBuiltinSpec:
    id: str
    starlark_name: str
    category: str
    summary: str
    signature: tuple[BuiltinArgSpec, ...] = field(default_factory=tuple)
    returns: str = "any"
    side_effects: str = "none"
    attach_mode: str = ATTACH_GUARDED
    # SUPPRESS 命中时由 _guard_builtin 直接返回的值；函数体不执行。
    # ``side_effects == "none"`` 的 builtin 不会被检查 capability，本字段无意义。
    # 含可变值（dict/list）时 _guard_builtin 会按调用做浅拷贝，避免被脚本污染共享实例。
    suppress_result: Any = None


@dataclass(frozen=True)
class RegisteredBuiltin:
    spec: PythonBuiltinSpec
    fn: Callable[..., Any]


_LOCK = RLock()
_REGISTERED: dict[str, RegisteredBuiltin] = {}


def register_builtin(spec: PythonBuiltinSpec) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a Python function as a Starlark builtin."""

    def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        entry = RegisteredBuiltin(spec=spec, fn=fn)
        with _LOCK:
            prev = _REGISTERED.get(spec.starlark_name)
            if prev and prev.fn is not fn:
                raise ValueError(f"duplicate starlark builtin name: {spec.starlark_name}")
            _REGISTERED[spec.starlark_name] = entry
        return fn

    return _wrap


def list_registered_builtins() -> list[RegisteredBuiltin]:
    with _LOCK:
        return [v for _, v in sorted(_REGISTERED.items(), key=lambda kv: kv[0])]


def builtin_map() -> dict[str, Callable[..., Any]]:
    return {entry.spec.starlark_name: entry.fn for entry in list_registered_builtins()}


def registry_python_doc() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for entry in list_registered_builtins():
        docs.append(
            {
                "id": entry.spec.id,
                "starlark_name": entry.spec.starlark_name,
                "category": entry.spec.category,
                "summary": entry.spec.summary,
                "signature": [
                    {"name": a.name, "type": a.type, "required": a.required} for a in entry.spec.signature
                ],
                "returns": entry.spec.returns,
                "side_effects": entry.spec.side_effects,
                "attach_mode": entry.spec.attach_mode,
            }
        )
    return docs
