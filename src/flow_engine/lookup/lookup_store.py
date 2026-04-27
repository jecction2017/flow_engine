"""MySQL-backed lookup tables (tabular reference data per profile + namespace).

Uses tables:
  fe_lookup_ns  — namespace metadata + JSON Schema definition
  fe_lookup_row — individual data rows (soft-deleted on replace/delete)

⚠  put_table (replace) 会积累软删历史行；建议定期清理 deleted_at IS NOT NULL 的行。
"""

from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any

import jsonschema
from sqlalchemy import select

from flow_engine.db.models import FeLookupNs, FeLookupRow
from flow_engine.db.session import db_session
from flow_engine.engine.exceptions import FlowEngineError
from flow_engine.stores.profile_store import DEFAULT_PROFILE_ID, active_profile, validate_profile_id


class LookupStoreError(FlowEngineError):
    """Invalid lookup namespace or document shape."""


_NS = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def validate_lookup_namespace(ns: str) -> str:
    if not ns or not _NS.match(ns):
        raise LookupStoreError(
            "Invalid lookup namespace: use letters, digits, underscore or hyphen (max 64 chars).",
        )
    return ns


def _normalize_cell(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, list):
        return [_normalize_cell(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _normalize_cell(val) for k, val in v.items()}
    return str(v)


def normalize_table(raw: dict[str, Any]) -> dict[str, Any]:
    """Ensure ``schema`` (optional) and ``rows`` (list of flat dicts)."""
    if not isinstance(raw, dict):
        raise LookupStoreError("lookup table must be a JSON object")

    rows = raw.get("rows")
    if rows is None:
        raise LookupStoreError("missing 'rows'")
    if not isinstance(rows, list):
        raise LookupStoreError("'rows' must be a list")

    out_rows: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise LookupStoreError(f"row {i} must be an object")
        out_rows.append({str(k): _normalize_cell(v) for k, v in row.items()})

    out_schema = raw.get("schema")
    if out_schema is None:
        fields = raw.get("fields")
        props: dict[str, Any] = {}
        if isinstance(fields, list):
            for f in fields:
                if isinstance(f, str):
                    props[f] = {"type": "string"}
                elif isinstance(f, dict) and "name" in f:
                    props[str(f["name"])] = {
                        "type": str(f.get("type", "string")),
                        "description": str(f.get("description", "")),
                    }
        elif out_rows:
            props = {str(k): {"type": "string"} for k in out_rows[0].keys()}
        out_schema = {"type": "object", "properties": props}

    if not isinstance(out_schema, dict):
        raise LookupStoreError("'schema' must be a JSON object")

    try:
        jsonschema.Draft7Validator.check_schema(out_schema)
        validator = jsonschema.Draft7Validator(out_schema)
        for i, row in enumerate(out_rows):
            errors = list(validator.iter_errors(row))
            if errors:
                err = errors[0]
                path = ".".join(str(p) for p in err.path) if err.path else "root"
                raise LookupStoreError(f"Row {i} validation failed at '{path}': {err.message}")
    except jsonschema.exceptions.SchemaError as e:
        raise LookupStoreError(f"Invalid JSON Schema: {e.message}")

    return {"schema": out_schema, "rows": out_rows}


_store_cache: "LookupStore | None" = None


def invalidate_lookup_store_cache() -> None:
    global _store_cache
    _store_cache = None


class LookupStore:
    """MySQL-backed lookup store; each namespace is a row in fe_lookup_ns,
    each data row is a row in fe_lookup_row."""

    # directory 属性保持 API 兼容
    directory: str = "mysql://lookup"

    def _resolve_profile(self, profile_id: str | None) -> str:
        return validate_profile_id(profile_id or active_profile())

    def create_profile(self, profile_id: str) -> None:
        """No-op in MySQL backend; profiles are managed via GlobalProfileStore."""

    def list_namespaces(self, *, profile: str | None = None) -> list[str]:
        pid = self._resolve_profile(profile)
        with db_session() as s:
            stmt = (
                select(FeLookupNs.ns_code)
                .where(FeLookupNs.profile_code == pid)
                .where(FeLookupNs.deleted_at.is_(None))
                .order_by(FeLookupNs.ns_code)
            )
            return list(s.execute(stmt).scalars().all())

    def exists(self, ns: str, *, profile: str | None = None) -> bool:
        validate_lookup_namespace(ns)
        pid = self._resolve_profile(profile)
        with db_session() as s:
            stmt = (
                select(FeLookupNs.id)
                .where(FeLookupNs.profile_code == pid)
                .where(FeLookupNs.ns_code == ns)
                .where(FeLookupNs.deleted_at.is_(None))
            )
            return s.execute(stmt).scalar_one_or_none() is not None

    def read_table(self, ns: str, *, profile: str | None = None) -> dict[str, Any]:
        validate_lookup_namespace(ns)
        pid = self._resolve_profile(profile)
        with db_session() as s:
            ns_stmt = (
                select(FeLookupNs)
                .where(FeLookupNs.profile_code == pid)
                .where(FeLookupNs.ns_code == ns)
                .where(FeLookupNs.deleted_at.is_(None))
            )
            ns_row = s.execute(ns_stmt).scalar_one_or_none()
            if ns_row is None:
                return {"schema": {"type": "object", "properties": {}}, "rows": []}
            row_stmt = (
                select(FeLookupRow.row_data)
                .where(FeLookupRow.profile_code == pid)
                .where(FeLookupRow.ns_code == ns)
                .where(FeLookupRow.deleted_at.is_(None))
                .order_by(FeLookupRow.id)
            )
            rows = list(s.execute(row_stmt).scalars().all())
            return {
                "schema": copy.deepcopy(ns_row.schema_json),
                "rows": copy.deepcopy(rows),
            }

    def write_table(self, ns: str, table: dict[str, Any], *, profile: str | None = None) -> None:
        """Replace all rows; soft-delete existing rows then bulk-insert new ones."""
        norm = normalize_table(table)
        pid = self._resolve_profile(profile)
        now = datetime.now(timezone.utc)
        with db_session() as s:
            # Upsert namespace row
            ns_stmt = (
                select(FeLookupNs)
                .where(FeLookupNs.profile_code == pid)
                .where(FeLookupNs.ns_code == ns)
                .where(FeLookupNs.deleted_at.is_(None))
            )
            ns_row = s.execute(ns_stmt).scalar_one_or_none()
            if ns_row is None:
                ns_row = FeLookupNs(
                    profile_code=pid,
                    ns_code=ns,
                    schema_json=norm["schema"],
                )
                s.add(ns_row)
            else:
                ns_row.schema_json = norm["schema"]

            # Soft-delete existing rows
            old_stmt = (
                select(FeLookupRow)
                .where(FeLookupRow.profile_code == pid)
                .where(FeLookupRow.ns_code == ns)
                .where(FeLookupRow.deleted_at.is_(None))
            )
            for old_row in s.execute(old_stmt).scalars().all():
                old_row.deleted_at = now

            # Bulk-insert new rows
            for row_data in norm["rows"]:
                s.add(
                    FeLookupRow(
                        profile_code=pid,
                        ns_code=ns,
                        row_data=row_data,
                    )
                )

    def delete_namespace(self, ns: str, *, profile: str | None = None) -> None:
        validate_lookup_namespace(ns)
        pid = self._resolve_profile(profile)
        now = datetime.now(timezone.utc)
        with db_session() as s:
            ns_stmt = (
                select(FeLookupNs)
                .where(FeLookupNs.profile_code == pid)
                .where(FeLookupNs.ns_code == ns)
                .where(FeLookupNs.deleted_at.is_(None))
            )
            ns_row = s.execute(ns_stmt).scalar_one_or_none()
            if ns_row:
                ns_row.deleted_at = now

            row_stmt = (
                select(FeLookupRow)
                .where(FeLookupRow.profile_code == pid)
                .where(FeLookupRow.ns_code == ns)
                .where(FeLookupRow.deleted_at.is_(None))
            )
            for row in s.execute(row_stmt).scalars().all():
                row.deleted_at = now


def get_lookup_store() -> LookupStore:
    global _store_cache
    if _store_cache is None:
        _store_cache = LookupStore()
    return _store_cache
