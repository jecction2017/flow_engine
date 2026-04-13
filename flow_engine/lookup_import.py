"""Parse uploaded bytes into lookup row lists (JSON / CSV / Excel)."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from flow_engine.lookup_store import LookupStoreError


def _detect_format(filename: str, fmt: str) -> str:
    f = (fmt or "auto").strip().lower()
    if f in ("json", "csv", "xlsx"):
        return f
    name = (filename or "").lower()
    if name.endswith(".json"):
        return "json"
    if name.endswith(".csv"):
        return "csv"
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        return "xlsx"
    raise LookupStoreError("Cannot detect format: use .json, .csv, .xlsx or pass format=")


def _rows_from_json(data: bytes) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8-sig")
        obj: Any = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise LookupStoreError(f"Invalid JSON: {e}") from e
    if isinstance(obj, list):
        if not all(isinstance(x, dict) for x in obj):
            raise LookupStoreError("JSON array must contain only objects")
        return [dict(x) for x in obj]
    if isinstance(obj, dict) and "rows" in obj:
        rows = obj["rows"]
        if not isinstance(rows, list) or not all(isinstance(x, dict) for x in rows):
            raise LookupStoreError("'rows' must be a list of objects")
        return [dict(x) for x in rows]
    raise LookupStoreError("JSON must be an array of objects or {\"rows\": [...]}")


def _rows_from_csv(data: bytes) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise LookupStoreError(f"CSV must be UTF-8: {e}") from e
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return []
    rows: list[dict[str, Any]] = []
    for raw in reader:
        row = {str(k): (v if v != "" else None) for k, v in raw.items() if k is not None}
        rows.append(row)
    return rows


def _rows_from_xlsx(data: bytes) -> list[dict[str, Any]]:
    try:
        import openpyxl
    except ImportError as e:
        raise LookupStoreError("Excel import requires: pip install openpyxl") from e
    from io import BytesIO

    wb = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True)
    try:
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration:
            return []
        keys = [str(c).strip() if c is not None else "" for c in header]
        keys = [k for k in keys if k]
        if not keys:
            return []
        out: list[dict[str, Any]] = []
        for tup in rows_iter:
            if tup is None:
                continue
            item: dict[str, Any] = {}
            empty = True
            for i, key in enumerate(keys):
                if i < len(tup):
                    val = tup[i]
                    if val is not None and str(val).strip() != "":
                        empty = False
                    item[key] = val
                else:
                    item[key] = None
            if empty and not any(v is not None and str(v).strip() != "" for v in item.values()):
                continue
            out.append(item)
        return out
    finally:
        wb.close()


def rows_from_bytes(data: bytes, *, filename: str = "", format: str = "auto") -> list[dict[str, Any]]:  # noqa: A002
    kind = _detect_format(filename, format)
    if kind == "json":
        return _rows_from_json(data)
    if kind == "csv":
        return _rows_from_csv(data)
    if kind == "xlsx":
        return _rows_from_xlsx(data)
    raise LookupStoreError(f"Unsupported format: {kind}")
