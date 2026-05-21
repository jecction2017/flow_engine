"""Subscription message ledger: idempotency + processing status per position."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from flow_engine.db.models import FeSubscriptionDedup
from flow_engine.db.session import db_session

MessageStatus = Literal["processing", "completed", "failed"]

_STATUS_PROCESSING: MessageStatus = "processing"
_STATUS_COMPLETED: MessageStatus = "completed"
_STATUS_FAILED: MessageStatus = "failed"

_MAX_ERROR_LEN = 16_000


def position_key(topic: str, partition: int, offset: int) -> str:
    return f"{topic}:{partition}:{offset}"


def idempotency_enabled(raw: dict[str, Any] | None) -> bool:
    """True when ``schedule_config.consumption.idempotency`` is configured (non-empty)."""
    if not raw or not isinstance(raw, dict):
        return False
    if raw.get("enabled") is False:
        return False
    return bool(raw)


def idempotency_window_s(raw: dict[str, Any] | None) -> int | None:
    if not idempotency_enabled(raw):
        return None
    window = raw.get("window_s") if isinstance(raw, dict) else None
    if window is None:
        return None
    try:
        value = int(window)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _truncate_error(message: str | None) -> str | None:
    if not message:
        return None
    text = str(message).strip()
    if not text:
        return None
    if len(text) <= _MAX_ERROR_LEN:
        return text
    return text[: _MAX_ERROR_LEN - 3] + "..."


def _purge_expired(*, deployment_id: int, window_s: int | None) -> None:
    if not window_s or window_s <= 0:
        return
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=int(window_s))
    with db_session() as s:
        s.execute(
            FeSubscriptionDedup.__table__.delete().where(
                FeSubscriptionDedup.deployment_id == int(deployment_id)
            ).where(FeSubscriptionDedup.created_at < cutoff)
        )


def begin_message_processing(
    *,
    deployment_id: int,
    topic: str,
    partition: int,
    offset: int,
    window_s: int | None,
    idempotency: bool,
) -> bool:
    """Record ``processing`` and return whether this position should run.

    With idempotency, concurrent duplicate claims lose (``IntegrityError``).
    Without idempotency, always returns True and upserts the ledger row.
    """
    key = position_key(topic, partition, offset)
    _purge_expired(deployment_id=deployment_id, window_s=window_s if idempotency else None)

    with db_session() as s:
        if idempotency:
            row = FeSubscriptionDedup(
                deployment_id=int(deployment_id),
                position_key=key,
                topic=topic,
                partition=int(partition),
                offset=int(offset),
                status=_STATUS_PROCESSING,
            )
            try:
                s.add(row)
                s.flush()
                return True
            except IntegrityError:
                s.rollback()
                return False

        existing = s.execute(
            select(FeSubscriptionDedup).where(
                FeSubscriptionDedup.deployment_id == int(deployment_id),
                FeSubscriptionDedup.position_key == key,
            )
        ).scalar_one_or_none()
        if existing is None:
            s.add(
                FeSubscriptionDedup(
                    deployment_id=int(deployment_id),
                    position_key=key,
                    topic=topic,
                    partition=int(partition),
                    offset=int(offset),
                    status=_STATUS_PROCESSING,
                )
            )
        else:
            existing.status = _STATUS_PROCESSING
            existing.deploy_run_id = None
            existing.error = None
        return True


def finish_message_processing(
    *,
    deployment_id: int,
    topic: str,
    partition: int,
    offset: int,
    status: MessageStatus,
    deploy_run_id: int | None = None,
    error: str | None = None,
) -> None:
    """Persist terminal status (or failure) for a message position."""
    if status not in (_STATUS_COMPLETED, _STATUS_FAILED):
        raise ValueError(f"finish_message_processing expects completed/failed, got {status!r}")
    key = position_key(topic, partition, offset)
    with db_session() as s:
        row = s.execute(
            select(FeSubscriptionDedup).where(
                FeSubscriptionDedup.deployment_id == int(deployment_id),
                FeSubscriptionDedup.position_key == key,
            )
        ).scalar_one_or_none()
        if row is None:
            row = FeSubscriptionDedup(
                deployment_id=int(deployment_id),
                position_key=key,
                topic=topic,
                partition=int(partition),
                offset=int(offset),
                status=status,
                deploy_run_id=deploy_run_id,
                error=_truncate_error(error) if status == _STATUS_FAILED else None,
            )
            s.add(row)
            return
        row.status = status
        row.deploy_run_id = deploy_run_id
        row.error = _truncate_error(error) if status == _STATUS_FAILED else None


def try_claim_message(
    *,
    deployment_id: int,
    topic: str,
    partition: int,
    offset: int,
    window_s: int | None,
) -> bool:
    """Backward-compatible idempotency claim (processing row, no terminal status)."""
    return begin_message_processing(
        deployment_id=deployment_id,
        topic=topic,
        partition=partition,
        offset=offset,
        window_s=window_s,
        idempotency=True,
    )
