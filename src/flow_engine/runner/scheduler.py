"""Cron scheduler embedded inside the Coordinator process (设计文档 §8.5).

定时由 Coordinator.run() 的事件循环每 30s 调用一次 ``Scheduler.tick``。
``tick`` 扫描 cron 模板部署，按 cron 表达式判定是否需要 fire；fire 时克隆出
一个 once 子部署（``status='pending'``、``parent_deployment_id=template.id``），
让 Coordinator 下一轮分配 Worker。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from flow_engine.db.models import FeFlowDeployment, FeFlowRun
from flow_engine.db.session import db_session

logger = logging.getLogger(__name__)


def _parse_cron_next(cron_expr: str, base_time: datetime) -> datetime:
    """Compute next fire time from ``base_time`` using croniter.

    Imported lazily so the module is usable on systems without croniter when
    cron schedules are not exercised (tests / debug).
    """
    from croniter import croniter

    if base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=timezone.utc)
    it = croniter(cron_expr, base_time)
    nxt: datetime = it.get_next(datetime)
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=timezone.utc)
    return nxt


class Scheduler:
    """In-process cron trigger; not a separate executable."""

    async def tick(self) -> None:
        try:
            await _tick_async()
        except Exception:  # noqa: BLE001
            logger.exception("scheduler tick failed")


# ---------------------------------------------------------------------------
# tick implementation
# ---------------------------------------------------------------------------


def _tick_sync() -> int:
    """Synchronous core. Returns how many cron fires were created."""
    fires = 0
    now = datetime.now(timezone.utc)
    with db_session() as s:
        stmt = (
            select(FeFlowDeployment)
            .where(FeFlowDeployment.schedule_type == "cron")
            .where(FeFlowDeployment.status.in_(("running", "stopped")))
            .where(FeFlowDeployment.deleted_at.is_(None))
        )
        templates = list(s.execute(stmt).scalars().all())

        for tmpl in templates:
            cfg = tmpl.schedule_config or {}
            cron_expr = cfg.get("cron_expr")
            if not cron_expr:
                continue
            base = _last_fire_time(s, tmpl) or tmpl.created_at or now
            try:
                nxt = _parse_cron_next(cron_expr, base)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "invalid cron_expr %r on deployment %s", cron_expr, tmpl.id
                )
                continue
            if nxt > now:
                continue

            # Fire: clone as a once child deployment.
            child = FeFlowDeployment(
                flow_code=tmpl.flow_code,
                ver_no=tmpl.ver_no,
                mode=tmpl.mode,
                schedule_type="once",
                schedule_config={},
                worker_policy=tmpl.worker_policy,
                capability_policy=tmpl.capability_policy,
                status="pending",
                env_profile_code=tmpl.env_profile_code,
                parent_deployment_id=tmpl.id,
            )
            s.add(child)
            fires += 1
    return fires


def _last_fire_time(session: Any, tmpl: FeFlowDeployment) -> datetime | None:
    """Approximation: the latest ``started_at`` of children produced by this template.

    If none, fall back to ``tmpl.created_at``. We never persist a dedicated
    "last fire" column to keep the schema flat.
    """
    stmt = (
        select(FeFlowRun)
        .join(
            FeFlowDeployment,
            FeFlowDeployment.id == FeFlowRun.deployment_id,
        )
        .where(FeFlowDeployment.parent_deployment_id == tmpl.id)
        .where(FeFlowRun.deleted_at.is_(None))
        .order_by(FeFlowRun.started_at.desc())
        .limit(1)
    )
    row = session.execute(stmt).scalars().first()
    if row is None:
        return tmpl.created_at
    return row.started_at


async def _tick_async() -> None:
    import asyncio

    await asyncio.to_thread(_tick_sync)
