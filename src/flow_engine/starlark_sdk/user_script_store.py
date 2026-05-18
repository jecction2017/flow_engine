"""MySQL-backed Starlark user script store.

Uses table: fe_user_script
  tenant   — 对应 user://<tenant>/ 路径段
  rel_path — 相对路径，如 my_lib/utils.star
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from flow_engine.db.models import FeUserScript
from flow_engine.db.session import db_session
from flow_engine.starlark_sdk.user_script_exports import extract_starlark_export_functions

_TENANT = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
_SAFE_REL = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_./-]*\.star$")
_EXPORT_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _normalize_export_functions(names: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = raw.strip()
        if not name or name in seen:
            continue
        if not _EXPORT_NAME.match(name):
            raise ValueError(f"Invalid export symbol: {name!r}")
        seen.add(name)
        out.append(name)
    return out


def validate_tenant(tenant: str) -> str:
    if not tenant or not _TENANT.match(tenant):
        raise ValueError(f"Invalid tenant: {tenant!r}")
    return tenant


def validate_script_path(rel_path: str) -> str:
    if not rel_path or not _SAFE_REL.match(rel_path):
        raise ValueError(
            f"Invalid script path {rel_path!r}; must end in .star and use safe characters"
        )
    return rel_path


class UserScriptStore:
    """MySQL-backed user Starlark script store (fe_user_script)."""

    def list_scripts(self, tenant: str | None = None) -> list[dict[str, Any]]:
        """Return list of {tenant, rel_path} dicts ordered by tenant, rel_path."""
        with db_session() as s:
            stmt = select(FeUserScript).where(FeUserScript.deleted_at.is_(None))
            if tenant is not None:
                validate_tenant(tenant)
                stmt = stmt.where(FeUserScript.tenant == tenant)
            stmt = stmt.order_by(FeUserScript.tenant, FeUserScript.rel_path)
            rows = s.execute(stmt).scalars().all()
            return [{"tenant": r.tenant, "rel_path": r.rel_path} for r in rows]

    def list_rel_paths(self) -> list[str]:
        """Return paths as 'tenant/rel_path' strings (used by user_script_list builtin)."""
        return [f"{r['tenant']}/{r['rel_path']}" for r in self.list_scripts()]

    def exists(self, tenant: str, rel_path: str) -> bool:
        validate_tenant(tenant)
        validate_script_path(rel_path)
        with db_session() as s:
            stmt = (
                select(FeUserScript.id)
                .where(FeUserScript.tenant == tenant)
                .where(FeUserScript.rel_path == rel_path)
                .where(FeUserScript.deleted_at.is_(None))
            )
            return s.execute(stmt).scalar_one_or_none() is not None

    def get_script(self, tenant: str, rel_path: str) -> str:
        return self.get_script_record(tenant, rel_path)["content"]

    def get_script_record(self, tenant: str, rel_path: str) -> dict[str, Any]:
        validate_tenant(tenant)
        validate_script_path(rel_path)
        with db_session() as s:
            stmt = (
                select(FeUserScript)
                .where(FeUserScript.tenant == tenant)
                .where(FeUserScript.rel_path == rel_path)
                .where(FeUserScript.deleted_at.is_(None))
            )
            row = s.execute(stmt).scalar_one_or_none()
            if row is None:
                raise FileNotFoundError(f"Script not found: user://{tenant}/{rel_path}")
            return _record_from_row(row)

    def put_script(
        self,
        tenant: str,
        rel_path: str,
        content: str,
        *,
        description: str | None = None,
        export_functions: list[str] | None = None,
    ) -> None:
        validate_tenant(tenant)
        validate_script_path(rel_path)
        if export_functions is not None:
            exports = _normalize_export_functions(export_functions)
        else:
            exports = extract_starlark_export_functions(content)
        desc = (description or "").strip() or None
        with db_session() as s:
            stmt = (
                select(FeUserScript)
                .where(FeUserScript.tenant == tenant)
                .where(FeUserScript.rel_path == rel_path)
                .where(FeUserScript.deleted_at.is_(None))
            )
            row = s.execute(stmt).scalar_one_or_none()
            if row is None:
                s.add(
                    FeUserScript(
                        tenant=tenant,
                        rel_path=rel_path,
                        content=content,
                        description=desc,
                        export_functions=exports,
                    )
                )
            else:
                row.content = content
                row.description = desc
                row.export_functions = exports

    def delete_script(self, tenant: str, rel_path: str) -> bool:
        """Soft-delete one script. Returns True if a row was updated."""
        validate_tenant(tenant)
        validate_script_path(rel_path)
        now = datetime.now(timezone.utc)
        with db_session() as s:
            stmt = (
                select(FeUserScript)
                .where(FeUserScript.tenant == tenant)
                .where(FeUserScript.rel_path == rel_path)
                .where(FeUserScript.deleted_at.is_(None))
            )
            row = s.execute(stmt).scalar_one_or_none()
            if row is None:
                return False
            row.deleted_at = now
            return True

    def delete_module(self, tenant: str) -> int:
        """Soft-delete all scripts in a module (tenant). Returns count deleted."""
        validate_tenant(tenant)
        now = datetime.now(timezone.utc)
        with db_session() as s:
            stmt = (
                select(FeUserScript)
                .where(FeUserScript.tenant == tenant)
                .where(FeUserScript.deleted_at.is_(None))
            )
            rows = s.execute(stmt).scalars().all()
            for row in rows:
                row.deleted_at = now
            return len(rows)


def _record_from_row(row: FeUserScript) -> dict[str, Any]:
    exports = row.export_functions
    if not isinstance(exports, list):
        exports = []
    return {
        "tenant": row.tenant,
        "rel_path": row.rel_path,
        "path": f"{row.tenant}/{row.rel_path}",
        "content": row.content,
        "description": row.description or "",
        "export_functions": [str(x) for x in exports],
    }


_store_cache: UserScriptStore | None = None


def get_user_script_store() -> UserScriptStore:
    global _store_cache
    if _store_cache is None:
        _store_cache = UserScriptStore()
    return _store_cache
