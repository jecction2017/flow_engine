"""Query and mutate lookup tables (used by HTTP API and Starlark ``lookup_query``)."""

from __future__ import annotations

import ast
import copy
import re
from typing import Any

from flow_engine.lookup.lookup_store import LookupStoreError, get_lookup_store, normalize_table, validate_lookup_namespace

MAX_QUERY_ROWS = 10_000
_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _filter_row(row: dict[str, Any], filt: dict[str, Any]) -> bool:
    for k, want in filt.items():
        key = str(k)
        if key not in row:
            return False
        if row[key] != want:
            return False
    return True


def _parse_filter_expr(expr: str) -> list[list[tuple[str, str, Any]]]:
    text = (expr or "").strip()
    if not text:
        return []
    groups = [g.strip() for g in text.split("||") if g.strip()]
    if not groups:
        return []
    out: list[list[tuple[str, str, Any]]] = []
    for group in groups:
        clauses = [c.strip() for c in group.split("&&") if c.strip()]
        if not clauses:
            continue
        and_clauses: list[tuple[str, str, Any]] = []
        for c in clauses:
            if " not in " in c:
                field, rhs = c.split(" not in ", 1)
                field = field.strip()
                if not _FIELD_RE.match(field):
                    raise LookupStoreError(f"invalid filter field: {field}")
                try:
                    values = ast.literal_eval(rhs.strip())
                except (ValueError, SyntaxError) as e:
                    raise LookupStoreError(f"invalid 'not in' expression: {c}") from e
                if not isinstance(values, (list, tuple, set)):
                    raise LookupStoreError(f"'not in' expression must use list/tuple/set: {c}")
                and_clauses.append((field, "not_in", list(values)))
                continue
            if " in " in c:
                field, rhs = c.split(" in ", 1)
                field = field.strip()
                if not _FIELD_RE.match(field):
                    raise LookupStoreError(f"invalid filter field: {field}")
                try:
                    values = ast.literal_eval(rhs.strip())
                except (ValueError, SyntaxError) as e:
                    raise LookupStoreError(f"invalid 'in' expression: {c}") from e
                if not isinstance(values, (list, tuple, set)):
                    raise LookupStoreError(f"'in' expression must use list/tuple/set: {c}")
                and_clauses.append((field, "in", list(values)))
                continue
            for token, op_name in (("==", "eq"), ("!=", "ne"), (">=", "ge"), ("<=", "le"), (">", "gt"), ("<", "lt")):
                if token in c:
                    field, rhs = c.split(token, 1)
                    field = field.strip()
                    if not _FIELD_RE.match(field):
                        raise LookupStoreError(f"invalid filter field: {field}")
                    try:
                        value = ast.literal_eval(rhs.strip())
                    except (ValueError, SyntaxError) as e:
                        raise LookupStoreError(f"invalid '{token}' expression: {c}") from e
                    and_clauses.append((field, op_name, value))
                    break
            else:
                raise LookupStoreError(f"unsupported filter clause: {c}")
        out.append(and_clauses)
    return out


def _match_expr(row: dict[str, Any], groups: list[list[tuple[str, str, Any]]]) -> bool:
    for clauses in groups:
        matched = True
        for field, op, rhs in clauses:
            if field not in row:
                matched = False
                break
            value = row[field]
            if op == "eq" and value != rhs:
                matched = False
                break
            if op == "ne" and value == rhs:
                matched = False
                break
            try:
                if op == "gt" and not (value > rhs):
                    matched = False
                    break
                if op == "ge" and not (value >= rhs):
                    matched = False
                    break
                if op == "lt" and not (value < rhs):
                    matched = False
                    break
                if op == "le" and not (value <= rhs):
                    matched = False
                    break
            except TypeError:
                matched = False
                break
            if op == "in" and value not in rhs:
                matched = False
                break
            if op == "not_in" and value in rhs:
                matched = False
                break
        if matched:
            return True
    return False


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


def lookup_query_page(  # noqa: A002
    namespace: str,
    filter: dict[str, Any] | str | None = None,
    *,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Query lookup rows with server-side pagination."""
    validate_lookup_namespace(namespace)
    if offset < 0:
        raise LookupStoreError("offset must be >= 0")
    if limit <= 0:
        raise LookupStoreError("limit must be > 0")
    if limit > MAX_QUERY_ROWS:
        raise LookupStoreError(f"limit must be <= {MAX_QUERY_ROWS}")

    raw_filter = filter or {}
    table = get_lookup_store().read_table(namespace)
    rows = table.get("rows", [])

    if isinstance(raw_filter, str):
        clauses = _parse_filter_expr(raw_filter)
        if not clauses:
            matched = rows
        else:
            matched = [r for r in rows if _match_expr(r, clauses)]
    elif isinstance(raw_filter, dict):
        filt = {str(k): copy.deepcopy(v) for k, v in raw_filter.items()}
        if not filt:
            matched = rows
        else:
            matched = [r for r in rows if _filter_row(r, filt)]
    else:
        raise LookupStoreError("filter must be a dict or expression string")

    if not raw_filter:
        matched = rows

    total = len(matched)
    page_rows = matched[offset : offset + limit]
    has_more = (offset + len(page_rows)) < total
    return {
        "schema": copy.deepcopy(table.get("schema", {"type": "object", "properties": {}})),
        "rows": copy.deepcopy(page_rows),
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
    }


def put_table(namespace: str, body: dict[str, Any], *, profile: str | None = None) -> dict[str, Any]:
    validate_lookup_namespace(namespace)
    norm = normalize_table(body)
    get_lookup_store().write_table(namespace, norm, profile=profile)
    return norm


def update_table_schema(namespace: str, schema: dict[str, Any], *, profile: str | None = None) -> dict[str, Any]:
    validate_lookup_namespace(namespace)
    if not isinstance(schema, dict):
        raise LookupStoreError("schema must be a JSON object")
    cur = get_lookup_store().read_table(namespace, profile=profile)
    out = {"schema": schema, "rows": list(cur.get("rows", []))}
    norm = normalize_table(out)
    get_lookup_store().write_table(namespace, norm, profile=profile)
    return {"schema": norm["schema"], "rows_count": len(norm.get("rows", []))}


def append_rows(namespace: str, new_rows: list[dict[str, Any]], *, profile: str | None = None) -> dict[str, Any]:
    validate_lookup_namespace(namespace)
    if not isinstance(new_rows, list):
        raise LookupStoreError("rows must be a list")
    cur = get_lookup_store().read_table(namespace, profile=profile)
    merged_rows = list(cur.get("rows", []))
    for i, row in enumerate(new_rows):
        if not isinstance(row, dict):
            raise LookupStoreError(f"append row {i} must be an object")
        merged_rows.append({str(k): v for k, v in row.items()})
    
    schema = cur.get("schema")
    if not schema and merged_rows:
        schema = {
            "type": "object",
            "properties": {str(k): {"type": "string"} for k in merged_rows[0].keys()}
        }
    out = {"schema": schema or {"type": "object", "properties": {}}, "rows": merged_rows}
    norm = normalize_table(out)
    get_lookup_store().write_table(namespace, norm, profile=profile)
    return get_lookup_store().read_table(namespace, profile=profile)


def delete_rows(
    namespace: str,
    rows_to_delete: list[dict[str, Any]],
    *,
    profile: str | None = None,
) -> dict[str, Any]:
    """Delete rows by exact object match; duplicates are removed one-by-one."""
    validate_lookup_namespace(namespace)
    if not isinstance(rows_to_delete, list):
        raise LookupStoreError("rows must be a list")
    delete_pool: list[dict[str, Any]] = []
    for i, row in enumerate(rows_to_delete):
        if not isinstance(row, dict):
            raise LookupStoreError(f"delete row {i} must be an object")
        delete_pool.append({str(k): copy.deepcopy(v) for k, v in row.items()})

    table = get_lookup_store().read_table(namespace, profile=profile)
    current_rows = list(table.get("rows", []))
    kept_rows: list[dict[str, Any]] = []
    removed = 0
    pending = list(delete_pool)
    for row in current_rows:
        try:
            idx = pending.index(row)
        except ValueError:
            kept_rows.append(row)
            continue
        pending.pop(idx)
        removed += 1

    out = {"schema": table.get("schema", {"type": "object", "properties": {}}), "rows": kept_rows}
    norm = normalize_table(out)
    get_lookup_store().write_table(namespace, norm, profile=profile)
    return {"removed": removed, "remaining": len(kept_rows)}


def delete_rows_by_filter(
    namespace: str,
    filter: dict[str, Any] | str | None = None,  # noqa: A002
    *,
    profile: str | None = None,
) -> dict[str, Any]:
    """Delete all rows matching equality filter. Empty filter deletes all rows."""
    validate_lookup_namespace(namespace)
    raw_filter = filter or {}

    table = get_lookup_store().read_table(namespace, profile=profile)
    current_rows = list(table.get("rows", []))
    if not raw_filter:
        kept_rows: list[dict[str, Any]] = []
        removed = len(current_rows)
    elif isinstance(raw_filter, str):
        clauses = _parse_filter_expr(raw_filter)
        kept_rows = [row for row in current_rows if not _match_expr(row, clauses)]
        removed = len(current_rows) - len(kept_rows)
    elif isinstance(raw_filter, dict):
        filt = {str(k): copy.deepcopy(v) for k, v in raw_filter.items()}
        kept_rows = [row for row in current_rows if not _filter_row(row, filt)]
        removed = len(current_rows) - len(kept_rows)
    else:
        raise LookupStoreError("filter must be a dict or expression string")

    out = {"schema": table.get("schema", {"type": "object", "properties": {}}), "rows": kept_rows}
    norm = normalize_table(out)
    get_lookup_store().write_table(namespace, norm, profile=profile)
    return {"removed": removed, "remaining": len(kept_rows)}


def merge_imported_rows(
    namespace: str,
    imported: list[dict[str, Any]],
    *,
    mode: str,
    profile: str | None = None,
) -> dict[str, Any]:
    mode_l = (mode or "replace").strip().lower()
    if mode_l not in ("replace", "append"):
        raise LookupStoreError("mode must be 'replace' or 'append'")
    if mode_l == "replace":
        norm = normalize_table({"schema": {"type": "object", "properties": {}}, "rows": imported})
        get_lookup_store().write_table(namespace, norm, profile=profile)
        return get_lookup_store().read_table(namespace, profile=profile)
    return append_rows(namespace, imported, profile=profile)
