"""Read subscription message ledger and deploy-run observability for Run Center APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from flow_engine.db.models import FeDeployRun, FeFlowDeployment, FeSubscriptionDedup
from flow_engine.db.session import db_session
from flow_engine.time_utils import utc_isoformat

_MESSAGE_STATUSES = ("processing", "completed", "failed")
_RUN_STATUSES = ("queued", "running", "completed", "failed", "terminated")


def _assert_subscription_deployment(deployment_id: int) -> None:
    with db_session() as s:
        row = s.get(FeFlowDeployment, int(deployment_id))
        if row is None or row.deleted_at is not None:
            raise LookupError("deployment not found")
        if str(row.schedule_type or "") != "subscription":
            raise ValueError("deployment is not subscription schedule_type")


def _subscription_consumer_id(deployment_id: int) -> str | None:
    with db_session() as s:
        row = s.get(FeFlowDeployment, int(deployment_id))
        if row is None or row.deleted_at is not None:
            return None
        schedule_config = dict(row.schedule_config or {})
    subscription = (
        schedule_config.get("subscription")
        if isinstance(schedule_config.get("subscription"), dict)
        else {}
    )
    consumer_id = str(subscription.get("consumer_id") or "").strip()
    return consumer_id or None


def _count_by_status(
    model: type,
    *,
    deployment_id: int,
    status_col: Any,
) -> dict[str, int]:
    with db_session() as s:
        rows = s.execute(
            select(status_col, func.count())
            .where(model.deployment_id == int(deployment_id))
            .where(model.deleted_at.is_(None))
            .group_by(status_col)
        ).all()
    out: dict[str, int] = {}
    for status, count in rows:
        key = str(status or "")
        if key:
            out[key] = int(count)
    return out


def get_subscription_summary(deployment_id: int) -> dict[str, Any]:
    """Aggregate message ledger + deploy-run counts for a subscription deployment."""
    _assert_subscription_deployment(deployment_id)
    consumer_id = _subscription_consumer_id(deployment_id)

    message_counts = _count_by_status(
        FeSubscriptionDedup,
        deployment_id=deployment_id,
        status_col=FeSubscriptionDedup.status,
    )
    run_counts = _count_by_status(
        FeDeployRun,
        deployment_id=deployment_id,
        status_col=FeDeployRun.status,
    )

    with db_session() as s:
        last_msg = s.execute(
            select(FeSubscriptionDedup)
            .where(FeSubscriptionDedup.deployment_id == int(deployment_id))
            .where(FeSubscriptionDedup.deleted_at.is_(None))
            .order_by(FeSubscriptionDedup.updated_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        recent_failed = list(
            s.execute(
                select(FeSubscriptionDedup)
                .where(FeSubscriptionDedup.deployment_id == int(deployment_id))
                .where(FeSubscriptionDedup.deleted_at.is_(None))
                .where(FeSubscriptionDedup.status == "failed")
                .order_by(FeSubscriptionDedup.updated_at.desc())
                .limit(8)
            ).scalars().all()
        )
        last_updated_at = utc_isoformat(last_msg.updated_at) if last_msg else None
        recent_failed_payload = [
            {
                "id": int(r.id),
                "position_key": r.position_key,
                "topic": r.topic,
                "partition": int(r.partition),
                "offset": int(r.offset),
                "status": r.status,
                "deploy_run_id": int(r.deploy_run_id) if r.deploy_run_id is not None else None,
                "error": r.error,
                "updated_at": utc_isoformat(r.updated_at),
            }
            for r in recent_failed
        ]

    return {
        "deployment_id": int(deployment_id),
        "consumer_id": consumer_id,
        "messages": {
            "total": sum(message_counts.values()),
            "by_status": {k: message_counts.get(k, 0) for k in _MESSAGE_STATUSES},
            "last_updated_at": last_updated_at,
        },
        "runs": {
            "total": sum(run_counts.values()),
            "by_status": {k: run_counts.get(k, 0) for k in _RUN_STATUSES},
        },
        "recent_failed_messages": recent_failed_payload,
    }


def list_subscription_messages(
    *,
    deployment_id: int,
    status: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Paginated message ledger for a subscription deployment."""
    _assert_subscription_deployment(deployment_id)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    with db_session() as s:
        base = (
            select(FeSubscriptionDedup)
            .where(FeSubscriptionDedup.deployment_id == int(deployment_id))
            .where(FeSubscriptionDedup.deleted_at.is_(None))
        )
        if status:
            base = base.where(FeSubscriptionDedup.status == str(status))
        total = int(
            s.execute(select(func.count()).select_from(base.subquery())).scalar_one()
        )
        rows = list(
            s.execute(
                base.order_by(FeSubscriptionDedup.updated_at.desc())
                .offset(offset)
                .limit(limit)
            ).scalars().all()
        )
        messages = [
            {
                "id": int(r.id),
                "deployment_id": int(r.deployment_id),
                "position_key": r.position_key,
                "topic": r.topic,
                "partition": int(r.partition),
                "offset": int(r.offset),
                "status": r.status,
                "deploy_run_id": int(r.deploy_run_id) if r.deploy_run_id is not None else None,
                "error": r.error,
                "created_at": utc_isoformat(r.created_at),
                "updated_at": utc_isoformat(r.updated_at),
            }
            for r in rows
        ]

    return {
        "deployment_id": int(deployment_id),
        "total": total,
        "offset": offset,
        "limit": limit,
        "messages": messages,
    }


def _serialize_subscription_message(row: FeSubscriptionDedup) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "deployment_id": int(row.deployment_id),
        "position_key": row.position_key,
        "topic": row.topic,
        "partition": int(row.partition),
        "offset": int(row.offset),
        "status": row.status,
        "deploy_run_id": int(row.deploy_run_id) if row.deploy_run_id is not None else None,
        "error": row.error,
        "created_at": utc_isoformat(row.created_at),
        "updated_at": utc_isoformat(row.updated_at),
    }


def list_recent_failed_subscription_messages(
    *,
    since: datetime | None = None,
    hours: float = 24,
    offset: int = 0,
    limit: int = 10,
) -> dict[str, Any]:
    """Latest failed subscription message per deployment within a lookback window."""
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=float(hours))
    elif since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    offset = max(0, int(offset))
    limit = max(1, min(int(limit), 200))

    deduped: list[dict[str, Any]] = []
    seen: set[int] = set()
    with db_session() as s:
        rows = list(
            s.execute(
                select(FeSubscriptionDedup)
                .where(FeSubscriptionDedup.deleted_at.is_(None))
                .where(FeSubscriptionDedup.status == "failed")
                .where(FeSubscriptionDedup.updated_at >= since)
                .order_by(
                    FeSubscriptionDedup.updated_at.desc(),
                    FeSubscriptionDedup.id.desc(),
                )
            ).scalars().all()
        )
        for row in rows:
            dep_id = int(row.deployment_id)
            if dep_id in seen:
                continue
            seen.add(dep_id)
            deduped.append(_serialize_subscription_message(row))

    return {
        "since": utc_isoformat(since),
        "offset": offset,
        "limit": limit,
        "total": len(deduped),
        "messages": deduped[offset : offset + limit],
    }
