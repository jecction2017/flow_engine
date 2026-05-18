"""Extract top-level ``def`` names from Starlark user scripts (export symbols)."""

from __future__ import annotations

import re

_DEF_RE = re.compile(r"^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", re.MULTILINE)


def extract_starlark_export_functions(content: str) -> list[str]:
    """Return module-level function names in source order, deduplicated."""
    seen: set[str] = set()
    out: list[str] = []
    for name in _DEF_RE.findall(content or ""):
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out
