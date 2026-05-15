"""MySQL-backed global runtime profile configuration (dev/sit/prod, etc.).

Uses table: fe_env_profile
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import func, or_, select

from flow_engine.db.models import (
    FeDictModule,
    FeEnvProfile,
    FeFlowDeployment,
    FeFlowDraft,
    FeFlowTestBatch,
    FeFlowTestPlan,
    FeFlowVersion,
    FeLookupNs,
    FeSecret,
)
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

    def get_system_capability_policy_map(self, profile_id: str) -> dict[str, list[dict[str, Any]]]:
        """Read environment-level system CapabilityPolicy map (raw dicts).

        Preferred JSON shape:
          {"debug":[rule...], "shadow":[rule...], "production":[rule...]}

        Backward compatible: legacy rows may store a plain list[rule]. In that
        case, we treat it as a single shared policy applied to all modes.
        """
        pid = validate_profile_id(profile_id)
        with db_session() as s:
            stmt = (
                select(FeEnvProfile.system_capability_policy)
                .where(FeEnvProfile.profile_code == pid)
                .where(FeEnvProfile.deleted_at.is_(None))
            )
            raw = s.execute(stmt).scalar_one_or_none()

            if raw is None:
                return {"debug": [], "shadow": [], "production": []}

            # legacy list[rule]
            if isinstance(raw, list):
                lst = list(raw or [])
                return {"debug": lst, "shadow": lst, "production": lst}

            # map shape
            if isinstance(raw, dict):
                def _as_list(x: Any) -> list[dict[str, Any]]:
                    return list(x or []) if isinstance(x, list) else []

                return {
                    "debug": _as_list(raw.get("debug")),
                    "shadow": _as_list(raw.get("shadow")),
                    "production": _as_list(raw.get("production")),
                }

            return {"debug": [], "shadow": [], "production": []}

    def get_system_capability_policy(
        self, profile_id: str, *, run_mode: str | None = None
    ) -> list[dict[str, Any]]:
        """Compatibility helper: return the list for a given run_mode.

        run_mode: "debug" | "shadow" | "production" (case-insensitive). Unknown
        values fall back to "production".
        """
        m = (run_mode or "production").strip().lower()
        mp = self.get_system_capability_policy_map(profile_id)
        if m == "debug":
            return list(mp["debug"])
        if m == "shadow":
            return list(mp["shadow"])
        return list(mp["production"])

    def set_system_capability_policy(
        self,
        profile_id: str,
        policy: dict[str, list[dict[str, Any]]] | list[dict[str, Any]],
    ) -> None:
        pid = validate_profile_id(profile_id)
        with db_session() as s:
            stmt = (
                select(FeEnvProfile)
                .where(FeEnvProfile.profile_code == pid)
                .where(FeEnvProfile.deleted_at.is_(None))
            )
            row = s.execute(stmt).scalar_one_or_none()
            if row is None:
                raise ProfileConfigError(f"Profile not found: {pid}")
            # Normalize to map shape on write.
            if isinstance(policy, list):
                lst = list(policy or [])
                row.system_capability_policy = {"debug": lst, "shadow": lst, "production": lst}
            else:
                row.system_capability_policy = {
                    "debug": list((policy or {}).get("debug") or []),
                    "shadow": list((policy or {}).get("shadow") or []),
                    "production": list((policy or {}).get("production") or []),
                }

    def list_profile_usage_labels(self, profile_id: str) -> list[str]:
        """Return human-readable dependency labels if ``profile_id`` is still referenced.

        Covers: deployments, test plans/batches, profile-layer dict modules, lookup
        namespaces, and flow draft/version bodies that embed ``profile_code`` for this id.
        """
        pid = validate_profile_id(profile_id)
        labels: list[str] = []
        with db_session() as s:

            def _count(model: type, *conds: Any) -> int:
                q = select(func.count()).select_from(model).where(*conds)
                return int(s.execute(q).scalar_one() or 0)

            if _count(FeFlowDeployment, FeFlowDeployment.env_profile_code == pid, FeFlowDeployment.deleted_at.is_(None)):
                labels.append("部署")

            if _count(FeFlowTestPlan, FeFlowTestPlan.profile_code == pid, FeFlowTestPlan.deleted_at.is_(None)):
                labels.append("测试方案")

            if _count(FeFlowTestBatch, FeFlowTestBatch.profile_code == pid, FeFlowTestBatch.deleted_at.is_(None)):
                labels.append("测试批次")

            if _count(
                FeDictModule,
                FeDictModule.layer == "profile",
                FeDictModule.profile_code == pid,
                FeDictModule.deleted_at.is_(None),
            ):
                labels.append("数据字典（环境覆盖）")

            if _count(FeLookupNs, FeLookupNs.profile_code == pid, FeLookupNs.deleted_at.is_(None)):
                labels.append("Lookup")

            if _count(FeSecret, FeSecret.profile_code == pid, FeSecret.deleted_at.is_(None)):
                labels.append("密钥管理")

            pat_compact = f'%"profile_code":"{pid}"%'
            pat_spaced = f'%"profile_code": "{pid}"%'
            if _count(
                FeFlowDraft,
                FeFlowDraft.deleted_at.is_(None),
                or_(FeFlowDraft.body.like(pat_compact), FeFlowDraft.body.like(pat_spaced)),
            ):
                labels.append("流程（草稿）")
            if _count(
                FeFlowVersion,
                FeFlowVersion.deleted_at.is_(None),
                or_(FeFlowVersion.body.like(pat_compact), FeFlowVersion.body.like(pat_spaced)),
            ):
                labels.append("流程（已发布版本）")

        return labels

    # DataDictStore / LookupStore 兼容接口（MySQL 后端无需创建目录）
    def delete_profile(self, profile_id: str) -> None:
        pid = validate_profile_id(profile_id)
        if pid == DEFAULT_PROFILE_ID:
            raise ProfileConfigError("无法删除内置 default 环境。")
        blockers = self.list_profile_usage_labels(pid)
        if blockers:
            joined = "、".join(blockers)
            raise ProfileConfigError(f"无法删除：该环境仍被以下模块使用：{joined}。请先解除引用后再删除。")
        now = datetime.now(timezone.utc)
        with db_session() as s:
            stmt = (
                select(FeEnvProfile)
                .where(FeEnvProfile.profile_code == pid)
                .where(FeEnvProfile.deleted_at.is_(None))
            )
            row = s.execute(stmt).scalar_one_or_none()
            if not row:
                return
            if row.is_default == 1:
                raise ProfileConfigError(
                    "无法删除：该环境当前为默认环境，请先将其他环境设为默认后再删除。"
                )
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
