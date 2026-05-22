"""Map an input record (lookup row, decoded message payload, ...) into flow global_ns fragment.

Same semantics as Test Center ``context_mapping`` — one implementation for batch test
and subscription ingress.
"""

from __future__ import annotations

from typing import Any


def apply_context_mapping(
    row: dict[str, Any],
    mapping: dict[str, Any] | None,
    *,
    run_mode: Any = None,
    capability_policy: Any = None,
) -> dict[str, Any]:
    """Map *row* to a dict merged into ``runtime.ctx.global_ns`` (not including system fields)."""
    if not mapping:
        return dict(row)
    mode = str(mapping.get("mode") or "spread")
    if mode == "spread":
        return dict(row)
    if mode == "wrap":
        key = str(mapping.get("wrap_key") or "input").strip() or "input"
        wrap_as_list = bool(mapping.get("wrap_as_list"))
        return {key: [dict(row)] if wrap_as_list else dict(row)}
    if mode == "rules":
        rules = mapping.get("rules") or []
        if not isinstance(rules, list):
            return dict(row)
        out: dict[str, Any] = {}

        def set_dotted(root: dict[str, Any], path: str, value: Any) -> None:
            parts = [p.strip() for p in path.split(".") if p.strip()]
            if not parts:
                return
            cur: dict[str, Any] = root
            for p in parts[:-1]:
                nxt = cur.get(p)
                if nxt is None or not isinstance(nxt, dict):
                    fresh: dict[str, Any] = {}
                    cur[p] = fresh
                    cur = fresh
                else:
                    cur = nxt
            cur[parts[-1]] = value

        for r in rules:
            if not isinstance(r, dict):
                continue
            src = str(r.get("source") or "").strip()
            tgt = str(r.get("target") or "").strip()
            if not src or not tgt:
                continue
            if src not in row:
                continue
            set_dotted(out, tgt, row.get(src))
        return out
    if mode == "script":
        script = str(mapping.get("script") or "").strip()
        if not script:
            raise ValueError("context_mapping script mode requires non-empty script")
        from flow_engine.starlark_sdk.runtime import eval_transform_script

        user_ctx = eval_transform_script(
            script,
            {"payload": dict(row)},
            run_mode=run_mode,
            capability_policy=capability_policy,
        )
        if not isinstance(user_ctx, dict):
            raise TypeError("context_mapping script must return a dict")
        return user_ctx
    return dict(row)
