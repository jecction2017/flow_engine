"""MySQL-backed versioned flow storage.

Uses tables:
  fe_flow         — flow metadata index (one row per flow)
  fe_flow_draft   — mutable draft body (0 or 1 active per flow)
  fe_flow_version — immutable version snapshots

旧文件系统实现已迁移至 MySQL，全部通过 SQLAlchemy Session 读写。
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from flow_engine.db.models import FeFlow, FeFlowDraft, FeFlowVersion
from flow_engine.db.session import db_session
from flow_engine.engine.version_meta import FlowMeta, FlowVersionMeta

_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")


def validate_flow_id(flow_id: str) -> str:
    if not flow_id or not _SAFE_ID.match(flow_id):
        raise ValueError(
            "Invalid flow id: use letters, digits, underscore or hyphen (max 128 chars).",
        )
    return flow_id


def _body_to_str(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _str_to_body(text: str) -> dict[str, Any]:
    d = json.loads(text)
    if not isinstance(d, dict):
        raise ValueError("Flow body must be a JSON object")
    return d


# ---------------------------------------------------------------------------
# VersionStore  (单流程视图)
# ---------------------------------------------------------------------------


class VersionStore:
    """MySQL-backed versioned flow store for a single flow_code."""

    def __init__(self, flow_code: str) -> None:
        validate_flow_id(flow_code)
        self.flow_code = flow_code

    def _get_flow_row(self, session) -> FeFlow | None:
        stmt = (
            select(FeFlow)
            .where(FeFlow.flow_code == self.flow_code)
            .where(FeFlow.deleted_at.is_(None))
        )
        return session.execute(stmt).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    def read_meta(self) -> FlowMeta:
        with db_session() as s:
            flow = self._get_flow_row(s)
            if flow is None:
                return FlowMeta(flow_id=self.flow_code)
            ver_stmt = (
                select(FeFlowVersion)
                .where(FeFlowVersion.flow_code == self.flow_code)
                .where(FeFlowVersion.deleted_at.is_(None))
                .order_by(FeFlowVersion.ver_no)
            )
            ver_rows = s.execute(ver_stmt).scalars().all()
            versions = [
                FlowVersionMeta(
                    version=r.ver_no,
                    created_at=r.created_at.timestamp() if r.created_at else time.time(),
                    description=r.description or None,
                    display_name=r.display_name or "",
                )
                for r in ver_rows
            ]
            return FlowMeta(
                flow_id=self.flow_code,
                latest_version=flow.latest_ver_no,
                has_draft=bool(flow.has_draft),
                versions=versions,
            )

    # ------------------------------------------------------------------
    # Draft
    # ------------------------------------------------------------------

    def has_draft(self) -> bool:
        with db_session() as s:
            flow = self._get_flow_row(s)
            return bool(flow and flow.has_draft)

    def read_draft(self) -> dict[str, Any]:
        with db_session() as s:
            stmt = (
                select(FeFlowDraft)
                .where(FeFlowDraft.flow_code == self.flow_code)
                .where(FeFlowDraft.deleted_at.is_(None))
            )
            draft = s.execute(stmt).scalar_one_or_none()
            if draft is None:
                raise FileNotFoundError(f"No draft for flow '{self.flow_code}'")
            return _str_to_body(draft.body)

    def save_draft(self, data: dict[str, Any]) -> None:
        body_str = _body_to_str(data)
        display_name = str(data.get("display_name") or data.get("name") or "")
        with db_session() as s:
            flow = self._get_flow_row(s)
            if flow is None:
                flow = FeFlow(
                    flow_code=self.flow_code,
                    display_name=display_name,
                    has_draft=1,
                    latest_ver_no=0,
                )
                s.add(flow)
                s.flush()
            else:
                flow.display_name = display_name
                flow.has_draft = 1
            # Upsert draft
            draft_stmt = (
                select(FeFlowDraft)
                .where(FeFlowDraft.flow_code == self.flow_code)
                .where(FeFlowDraft.deleted_at.is_(None))
            )
            draft = s.execute(draft_stmt).scalar_one_or_none()
            if draft is None:
                s.add(FeFlowDraft(flow_code=self.flow_code, body=body_str))
            else:
                draft.body = body_str

    def delete_draft(self) -> None:
        now = datetime.now(timezone.utc)
        with db_session() as s:
            draft_stmt = (
                select(FeFlowDraft)
                .where(FeFlowDraft.flow_code == self.flow_code)
                .where(FeFlowDraft.deleted_at.is_(None))
            )
            draft = s.execute(draft_stmt).scalar_one_or_none()
            if draft:
                draft.deleted_at = now
            flow = self._get_flow_row(s)
            if flow:
                flow.has_draft = 0

    # ------------------------------------------------------------------
    # Versions (immutable snapshots)
    # ------------------------------------------------------------------

    def list_versions(self) -> list[FlowVersionMeta]:
        return self.read_meta().versions

    def read_version(self, version: int) -> dict[str, Any]:
        with db_session() as s:
            stmt = (
                select(FeFlowVersion)
                .where(FeFlowVersion.flow_code == self.flow_code)
                .where(FeFlowVersion.ver_no == version)
                .where(FeFlowVersion.deleted_at.is_(None))
            )
            row = s.execute(stmt).scalar_one_or_none()
            if row is None:
                raise FileNotFoundError(
                    f"Version v{version} not found for flow '{self.flow_code}'"
                )
            return _str_to_body(row.body)

    def commit_version(
        self,
        data: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> int:
        """Commit draft (or supplied data) as a new immutable version. Returns new version number."""
        if data is None:
            data = self.read_draft()
        body_str = _body_to_str(data)
        display_name = str(data.get("display_name") or data.get("name") or self.flow_code)
        with db_session() as s:
            flow = self._get_flow_row(s)
            if flow is None:
                flow = FeFlow(
                    flow_code=self.flow_code,
                    display_name=display_name,
                    has_draft=0,
                    latest_ver_no=0,
                )
                s.add(flow)
                s.flush()
            new_ver = flow.latest_ver_no + 1
            s.add(
                FeFlowVersion(
                    flow_code=self.flow_code,
                    ver_no=new_ver,
                    body=body_str,
                    display_name=display_name,
                    description=description or "",
                )
            )
            flow.latest_ver_no = new_ver
            flow.display_name = display_name
        return new_ver

    def latest_version_num(self) -> int:
        with db_session() as s:
            flow = self._get_flow_row(s)
            return flow.latest_ver_no if flow else 0

    def delete(self) -> None:
        """Soft-delete the flow (and implicitly its draft/versions by filtering deleted_at IS NULL)."""
        now = datetime.now(timezone.utc)
        with db_session() as s:
            flow = self._get_flow_row(s)
            if flow:
                flow.deleted_at = now


# ---------------------------------------------------------------------------
# FlowVersionRegistry  (顶层注册表：管理所有流程)
# ---------------------------------------------------------------------------


class FlowVersionRegistry:
    """MySQL-backed top-level registry that manages all versioned flows."""

    # 保持 directory 属性供 API 响应字段兼容
    directory: str = "mysql://flows"

    def version_store(self, flow_id: str) -> VersionStore:
        return VersionStore(flow_id)

    def list_flows(self) -> list[dict[str, Any]]:
        with db_session() as s:
            stmt = (
                select(FeFlow)
                .where(FeFlow.deleted_at.is_(None))
                .order_by(FeFlow.updated_at.desc())
            )
            rows = s.execute(stmt).scalars().all()
            return [
                {
                    "id": r.flow_code,
                    "display_name": r.display_name or "",
                    "path": f"mysql://flows/{r.flow_code}",
                    "updated_at": r.updated_at.timestamp() if r.updated_at else 0.0,
                    "latest_version": r.latest_ver_no,
                    "has_draft": bool(r.has_draft),
                }
                for r in rows
            ]

    def exists(self, flow_id: str) -> bool:
        try:
            validate_flow_id(flow_id)
        except ValueError:
            return False
        with db_session() as s:
            stmt = (
                select(FeFlow.id)
                .where(FeFlow.flow_code == flow_id)
                .where(FeFlow.deleted_at.is_(None))
            )
            return s.execute(stmt).scalar_one_or_none() is not None

    def create(self, flow_id: str, initial_data: dict[str, Any]) -> None:
        validate_flow_id(flow_id)
        self.version_store(flow_id).save_draft(initial_data)

    def delete(self, flow_id: str) -> None:
        validate_flow_id(flow_id)
        self.version_store(flow_id).delete()

    def resolve_version_data(
        self, flow_id: str, channel: str
    ) -> tuple[int | None, dict[str, Any]]:
        """Resolve channel/version string to (version_num, flow_data).

        channel values:
          - "latest" → latest committed version
          - "draft"  → draft
          - "v3"/"3" → specific version number
        """
        vs = self.version_store(flow_id)
        if channel == "latest":
            meta = vs.read_meta()
            if meta.latest_version == 0:
                raise ValueError(f"No versions committed for flow '{flow_id}'")
            return meta.latest_version, vs.read_version(meta.latest_version)
        if channel == "draft":
            return None, vs.read_draft()
        raw = channel.lstrip("vV")
        try:
            n = int(raw)
        except ValueError:
            raise ValueError(f"Unknown channel/version: '{channel}'")
        return n, vs.read_version(n)
