"""Cron scheduler embedded inside the Coordinator process.

定时由 Coordinator.run() 的事件循环按 ``FLOW_SCHEDULER_TICK_S`` 调用 ``Scheduler.tick``。
``tick`` 扫描 cron 模板部署，按 cron 表达式判定是否需要 fire；fire 时在 ``fe_deploy_run``
插入 ``status='queued'`` 的一条记录（同一 ``deployment_id``），由 Coordinator 分配 Worker，
Worker claim 后执行。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from flow_engine.db.models import FeDeployRun, FeFlowDeployment, FeWorker
from flow_engine.db.session import db_session

logger = logging.getLogger(__name__)


def _parse_cron_next(cron_expr: str, base_time: datetime) -> datetime:
    """Compute next fire time from ``base_time`` using croniter.

    Imported lazily so the module is usable on systems without croniter when
    cron schedules are not exercised (tests / debug).
    """
    try:
        from croniter import croniter
    except ModuleNotFoundError as e:  # pragma: no cover
        raise RuntimeError(
            "cron schedule requires extra dependency 'croniter'. "
            "Install with: pip install -e \".[runner]\" (or pip install croniter)."
        ) from e

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

def _normalize_targeting(raw: Any) -> dict[str, Any]:
    """Best-effort normalize; invalid shapes become mode=any."""
    if not isinstance(raw, dict):
        return {"mode": "any"}
    mode = str(raw.get("mode") or "any").strip().lower()
    if mode == "pin":
        worker_id = str(raw.get("worker_id") or "").strip()
        if worker_id:
            return {"mode": "pin", "worker_id": worker_id}
        return {"mode": "any"}
    if mode == "pool":
        worker_ids = raw.get("worker_ids")
        if isinstance(worker_ids, list):
            ids = [str(x).strip() for x in worker_ids if str(x).strip()]
            if ids:
                return {"mode": "pool", "worker_ids": list(dict.fromkeys(ids))}
        return {"mode": "any"}
    return {"mode": "any"}


def _has_eligible_worker(*, tmpl: FeFlowDeployment, active_workers: set[str]) -> bool:
    """Whether this template has at least one eligible active worker."""
    targeting = _normalize_targeting(getattr(tmpl, "worker_targeting", None) or {})
    mode = targeting.get("mode")
    if mode == "pin":
        return targeting["worker_id"] in active_workers
    if mode == "pool":
        pool = {str(x) for x in (targeting.get("worker_ids") or []) if str(x)}
        return bool(active_workers & pool)
    return bool(active_workers)


def _tick_sync() -> int:
    """Synchronous core. Returns how many cron fires (queued runs) were created."""
    fires = 0
    now = datetime.now(timezone.utc)
    with db_session() as s:
        active_workers = set(
            s.execute(
                select(FeWorker.worker_id)
                .where(FeWorker.status == "active")
                .where(FeWorker.deleted_at.is_(None))
            )
            .scalars()
            .all()
        )
        stmt = (
            select(FeFlowDeployment)
            .where(FeFlowDeployment.schedule_type == "cron")
            # Only running templates should fire. Stopped means disabled.
            .where(FeFlowDeployment.status == "running")
            .where(FeFlowDeployment.deleted_at.is_(None))
        )
        templates = list(s.execute(stmt).scalars().all())

        for tmpl in templates:
            if not _has_eligible_worker(tmpl=tmpl, active_workers=active_workers):
                targeting = _normalize_targeting(getattr(tmpl, "worker_targeting", None) or {})
                tmpl.status = "failed"
                tmpl.status_detail = {
                    "reason": "no_eligible_worker",
                    "schedule_type": "cron",
                    "targeting": targeting,
                    "active_worker_count": len(active_workers),
                    "ts": now.isoformat(),
                    "message": "cron due but no eligible active worker",
                }
                logger.warning(
                    "cron template due but no eligible active workers; mark failed: dep_id=%s targeting=%s active=%d",
                    tmpl.id,
                    targeting,
                    len(active_workers),
                )
                continue
            cfg = tmpl.schedule_config or {}
            cron_expr = cfg.get("cron_expr")
            if not cron_expr:
                continue
            base = _cron_schedule_base_time(s, tmpl) or now
            try:
                nxt = _parse_cron_next(cron_expr, base)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "invalid cron_expr %r on deployment %s", cron_expr, tmpl.id
                )
                continue
            if nxt > now:
                continue

            s.add(
                FeDeployRun(
                    deployment_id=int(tmpl.id),
                    worker_id=None,
                    flow_code=tmpl.flow_code,
                    ver_no=int(tmpl.ver_no),
                    mode=str(tmpl.mode),
                    schedule_type="cron",
                    trigger_type="cron",
                    trigger_context=None,
                    status="queued",
                    started_at=None,
                )
            )
            fires += 1
    return fires


def _cron_schedule_base_time(session: Any, tmpl: FeFlowDeployment) -> datetime | None:
    """Anchor for ``croniter.get_next``: last time we enqueued a cron run for this template.

    Uses ``max(created_at)`` of ``FeDeployRun`` rows for this deployment with
    ``trigger_type='cron'``. If none, uses the template's ``created_at``.
    """
    stmt = (
        select(func.max(FeDeployRun.created_at))
        .where(FeDeployRun.deployment_id == tmpl.id)
        .where(FeDeployRun.trigger_type == "cron")
        .where(FeDeployRun.deleted_at.is_(None))
    )
    max_enqueued = session.execute(stmt).scalar_one_or_none()
    if max_enqueued is not None:
        if max_enqueued.tzinfo is None:
            return max_enqueued.replace(tzinfo=timezone.utc)
        return max_enqueued
    created = tmpl.created_at
    if created is None:
        return None
    if created.tzinfo is None:
        return created.replace(tzinfo=timezone.utc)
    return created


async def _tick_async() -> None:
    import asyncio

    await asyncio.to_thread(_tick_sync)
