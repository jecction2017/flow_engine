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


@dataclass(frozen=True)
class PythonBuiltinSpec:
    id: str
    starlark_name: str
    category: str
    summary: str
    signature: tuple[BuiltinArgSpec, ...] = field(default_factory=tuple)
    returns: str = "any"
    side_effects: str = "none"


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
            }
        )
    return docs
