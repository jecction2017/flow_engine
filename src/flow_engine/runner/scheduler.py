"""Cron scheduling primitives (worker-side execution).

Workers assigned to a ``schedule_type='cron'`` deployment compute the next fire
time locally and insert ``FeDeployRun`` rows when due. The Coordinator only
assigns / re-assigns workers and renews leader leases — it does not tick cron.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from flow_engine.db.models import FeDeployRun, FeFlowDeployment
from flow_engine.db.session import db_session

logger = logging.getLogger(__name__)


def _parse_cron_next(cron_expr: str, base_time: datetime) -> datetime:
    """Compute next fire time from ``base_time`` using croniter."""
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


def cron_schedule_base_time(session: Any, tmpl: FeFlowDeployment) -> datetime | None:
    """Anchor for ``croniter.get_next``: last cron run enqueue/start for this template."""
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


def next_cron_fire_at(
    tmpl: FeFlowDeployment,
    *,
    now: datetime | None = None,
    session: Any | None = None,
) -> datetime | None:
    """Return the next scheduled fire instant, or None if cron_expr is missing/invalid."""
    cfg = tmpl.schedule_config or {}
    cron_expr = cfg.get("cron_expr")
    if not cron_expr:
        return None
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    def _base(sess: Any) -> datetime:
        anchored = cron_schedule_base_time(sess, tmpl)
        return anchored or now

    try:
        if session is not None:
            base = _base(session)
        else:
            with db_session() as s:
                base = _base(s)
        return _parse_cron_next(str(cron_expr), base)
    except Exception:  # noqa: BLE001
        logger.exception(
            "invalid cron_expr %r on deployment %s", cron_expr, tmpl.id
        )
        return None


def cron_is_due(
    tmpl: FeFlowDeployment,
    *,
    now: datetime | None = None,
    session: Any | None = None,
) -> bool:
    """Whether a cron fire should happen now (same semantics as legacy coordinator tick)."""
    nxt = next_cron_fire_at(tmpl, now=now, session=session)
    if nxt is None:
        return False
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return nxt <= now


def enqueue_cron_run_if_due(
    deployment_id: int,
    *,
    worker_id: str | None = None,
    now: datetime | None = None,
) -> int | None:
    """Insert a ``queued`` cron run when due; returns new run id or None.

    The worker claims the row immediately via ``claim_queued_deploy_run`` so only
    one leader executes per slot even if multiple workers poll.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    with db_session() as s:
        tmpl = s.get(FeFlowDeployment, int(deployment_id))
        if tmpl is None or tmpl.deleted_at is not None:
            return None
        if str(tmpl.schedule_type or "") != "cron":
            return None
        if tmpl.status != "running":
            return None

        existing = (
            s.execute(
                select(FeDeployRun)
                .where(FeDeployRun.deployment_id == int(tmpl.id))
                .where(FeDeployRun.status == "queued")
                .where(FeDeployRun.trigger_type == "cron")
                .where(FeDeployRun.deleted_at.is_(None))
                .order_by(FeDeployRun.id.asc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if existing is not None:
            return int(existing.id)

        if not cron_is_due(tmpl, now=now, session=s):
            return None

        row = FeDeployRun(
            deployment_id=int(tmpl.id),
            worker_id=worker_id,
            flow_code=tmpl.flow_code,
            ver_no=int(tmpl.ver_no),
            mode=str(tmpl.mode),
            schedule_type="cron",
            trigger_type="cron",
            trigger_context=None,
            status="queued",
            started_at=None,
        )
        s.add(row)
        s.flush()
        return int(row.id)
