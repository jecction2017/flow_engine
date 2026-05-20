"""Serialize lookup tables to JSON / CSV / Excel bytes."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from flow_engine.lookup.lookup_store import LookupStoreError


def _collect_columns(rows: list[dict[str, Any]], schema: dict[str, Any] | None) -> list[str]:
    cols: list[str] = []
    seen: set[str] = set()
    if schema and isinstance(schema.get("properties"), dict):
        for key in schema["properties"]:
            if isinstance(key, str) and key not in seen:
                seen.add(key)
                cols.append(key)
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                cols.append(key)
    return cols


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def table_to_bytes(table: dict[str, Any], *, format: str) -> tuple[bytes, str, str]:  # noqa: A002
    """Return ``(payload, media_type, filename_extension)``."""
    kind = (format or "").strip().lower()
    if kind not in ("json", "csv", "xlsx"):
        raise LookupStoreError("format must be json, csv, or xlsx")

    rows = table.get("rows")
    if not isinstance(rows, list):
        raise LookupStoreError("missing 'rows'")
    schema = table.get("schema")
    schema_obj = schema if isinstance(schema, dict) else None

    if kind == "json":
        payload = {"schema": schema_obj or {"type": "object", "properties": {}}, "rows": rows}
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return data, "application/json; charset=utf-8", "json"

    columns = _collect_columns(rows, schema_obj)
    if kind == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            if not isinstance(row, dict):
                continue
            writer.writerow({col: _cell_text(row.get(col)) for col in columns})
        return buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "csv"

    try:
        import openpyxl
    except ImportError as e:
        raise LookupStoreError("Excel export requires: pip install openpyxl") from e

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(columns)
    for row in rows:
        if not isinstance(row, dict):
            continue
        ws.append([row.get(col) for col in columns])
    out = io.BytesIO()
    wb.save(out)
    wb.close()
    return out.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
