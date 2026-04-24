"""Validate a single read-only SELECT before execution."""

from __future__ import annotations

import re

_ALLOWED_PREFIX = re.compile(r"^\s*select\b", re.IGNORECASE)

_DANGEROUS = [
    r"\binto\s+outfile\b",
    r"\binto\s+dumpfile\b",
    r"\bload_file\b",
    r"\bload\s+data\b",
    r"\bsleep\b",
    r"\bbenchmark\b",
    r"\bfor\s+update\b",
    r"\block\s+in\s+share\s+mode\b",
]


def _strip_string_literals(sql: str) -> str:
    def repl_single(m: re.Match[str]) -> str:
        return "__S__"

    def repl_double(m: re.Match[str]) -> str:
        return "__D__"

    out = re.sub(r"'(?:[^'\\]|\\.)*'", repl_single, sql)
    out = re.sub(r'"(?:[^"\\]|\\.)*"', repl_double, out)
    return out


def validate_select_statement(sql: str) -> tuple[bool, str | None]:
    """Return ``(ok, error_message)`` for a single SELECT."""
    raw = sql.strip()
    if not raw:
        return False, "Query is empty"

    stmt = raw[:-1].rstrip() if raw.endswith(";") else raw
    if ";" in stmt:
        return False, "Multiple statements are not allowed (remove ';' except optional trailing)"

    for bad in ("--", "/*", "*/"):
        if bad in stmt:
            return False, f"Comments are not allowed: {bad!r}"

    if not _ALLOWED_PREFIX.match(stmt):
        return False, "Query must start with SELECT"

    lowered = stmt.lower()
    if " into outfile" in lowered or " into dumpfile" in lowered:
        return False, "INTO OUTFILE / DUMPFILE is not allowed"

    sans_literals = _strip_string_literals(stmt)
    check = sans_literals.lower()
    for pat in _DANGEROUS:
        if re.search(pat, check, re.IGNORECASE):
            return False, f"Query contains forbidden pattern: {pat!r}"

    return True, None


def validate_schema_table_name(name: str) -> tuple[bool, str | None]:
    n = name.strip()
    if not n:
        return False, "table_name is empty"
    if not re.match(r"^[a-zA-Z0-9_]+$", n):
        return False, "table_name must contain only letters, digits, and underscore"
    if len(n) > 64:
        return False, "table_name is too long"
    return True, None


def sanitize_schema_keyword(keyword: str) -> tuple[str | None, str | None]:
    """Return a safe LIKE substring (alphanumeric + underscore only) or error."""
    k = keyword.strip()
    if not k:
        return None, "keyword is empty"
    if not re.match(r"^[a-zA-Z0-9_]+$", k):
        return None, "keyword must contain only letters, digits, and underscore"
    if len(k) > 64:
        return None, "keyword is too long"
    return k, None
