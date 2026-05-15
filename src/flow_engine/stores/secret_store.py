"""MySQL-backed secret definitions (fe_secret), scoped by profile."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from flow_engine.engine.exceptions import FlowEngineError
from flow_engine.stores.profile_store import validate_profile_id

SECRET_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SECRET_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class SecretStoreError(FlowEngineError):
    """Invalid secret name/type or missing row."""


@dataclass(frozen=True)
class SecretRecord:
    profile_code: str
    secret_name: str
    secret_type: str
    secret_data: dict[str, Any]


def validate_secret_name(name: str) -> str:
    n = (name or "").strip().lower()
    if not SECRET_NAME_PATTERN.fullmatch(n):
        raise SecretStoreError(
            f"Invalid secret_name {name!r}; expected ^[a-z][a-z0-9_-]{{0,63}}$"
        )
    return n


def validate_secret_type(secret_type: str) -> str:
    from flow_engine.secrets.registry import list_secret_types

    t = (secret_type or "").strip().lower()
    if not SECRET_TYPE_PATTERN.fullmatch(t):
        raise SecretStoreError(
            f"Invalid secret_type {secret_type!r}; expected ^[a-z][a-z0-9_-]{{0,63}}$"
        )
    if t not in list_secret_types():
        known = ", ".join(list_secret_types()) or "(none)"
        raise SecretStoreError(f"Unknown secret_type {t!r}; registered: {known}")
    return t


def _validate_secret_data(data: Any) -> dict[str, Any]:
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SecretStoreError("secret_data must be a JSON object")
    return data


class SecretStore:
    """CRUD for ``fe_secret`` (per profile)."""

    directory: str = "mysql://secrets"

    def list_secrets(self, *, profile: str) -> list[SecretRecord]:
        from sqlalchemy import select

        from flow_engine.db.models import FeSecret
        from flow_engine.db.session import db_session

        pid = validate_profile_id(profile)
        with db_session() as s:
            rows = s.execute(
                select(FeSecret)
                .where(FeSecret.profile_code == pid)
                .where(FeSecret.deleted_at.is_(None))
                .order_by(FeSecret.secret_name)
            ).scalars().all()
            out: list[SecretRecord] = []
            for r in rows:
                out.append(
                    SecretRecord(
                        profile_code=r.profile_code,
                        secret_name=r.secret_name,
                        secret_type=r.secret_type,
                        secret_data=_validate_secret_data(copy.deepcopy(r.secret_data)),
                    )
                )
            return out

    def get_secret(self, secret_name: str, *, profile: str) -> SecretRecord:
        from sqlalchemy import select

        from flow_engine.db.models import FeSecret
        from flow_engine.db.session import db_session

        pid = validate_profile_id(profile)
        name = validate_secret_name(secret_name)
        with db_session() as s:
            row = s.execute(
                select(FeSecret)
                .where(FeSecret.profile_code == pid)
                .where(FeSecret.secret_name == name)
                .where(FeSecret.deleted_at.is_(None))
            ).scalar_one_or_none()
            if row is None:
                raise SecretStoreError(
                    f"Secret not found: profile={pid!r} name={name!r}"
                )
            return SecretRecord(
                profile_code=row.profile_code,
                secret_name=row.secret_name,
                secret_type=row.secret_type,
                secret_data=_validate_secret_data(copy.deepcopy(row.secret_data)),
            )

    def put_secret(
        self,
        secret_name: str,
        secret_type: str,
        secret_data: dict[str, Any],
        *,
        profile: str,
    ) -> SecretRecord:
        from sqlalchemy import select

        from flow_engine.db.models import FeSecret
        from flow_engine.db.session import db_session

        pid = validate_profile_id(profile)
        name = validate_secret_name(secret_name)
        stype = validate_secret_type(secret_type)
        data = _validate_secret_data(secret_data)

        with db_session() as s:
            row = s.execute(
                select(FeSecret)
                .where(FeSecret.profile_code == pid)
                .where(FeSecret.secret_name == name)
                .where(FeSecret.deleted_at.is_(None))
            ).scalar_one_or_none()
            if row is None:
                row = FeSecret(
                    profile_code=pid,
                    secret_name=name,
                    secret_type=stype,
                    secret_data=data,
                )
                s.add(row)
            else:
                row.secret_type = stype
                row.secret_data = data
            s.flush()
            s.refresh(row)
            return SecretRecord(
                profile_code=row.profile_code,
                secret_name=row.secret_name,
                secret_type=row.secret_type,
                secret_data=_validate_secret_data(copy.deepcopy(row.secret_data)),
            )

    def delete_secret(self, secret_name: str, *, profile: str) -> None:
        from sqlalchemy import select

        from flow_engine.db.models import FeSecret
        from flow_engine.db.session import db_session

        pid = validate_profile_id(profile)
        name = validate_secret_name(secret_name)
        now = datetime.now(timezone.utc)
        with db_session() as s:
            row = s.execute(
                select(FeSecret)
                .where(FeSecret.profile_code == pid)
                .where(FeSecret.secret_name == name)
                .where(FeSecret.deleted_at.is_(None))
            ).scalar_one_or_none()
            if row is None:
                raise SecretStoreError(
                    f"Secret not found: profile={pid!r} name={name!r}"
                )
            row.deleted_at = now


_store_cache: SecretStore | None = None


def store() -> SecretStore:
    global _store_cache
    if _store_cache is None:
        _store_cache = SecretStore()
    return _store_cache


def invalidate_store_cache() -> None:
    global _store_cache
    _store_cache = None
