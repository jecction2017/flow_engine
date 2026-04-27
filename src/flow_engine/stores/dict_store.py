"""MySQL-backed modular data dictionary storage.

Uses table: fe_dict_module
  layer='base',    profile_code='default'  → 基础层模块
  layer='profile', profile_code=<env>      → 环境覆盖层模块
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import yaml

from flow_engine.engine.exceptions import FlowEngineError


class DataDictError(FlowEngineError):
    """Invalid dictionary module, id, or path."""


CORE_MODULE_ID = "core"
DEFAULT_PROFILE_ID = "default"
MODULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
PROFILE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
DictLayer = Literal["base", "profile"]

# base 层使用 'default' 作为 profile_code 哨兵值（与 fe_dict_module 表设计一致）
_BASE_PROFILE_SENTINEL = "default"


@dataclass(frozen=True)
class DictModule:
    module_id: str
    layer: DictLayer
    path: str          # MySQL 后端：虚拟路径 "db://<layer>/<module_code>"
    profile: str | None = None


def validate_module_id(module_id: str) -> str:
    mid = (module_id or "").strip()
    if not MODULE_ID_PATTERN.fullmatch(mid):
        raise DataDictError(
            f"Invalid module_id {module_id!r}; expected ^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$"
        )
    return mid


def validate_profile_id(profile_id: str) -> str:
    pid = (profile_id or "").strip()
    if not PROFILE_ID_PATTERN.fullmatch(pid):
        raise DataDictError(
            f"Invalid profile_id {profile_id!r}; expected ^[a-z][a-z0-9_-]{{0,63}}$"
        )
    return pid


def _parse_yaml_mapping(text: str, *, label: str) -> dict[str, Any]:
    if not text.strip():
        data: Any = {}
    else:
        data = yaml.safe_load(text)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise DataDictError(f"{label} root must be a mapping (object)")
    return data


def _dump_yaml_mapping(data: dict[str, Any]) -> str:
    if not isinstance(data, dict):
        raise DataDictError("dictionary module root must be a mapping (object)")
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


def _profile_code_for_layer(layer: DictLayer, profile: str | None) -> str:
    """fe_dict_module 的 profile_code 字段：base 层用哨兵 'default'，profile 层用实际 profile。"""
    if layer == "base":
        return _BASE_PROFILE_SENTINEL
    if profile is None:
        raise DataDictError("profile is required for profile layer modules")
    return validate_profile_id(profile)


class DataDictStore:
    """MySQL-backed layered module store.

    Layout (conceptual):
      base layer   → fe_dict_module WHERE layer='base'   AND profile_code='default'
      profile layer→ fe_dict_module WHERE layer='profile' AND profile_code=<env>
    """

    # directory 属性保持 API 兼容
    directory: str = "mysql://dict"

    def __init__(self) -> None:
        self._ensure_core_module()

    def _ensure_core_module(self) -> None:
        """Ensure the base/core module row exists (idempotent bootstrap)."""
        from sqlalchemy import select

        from flow_engine.db.models import FeDictModule
        from flow_engine.db.session import db_session

        with db_session() as s:
            stmt = (
                select(FeDictModule)
                .where(FeDictModule.layer == "base")
                .where(FeDictModule.profile_code == _BASE_PROFILE_SENTINEL)
                .where(FeDictModule.module_code == CORE_MODULE_ID)
                .where(FeDictModule.deleted_at.is_(None))
            )
            if s.execute(stmt).scalar_one_or_none() is None:
                s.add(
                    FeDictModule(
                        layer="base",
                        profile_code=_BASE_PROFILE_SENTINEL,
                        module_code=CORE_MODULE_ID,
                        yaml_text="{}\n",
                    )
                )

    def list_profiles(self) -> list[str]:
        from sqlalchemy import distinct, select

        from flow_engine.db.models import FeDictModule
        from flow_engine.db.session import db_session

        with db_session() as s:
            stmt = (
                select(distinct(FeDictModule.profile_code))
                .where(FeDictModule.layer == "profile")
                .where(FeDictModule.deleted_at.is_(None))
                .order_by(FeDictModule.profile_code)
            )
            rows = s.execute(stmt).scalars().all()
            return list(rows)

    def ensure_profile(self, profile_id: str) -> None:
        """Raise DataDictError if the profile does not exist in fe_env_profile."""
        from sqlalchemy import select

        from flow_engine.db.models import FeEnvProfile
        from flow_engine.db.session import db_session

        pid = validate_profile_id(profile_id)
        with db_session() as s:
            stmt = (
                select(FeEnvProfile.id)
                .where(FeEnvProfile.profile_code == pid)
                .where(FeEnvProfile.deleted_at.is_(None))
            )
            if s.execute(stmt).scalar_one_or_none() is None:
                raise DataDictError(f"Profile not found: {profile_id}")

    def create_profile(self, profile_id: str) -> None:
        """No-op in MySQL backend; profiles are managed via GlobalProfileStore / fe_env_profile."""

    def list_modules(self, layer: DictLayer, *, profile: str | None = None) -> list[DictModule]:
        from sqlalchemy import select

        from flow_engine.db.models import FeDictModule
        from flow_engine.db.session import db_session

        profile_code = _profile_code_for_layer(layer, profile)
        with db_session() as s:
            stmt = (
                select(FeDictModule)
                .where(FeDictModule.layer == layer)
                .where(FeDictModule.profile_code == profile_code)
                .where(FeDictModule.deleted_at.is_(None))
                .order_by(FeDictModule.module_code)
            )
            rows = s.execute(stmt).scalars().all()
            return [
                DictModule(
                    module_id=r.module_code,
                    layer=layer,
                    profile=profile if layer == "profile" else None,
                    path=f"db://{layer}/{r.module_code}",
                )
                for r in rows
            ]

    def read_module_raw(
        self, layer: DictLayer, module_id: str, *, profile: str | None = None
    ) -> str:
        from sqlalchemy import select

        from flow_engine.db.models import FeDictModule
        from flow_engine.db.session import db_session

        mid = validate_module_id(module_id)
        profile_code = _profile_code_for_layer(layer, profile)
        with db_session() as s:
            stmt = (
                select(FeDictModule)
                .where(FeDictModule.layer == layer)
                .where(FeDictModule.profile_code == profile_code)
                .where(FeDictModule.module_code == mid)
                .where(FeDictModule.deleted_at.is_(None))
            )
            row = s.execute(stmt).scalar_one_or_none()
            if row is None:
                raise DataDictError(f"Dictionary module not found: {module_id}")
            return row.yaml_text

    def read_module(
        self, layer: DictLayer, module_id: str, *, profile: str | None = None
    ) -> dict[str, Any]:
        raw = self.read_module_raw(layer, module_id, profile=profile)
        return copy.deepcopy(_parse_yaml_mapping(raw, label=f"{layer} module {module_id}"))

    def write_module(
        self,
        layer: DictLayer,
        module_id: str,
        text: str,
        *,
        profile: str | None = None,
    ) -> None:
        from sqlalchemy import select

        from flow_engine.db.models import FeDictModule
        from flow_engine.db.session import db_session

        mid = validate_module_id(module_id)
        _parse_yaml_mapping(text, label=f"{layer} module {module_id}")  # validate YAML
        profile_code = _profile_code_for_layer(layer, profile)
        with db_session() as s:
            stmt = (
                select(FeDictModule)
                .where(FeDictModule.layer == layer)
                .where(FeDictModule.profile_code == profile_code)
                .where(FeDictModule.module_code == mid)
                .where(FeDictModule.deleted_at.is_(None))
            )
            row = s.execute(stmt).scalar_one_or_none()
            if row is None:
                s.add(
                    FeDictModule(
                        layer=layer,
                        profile_code=profile_code,
                        module_code=mid,
                        yaml_text=text,
                    )
                )
            else:
                row.yaml_text = text

    def delete_module(
        self,
        layer: DictLayer,
        module_id: str,
        *,
        profile: str | None = None,
    ) -> None:
        from sqlalchemy import select

        from flow_engine.db.models import FeDictModule
        from flow_engine.db.session import db_session

        mid = validate_module_id(module_id)
        if layer == "base" and mid == CORE_MODULE_ID:
            raise DataDictError("core base module cannot be deleted")
        profile_code = _profile_code_for_layer(layer, profile)
        now = datetime.now(timezone.utc)
        with db_session() as s:
            stmt = (
                select(FeDictModule)
                .where(FeDictModule.layer == layer)
                .where(FeDictModule.profile_code == profile_code)
                .where(FeDictModule.module_code == mid)
                .where(FeDictModule.deleted_at.is_(None))
            )
            row = s.execute(stmt).scalar_one_or_none()
            if row:
                row.deleted_at = now


# ---------------------------------------------------------------------------
# Utility functions (used by data_dict.py)
# ---------------------------------------------------------------------------


def parse_path(path: str) -> list[str]:
    p = path.strip().strip(".")
    if not p:
        return []
    parts: list[str] = []
    for seg in p.split("."):
        s = seg.strip()
        if not s:
            raise DataDictError(f"Invalid dictionary path: {path!r}")
        parts.append(s)
    return parts


def get_at_path(tree: dict[str, Any], parts: list[str]) -> Any:
    if not parts:
        return tree
    cur: Any = tree
    for key in parts:
        if not isinstance(cur, dict):
            raise DataDictError(f"Not a mapping at {key!r}")
        if key not in cur:
            raise KeyError("missing")
        cur = cur[key]
    return cur


def set_at_path(tree: dict[str, Any], parts: list[str], value: Any) -> None:
    if not parts:
        if not isinstance(value, dict):
            raise DataDictError("root replacement must be a mapping")
        tree.clear()
        tree.update(value)
        return
    cur = tree
    for key in parts[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[parts[-1]] = value


def delete_at_path(tree: dict[str, Any], parts: list[str]) -> None:
    if not parts:
        tree.clear()
        return
    cur = tree
    for key in parts[:-1]:
        if not isinstance(cur, dict) or key not in cur:
            return
        cur = cur[key]
        if not isinstance(cur, dict):
            return
    last = parts[-1]
    if isinstance(cur, dict) and last in cur:
        del cur[last]
