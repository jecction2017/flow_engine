"""Evaluate test assertions against flow ``global_ns`` after a run completes."""

from __future__ import annotations

import json
import re
from typing import Any

from flow_engine.engine.models import FlowState
from flow_engine.engine.starlark_glue import run_starfile_script


def _get_path(data: Any, path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _json_subset(expected: Any, actual: Any) -> bool:
    if expected is None:
        return True
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k, ev in expected.items():
            if k not in actual or not _json_subset(ev, actual[k]):
                return False
        return True
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) > len(actual):
            return False
        for i, ev in enumerate(expected):
            if not _json_subset(ev, actual[i]):
                return False
        return True
    return expected == actual


def _compare(op: str, actual: Any, expected: Any) -> bool:
    o = (op or "eq").lower()
    if o == "eq":
        return actual == expected
    if o == "ne":
        return actual != expected
    if o == "contains":
        return str(expected) in str(actual)
    if o == "regex":
        return re.search(str(expected), str(actual)) is not None
    if o in ("json_match", "json_subset"):
        return _json_subset(expected, actual)
    raise ValueError(f"unsupported assertion op: {op}")


def strip_expect_keys(row: dict[str, Any]) -> dict[str, Any]:
    """Remove ``_expect`` / ``_expect.*`` keys so they are not merged into global_ns."""
    return {
        k: v
        for k, v in row.items()
        if k != "_expect" and not str(k).startswith("_expect.")
    }


def row_derived_assertion_rules(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Build rules from optional lookup row ``_expect`` object or flat ``_expect.*`` keys."""
    rules: list[dict[str, Any]] = []
    nested = row.get("_expect")
    if isinstance(nested, dict) and nested.get("path"):
        rules.append(
            {
                "id": str(nested.get("id") or "_row._expect"),
                "op": str(nested.get("op") or "eq"),
                "path": str(nested["path"]),
                "expected": nested.get("equals", nested.get("expected")),
            }
        )
    path_k = "_expect.path"
    if path_k in row:
        rules.append(
            {
                "id": "_row._expect.path",
                "op": str(row.get("_expect.op") or "eq"),
                "path": str(row[path_k]),
                "expected": row.get("_expect.equals", row.get("_expect.expected")),
            }
        )
    return rules


def evaluate_assertions(
    *,
    flow_state: FlowState,
    global_ns: dict[str, Any],
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a structured evaluation payload for persistence on ``FeFlowRun.evaluation``."""
    if flow_state != FlowState.COMPLETED:
        return {
            "verdict": "fail",
            "flow_state": flow_state.value,
            "rules": [],
            "reason": "flow_not_completed",
        }

    if not rules:
        return {
            "verdict": "pass",
            "flow_state": flow_state.value,
            "rules": [],
        }

    rule_results: list[dict[str, Any]] = []
    all_pass = True
    for i, rule in enumerate(rules):
        rid = str(rule.get("id") or f"rule_{i}")
        op = str(rule.get("op") or "eq").lower()
        try:
            if op == "starlark":
                expr = str(rule.get("expr") or rule.get("starlark_expr") or "").strip()
                if not expr:
                    raise ValueError("empty starlark expr")
                raw = run_starfile_script(expr, extra_globals={"global_ns": global_ns})
                val = raw
                if isinstance(raw, dict) and "pass" in raw:
                    ok = bool(raw.get("pass"))
                    msg = str(raw.get("message") or "")
                else:
                    ok = bool(raw)
                    msg = "" if ok else f"expression is falsy: {json.dumps(raw, default=str)[:200]}"
            else:
                path = str(rule.get("path") or rule.get("context_path") or "").strip()
                if not path:
                    raise ValueError("missing path")
                actual = _get_path(global_ns, path)
                expected = rule.get("expected")
                ok = _compare(op, actual, expected)
                msg = "" if ok else f"path {path!r}: got {actual!r}, expected {expected!r} (op={op})"
            rule_results.append({"id": rid, "pass": ok, "message": msg})
            if not ok:
                all_pass = False
        except Exception as e:  # noqa: BLE001
            all_pass = False
            rule_results.append({"id": rid, "pass": False, "message": str(e)})

    return {
        "verdict": "pass" if all_pass else "fail",
        "flow_state": flow_state.value,
        "rules": rule_results,
    }


def eval_assertion_preview(expr: str, global_ns: dict[str, Any]) -> Any:
    """Debug helper: evaluate a Starlark snippet with ``global_ns`` bound."""
    return run_starfile_script(expr.strip(), extra_globals={"global_ns": global_ns})
