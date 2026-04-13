"""Query and mutate lookup tables (used by HTTP API and Starlark ``lookup_query``)."""

from __future__ import annotations

import copy
from typing import Any

from flow_engine.lookup_store import LookupStoreError, get_lookup_store, normalize_table, validate_lookup_namespace

MAX_QUERY_ROWS = 10_000


def _filter_row(row: dict[str, Any], filt: dict[str, Any]) -> bool:
    for k, want in filt.items():
        key = str(k)
        if key not in row:
            return False
        if row[key] != want:
            return False
    return True


def lookup_query(namespace: str, filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # noqa: A002
    """Return rows matching **all** key equality constraints in ``filter`` (AND). Empty filter = all rows (capped)."""
    validate_lookup_namespace(namespace)
    filt = filter or {}
    if not isinstance(filt, dict):
        raise LookupStoreError("filter must be a dict")
    filt = {str(k): copy.deepcopy(v) for k, v in filt.items()}
    table = get_lookup_store().read_table(namespace)
    rows = table.get("rows", [])
    if not filt:
        if len(rows) > MAX_QUERY_ROWS:
            return copy.deepcopy(rows[:MAX_QUERY_ROWS])
        return copy.deepcopy(rows)
    out = [r for r in rows if _filter_row(r, filt)]
    if len(out) > MAX_QUERY_ROWS:
        out = out[:MAX_QUERY_ROWS]
    return copy.deepcopy(out)


def put_table(namespace: str, body: dict[str, Any]) -> dict[str, Any]:
    validate_lookup_namespace(namespace)
    norm = normalize_table(body)
    get_lookup_store().write_table(namespace, norm)
    return norm


def append_rows(namespace: str, new_rows: list[dict[str, Any]]) -> dict[str, Any]:
    validate_lookup_namespace(namespace)
    if not isinstance(new_rows, list):
        raise LookupStoreError("rows must be a list")
    cur = get_lookup_store().read_table(namespace)
    merged_rows = list(cur.get("rows", []))
    for i, row in enumerate(new_rows):
        if not isinstance(row, dict):
            raise LookupStoreError(f"append row {i} must be an object")
        merged_rows.append({str(k): v for k, v in row.items()})
    fields = cur.get("fields") or []
    if not fields and merged_rows:
        fields = list(merged_rows[0].keys())
    out = {"fields": fields, "rows": merged_rows}
    norm = normalize_table(out)
    get_lookup_store().write_table(namespace, norm)
    return get_lookup_store().read_table(namespace)


def merge_imported_rows(
    namespace: str,
    imported: list[dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    mode_l = (mode or "replace").strip().lower()
    if mode_l not in ("replace", "append"):
        raise LookupStoreError("mode must be 'replace' or 'append'")
    if mode_l == "replace":
        norm = normalize_table({"fields": [], "rows": imported})
        get_lookup_store().write_table(namespace, norm)
        return get_lookup_store().read_table(namespace)
    return append_rows(namespace, imported)
