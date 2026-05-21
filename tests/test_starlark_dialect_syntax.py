"""Verify Starlark dialect syntax constraints (starlark-pyo3 standard + load)."""

from __future__ import annotations

from pathlib import Path

import pytest
import starlark as sl

from flow_engine.engine.context import ContextStack
from flow_engine.starlark_sdk.loader import dialect_with_load
from flow_engine.starlark_sdk.runtime import eval_task_script


def _parse(src: str, label: str = "test.star") -> None:
    sl.parse(label, src, dialect=dialect_with_load())


# --- parse: must succeed ---

@pytest.mark.parametrize(
    "src",
    [
        'def f():\n  if True:\n    return 1\n  return 0\n{"a": f()}',
        'x = 1 if True else 0\n{"a": x}',
        '{"a": [x for x in [1, 2, 3]]}',
        '{"a": {k: k for k in ["a", "b"]}}',
        'x = 1\n{"a": x}',
        '{"a": 1}',
        'def f(*args):\n  return args\n{"a": f(1, 2)}',
        'def f(**kw):\n  return kw\n{"a": f(a=1)}',
        'def f(a=1):\n  return a\n{"a": f()}',
        'load("internal://lib/helpers.star", "double_int")\n{"a": double_int(2)}',
        'f = lambda x: x\n{"a": f(1)}',
        "x += 1\n{\"a\": x}",
        'x = []\nx = x + [1]\n{"a": x}',
        's = "a\\nb"\n{"a": s}',
        '{"a": True and False or True}',
        '{"a": "b" in {"b": 1}}',
        '{"a": None}',
        'def outer():\n  def inner():\n    return 1\n  return inner()\n{"a": outer()}',
    ],
)
def test_parse_valid(src: str) -> None:
    _parse(src)


# --- parse: must fail (standard dialect, no top-level control flow) ---

@pytest.mark.parametrize(
    "src",
    [
        'if True:\n  x = 1\n{"a": 1}',
        'for i in [1, 2]:\n  x = i\n{"a": 1}',
        'while False:\n  pass\n{"a": 1}',
        "class Foo:\n  pass\n{\"a\": 1}",
        'try:\n  x = 1\nexcept:\n  x = 0\n{"a": x}',
        'import json\n{"a": 1}',
        "assert True\n{\"a\": 1}",
        'global x\nx = 1\n{"a": x}',
        'def f():\n  nonlocal x\n  return x\nx = 1\nf()\n{"a": 1}',
    ],
)
def test_parse_invalid(src: str) -> None:
    with pytest.raises(sl.StarlarkError):
        _parse(src)


def test_kafka_example_invalid_top_level_if() -> None:
    path = Path("examples/kafka_simple_alarms/starlark_kafka_receive_test.star")
    src = path.read_text(encoding="utf-8")
    with pytest.raises(sl.StarlarkError, match="outside"):
        _parse(src)


# --- features that fail at parse or eval ---

@pytest.mark.parametrize(
    "src",
    [
        'x = 1\n{"a": f"{x}"}',
        '{"a": 1 is 1}',
        '{"a": 2 ** 3}',
        "a, *rest = [1, 2, 3]\n{\"a\": rest}",
    ],
)
def test_unsupported_expressions_fail(src: str) -> None:
    with pytest.raises((sl.StarlarkError, SyntaxError)):
        _parse(src)


def test_top_level_if_refactor_evals() -> None:
    """Pattern agents should use instead of top-level if/for."""
    script = """
def build():
    recv = {"ok": True, "data": {"messages": [{"value": {"id": 1}}]}}
    alarms = []
    if "ok" in recv and recv["ok"]:
        for m in recv["data"]["messages"]:
            alarms = alarms + [m["value"]]
    return {"alarm_count": len(alarms), "alarms": alarms}

build()
""".strip()
    out, _ = eval_task_script(script, ContextStack(), {})
    assert out["alarm_count"] == 1
