"""MySQL-backed global runtime profile configuration (dev/sit/prod, etc.).

Uses table: fe_env_profile
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import select

from flow_engine.db.models import FeEnvProfile
from flow_engine.db.session import db_session
from flow_engine.engine.exceptions import FlowEngineError

DEFAULT_PROFILE_ID = "default"
PROFILE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class ProfileConfigError(FlowEngineError):
    """Invalid profile id or broken profile config."""


def validate_profile_id(profile_id: str) -> str:
    pid = (profile_id or "").strip()
    if not PROFILE_ID_PATTERN.fullmatch(pid):
        raise ProfileConfigError(
            f"Invalid profile_id {profile_id!r}; expected ^[a-z][a-z0-9_-]{{0,63}}$"
        )
    return pid


class GlobalProfileStore:
    """MySQL-backed global profile store; each row in fe_env_profile is one environment."""

    def __init__(self) -> None:
        self._ensure_default_profile()

    def _ensure_default_profile(self) -> None:
        """Guarantee the 'default' profile row exists (idempotent)."""
        with db_session() as s:
            stmt = (
                select(FeEnvProfile)
                .where(FeEnvProfile.profile_code == DEFAULT_PROFILE_ID)
                .where(FeEnvProfile.deleted_at.is_(None))
            )
            row = s.execute(stmt).scalar_one_or_none()
            if row is None:
                s.add(
                    FeEnvProfile(
                        profile_code=DEFAULT_PROFILE_ID,
                        display_name="Default",
                        is_default=1,
                    )
                )

    def list_profiles(self) -> list[str]:
        with db_session() as s:
            stmt = (
                select(FeEnvProfile.profile_code)
                .where(FeEnvProfile.deleted_at.is_(None))
                .order_by(FeEnvProfile.profile_code)
            )
            return list(s.execute(stmt).scalars().all())

    def get_default_profile(self) -> str:
        with db_session() as s:
            stmt = (
                select(FeEnvProfile.profile_code)
                .where(FeEnvProfile.is_default == 1)
                .where(FeEnvProfile.deleted_at.is_(None))
            )
            result = s.execute(stmt).scalar_one_or_none()
            return result or DEFAULT_PROFILE_ID

    def create_profile(self, profile_id: str) -> str:
        pid = validate_profile_id(profile_id)
        with db_session() as s:
            stmt = (
                select(FeEnvProfile)
                .where(FeEnvProfile.profile_code == pid)
                .where(FeEnvProfile.deleted_at.is_(None))
            )
            existing = s.execute(stmt).scalar_one_or_none()
            if existing is None:
                s.add(
                    FeEnvProfile(
                        profile_code=pid,
                        display_name=pid,
                        is_default=0,
                    )
                )
        return pid

    def set_default_profile(self, profile_id: str) -> str:
        pid = validate_profile_id(profile_id)
        with db_session() as s:
            # Ensure target profile exists
            target_stmt = (
                select(FeEnvProfile)
                .where(FeEnvProfile.profile_code == pid)
                .where(FeEnvProfile.deleted_at.is_(None))
            )
            target = s.execute(target_stmt).scalar_one_or_none()
            if target is None:
                target = FeEnvProfile(
                    profile_code=pid,
                    display_name=pid,
                    is_default=0,
                )
                s.add(target)
                s.flush()
            # Clear existing default(s)
            all_stmt = (
                select(FeEnvProfile)
                .where(FeEnvProfile.is_default == 1)
                .where(FeEnvProfile.deleted_at.is_(None))
            )
            for row in s.execute(all_stmt).scalars().all():
                row.is_default = 0
            target.is_default = 1
        return pid

    def resolve_profile(self, explicit_profile: str | None = None) -> str:
        if explicit_profile:
            pid = validate_profile_id(explicit_profile)
            if pid not in self.list_profiles():
                raise ProfileConfigError(f"Profile not found: {pid}")
            return pid
        return self.get_default_profile()

    # DataDictStore / LookupStore 兼容接口（MySQL 后端无需创建目录）
    def delete_profile(self, profile_id: str) -> None:
        pid = validate_profile_id(profile_id)
        if pid == DEFAULT_PROFILE_ID:
            raise ProfileConfigError("Cannot delete the default profile")
        now = datetime.now(timezone.utc)
        with db_session() as s:
            stmt = (
                select(FeEnvProfile)
                .where(FeEnvProfile.profile_code == pid)
                .where(FeEnvProfile.deleted_at.is_(None))
            )
            row = s.execute(stmt).scalar_one_or_none()
            if row:
                row.deleted_at = now


# ---------------------------------------------------------------------------
# Module-level singletons / context helpers
# ---------------------------------------------------------------------------

_store_cache: GlobalProfileStore | None = None
_active_profile: ContextVar[str | None] = ContextVar("flow_engine_active_profile", default=None)


def invalidate_profile_store_cache() -> None:
    global _store_cache
    _store_cache = None


def store() -> GlobalProfileStore:
    global _store_cache
    if _store_cache is None:
        _store_cache = GlobalProfileStore()
    return _store_cache


def active_profile() -> str:
    cur = _active_profile.get()
    return store().resolve_profile(cur)


@contextmanager
def profile_scope(profile_id: str | None) -> Iterator[str]:
    resolved = store().resolve_profile(profile_id)
    token = _active_profile.set(resolved)
    try:
        yield resolved
    finally:
        _active_profile.reset(token)
