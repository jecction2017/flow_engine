"""Validate a single MySQL DML statement before execution (defense in depth)."""

from __future__ import annotations

import re

_ALLOWED_PREFIX = re.compile(r"^\s*(insert|update|delete)\b", re.IGNORECASE)

# After stripping string literals, reject DDL / privilege / dangerous patterns.
_DANGEROUS = [
    r"\bdrop\b",
    r"\balter\b",
    r"\bcreate\b",
    r"\btruncate\b",
    r"\brename\b",
    r"\bgrant\b",
    r"\brevoke\b",
    r"\binto\s+outfile\b",
    r"\binto\s+dumpfile\b",
    r"\bload_file\b",
    r"\bload\s+data\b",
    r"\bsleep\b",
    r"\bbenchmark\b",
]


def _strip_string_literals(sql: str) -> str:
    """Replace '...' and \"...\" with placeholders to avoid false positives inside values."""

    def repl_single(m: re.Match[str]) -> str:
        return "__S__"

    def repl_double(m: re.Match[str]) -> str:
        return "__D__"

    out = re.sub(r"'(?:[^'\\]|\\.)*'", repl_single, sql)
    out = re.sub(r'"(?:[^"\\]|\\.)*"', repl_double, out)
    return out


def validate_dml_statement(sql: str) -> tuple[bool, str | None]:
    """Return ``(ok, error_message)``."""
    raw = sql.strip()
    if not raw:
        return False, "Statement is empty"

    stmt = raw[:-1].rstrip() if raw.endswith(";") else raw
    if ";" in stmt:
        return False, "Multiple statements are not allowed (remove ';' except optional trailing)"

    for bad in ("--", "/*", "*/"):
        if bad in stmt:
            return False, f"Comments are not allowed: {bad!r}"

    if not _ALLOWED_PREFIX.match(stmt):
        return False, "Statement must start with INSERT, UPDATE, or DELETE"

    lowered = stmt.lower()
    if " into outfile" in lowered or " into dumpfile" in lowered:
        return False, "INTO OUTFILE / DUMPFILE is not allowed"

    sans_literals = _strip_string_literals(stmt)
    check = sans_literals.lower()
    for pat in _DANGEROUS:
        if re.search(pat, check, re.IGNORECASE):
            return False, f"Statement contains forbidden pattern: {pat!r}"

    return True, None
