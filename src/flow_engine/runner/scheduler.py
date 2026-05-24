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
from flow_engine.time_utils import utc_isoformat

logger = logging.getLogger(__name__)


def truncate_to_utc_second(value: datetime) -> datetime:
    """Normalize cron instants to whole UTC seconds."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.replace(microsecond=0)


def utc_second_iso(value: datetime) -> str:
    return utc_isoformat(truncate_to_utc_second(value)) or ""


def parse_schedule_iso(value: Any) -> datetime | None:
    """Parse ``schedule_config`` ISO timestamps (naive values treated as UTC)."""
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return truncate_to_utc_second(dt)


def merge_cron_schedule_meta(
    tmpl: FeFlowDeployment,
    *,
    last_run_at: datetime | None = None,
    next_run_at: datetime | None = None,
) -> None:
    """Persist ``last_run_at`` / ``next_run_at`` into ``schedule_config`` (whole seconds)."""
    cfg = dict(tmpl.schedule_config or {})
    if last_run_at is not None:
        cfg["last_run_at"] = utc_second_iso(last_run_at)
    if next_run_at is not None:
        cfg["next_run_at"] = utc_second_iso(next_run_at)
    tmpl.schedule_config = cfg


def refresh_cron_schedule_config(
    tmpl: FeFlowDeployment,
    *,
    session: Any,
    now: datetime | None = None,
) -> None:
    """Initialize or refresh persisted ``next_run_at`` for a cron deployment."""
    if now is None:
        now = datetime.now(timezone.utc)
    now = truncate_to_utc_second(now)
    nxt = peek_next_cron_fire_at(tmpl, now=now, session=session)
    if nxt is not None:
        merge_cron_schedule_meta(tmpl, next_run_at=nxt)


def peek_next_cron_fire_at(
    tmpl: FeFlowDeployment,
    *,
    now: datetime | None = None,
    session: Any | None = None,
    skip_missed: bool = True,
) -> datetime | None:
    """Read-only next fire instant.

    When ``skip_missed`` is True (recovery / display), past ``next_run_at`` values
    advance to the first future slot. When False (due check / enqueue), the stored
  slot is returned even if slightly in the past so a single fire can proceed.
    """
    cfg = tmpl.schedule_config or {}
    cron_expr = cfg.get("cron_expr")
    if not cron_expr:
        return None
    if now is None:
        now = datetime.now(timezone.utc)
    now = truncate_to_utc_second(now)

    def _peek(sess: Any) -> datetime | None:
        stored = parse_schedule_iso(cfg.get("next_run_at"))
        if stored is None:
            base = cron_schedule_base_time(sess, tmpl) or now
            return _parse_cron_next(str(cron_expr), base)
        if skip_missed and stored < now:
            return _parse_cron_next(str(cron_expr), now)
        return stored

    try:
        if session is not None:
            return _peek(session)
        with db_session() as s:
            return _peek(s)
    except Exception:  # noqa: BLE001
        logger.exception(
            "invalid cron_expr %r on deployment %s", cron_expr, tmpl.id
        )
        return None


def align_cron_next_fire(
    tmpl: FeFlowDeployment,
    *,
    session: Any,
    now: datetime | None = None,
) -> datetime | None:
    """Persist skip-missed adjustment and return authoritative ``next_run_at``."""
    nxt = peek_next_cron_fire_at(tmpl, now=now, session=session, skip_missed=True)
    if nxt is not None:
        merge_cron_schedule_meta(tmpl, next_run_at=nxt)
    return nxt


def _parse_cron_next(cron_expr: str, base_time: datetime) -> datetime:
    """Compute next fire time from ``base_time`` using croniter."""
    try:
        from croniter import croniter
    except ModuleNotFoundError as e:  # pragma: no cover
        raise RuntimeError(
            "cron schedule requires extra dependency 'croniter'. "
            "Install with: pip install -e \".[runner]\" (or pip install croniter)."
        ) from e

    base_time = truncate_to_utc_second(base_time)
    it = croniter(cron_expr, base_time)
    nxt: datetime = it.get_next(datetime)
    return truncate_to_utc_second(nxt)


def cron_schedule_base_time(session: Any, tmpl: FeFlowDeployment) -> datetime | None:
    """Anchor for ``croniter.get_next``: persisted last fire, else last cron run, else created_at."""
    cfg = tmpl.schedule_config or {}
    stored = parse_schedule_iso(cfg.get("last_run_at"))
    if stored is not None:
        return stored

    stmt = (
        select(func.max(FeDeployRun.created_at))
        .where(FeDeployRun.deployment_id == tmpl.id)
        .where(FeDeployRun.trigger_type == "cron")
        .where(FeDeployRun.deleted_at.is_(None))
    )
    max_enqueued = session.execute(stmt).scalar_one_or_none()
    if max_enqueued is not None:
        return truncate_to_utc_second(max_enqueued)
    created = tmpl.created_at
    if created is None:
        return None
    return truncate_to_utc_second(created)


def next_cron_fire_at(
    tmpl: FeFlowDeployment,
    *,
    now: datetime | None = None,
    session: Any | None = None,
) -> datetime | None:
    """Return the next scheduled fire instant, or None if cron_expr is missing/invalid."""
    return peek_next_cron_fire_at(tmpl, now=now, session=session)


def cron_is_due(
    tmpl: FeFlowDeployment,
    *,
    now: datetime | None = None,
    session: Any | None = None,
) -> bool:
    """Whether a cron fire should happen now (never catch up missed slots)."""
    nxt = peek_next_cron_fire_at(
        tmpl, now=now, session=session, skip_missed=False
    )
    if nxt is None:
        return False
    if now is None:
        now = datetime.now(timezone.utc)
    now = truncate_to_utc_second(now)
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
    now = truncate_to_utc_second(now)
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

        cfg = tmpl.schedule_config or {}
        stored_next = parse_schedule_iso(cfg.get("next_run_at"))
        if stored_next is not None and stored_next < now:
            align_cron_next_fire(tmpl, session=s, now=now)

        if not cron_is_due(tmpl, now=now, session=s):
            return None

        due_at = peek_next_cron_fire_at(
            tmpl, now=now, session=s, skip_missed=False
        )
        if due_at is None:
            return None
        cron_expr = str(cfg.get("cron_expr") or "")
        next_after = _parse_cron_next(cron_expr, due_at)
        merge_cron_schedule_meta(
            tmpl,
            last_run_at=due_at,
            next_run_at=next_after,
        )

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
