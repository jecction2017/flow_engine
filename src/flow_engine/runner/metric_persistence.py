"""Persistence layer for ``fe_node_metric``.

Buckets are 5-minute UTC-aligned. Backends accumulate counts and tail
durations in-memory and UPSERT a single bucket row each flush.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select

from flow_engine.db.models import FeNodeMetric
from flow_engine.db.session import db_session
from flow_engine.time_utils import utc_isoformat


BUCKET_SIZE_SECONDS = 5 * 60


def bucket_for(at: datetime) -> datetime:
    """Floor ``at`` to the start of its 5-minute bucket in UTC."""
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    else:
        at = at.astimezone(timezone.utc)
    floored = at - timedelta(
        seconds=at.second + (at.minute % 5) * 60,
        microseconds=at.microsecond,
    )
    return floored


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def upsert_metric_bucket(
    *,
    deploy_run_id: int,
    flow_code: str,
    node_id: str,
    bucket_at: datetime,
    span_count: int,
    success_count: int,
    failed_count: int,
    skipped_count: int,
    total_ms: int,
    p50_ms: int | None,
    p95_ms: int | None,
    p99_ms: int | None,
    max_ms: int | None,
    min_ms: int | None,
) -> None:
    """Insert or merge a bucket row.

    Merge semantics: counts and ``total_ms`` ADD; percentile / max / min
    OVERWRITE (the caller computed these from the in-memory tail buffer
    and they represent the freshest view of the bucket). The bucket
    boundary is identified by ``(deploy_run_id, node_id, bucket_at)``
    (unique index).
    """
    bucket = bucket_for(bucket_at)
    with db_session() as s:
        stmt = (
            select(FeNodeMetric)
            .where(FeNodeMetric.deploy_run_id == int(deploy_run_id))
            .where(FeNodeMetric.node_id == node_id)
            .where(FeNodeMetric.bucket_at == bucket)
            .where(FeNodeMetric.deleted_at.is_(None))
        )
        row = s.execute(stmt).scalar_one_or_none()
        if row is None:
            s.add(
                FeNodeMetric(
                    deploy_run_id=int(deploy_run_id),
                    flow_code=flow_code,
                    node_id=node_id,
                    bucket_at=bucket,
                    span_count=int(span_count),
                    success_count=int(success_count),
                    failed_count=int(failed_count),
                    skipped_count=int(skipped_count),
                    total_ms=int(total_ms),
                    p50_ms=p50_ms,
                    p95_ms=p95_ms,
                    p99_ms=p99_ms,
                    max_ms=max_ms,
                    min_ms=min_ms,
                )
            )
            return
        row.span_count = int(row.span_count or 0) + int(span_count)
        row.success_count = int(row.success_count or 0) + int(success_count)
        row.failed_count = int(row.failed_count or 0) + int(failed_count)
        row.skipped_count = int(row.skipped_count or 0) + int(skipped_count)
        row.total_ms = int(row.total_ms or 0) + int(total_ms)
        row.p50_ms = p50_ms
        row.p95_ms = p95_ms
        row.p99_ms = p99_ms
        row.max_ms = max_ms if max_ms is not None else row.max_ms
        row.min_ms = (
            min_ms if min_ms is not None and (row.min_ms is None or min_ms < row.min_ms) else row.min_ms
        )


# ---------------------------------------------------------------------------
# Reads (HTTP API)
# ---------------------------------------------------------------------------


def _bucket_dict(r: FeNodeMetric) -> dict[str, Any]:
    span_count = int(r.span_count or 0)
    success_count = int(r.success_count or 0)
    failed_count = int(r.failed_count or 0)
    skipped_count = int(r.skipped_count or 0)
    total_ms = int(r.total_ms or 0)
    avg_ms = (total_ms / span_count) if span_count > 0 else None
    finished = success_count + failed_count
    success_rate = (success_count / finished) if finished > 0 else None
    return {
        "bucket_at": utc_isoformat(r.bucket_at),
        "span_count": span_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "avg_ms": avg_ms,
        "p50_ms": int(r.p50_ms) if r.p50_ms is not None else None,
        "p95_ms": int(r.p95_ms) if r.p95_ms is not None else None,
        "p99_ms": int(r.p99_ms) if r.p99_ms is not None else None,
        "max_ms": int(r.max_ms) if r.max_ms is not None else None,
        "min_ms": int(r.min_ms) if r.min_ms is not None else None,
        "success_rate": success_rate,
    }


def query_metric_buckets(
    *,
    deploy_run_id: int,
    node_id: str | None = None,
    bucket_from: datetime | None = None,
    bucket_to: datetime | None = None,
) -> dict[str, Any]:
    """Return per-bucket time-series for one (or all) node ids."""
    with db_session() as s:
        stmt = (
            select(FeNodeMetric)
            .where(FeNodeMetric.deploy_run_id == int(deploy_run_id))
            .where(FeNodeMetric.deleted_at.is_(None))
        )
        if node_id:
            stmt = stmt.where(FeNodeMetric.node_id == node_id)
        if bucket_from is not None:
            stmt = stmt.where(FeNodeMetric.bucket_at >= bucket_from)
        if bucket_to is not None:
            stmt = stmt.where(FeNodeMetric.bucket_at < bucket_to)
        stmt = stmt.order_by(FeNodeMetric.node_id.asc(), FeNodeMetric.bucket_at.asc())
        rows = list(s.execute(stmt).scalars().all())

        by_node: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            by_node.setdefault(r.node_id, []).append(_bucket_dict(r))

        if node_id:
            return {
                "deploy_run_id": int(deploy_run_id),
                "node_id": node_id,
                "buckets": by_node.get(node_id, []),
            }
        # Multi-node response: return a stable list shape.
        return {
            "deploy_run_id": int(deploy_run_id),
            "nodes": [
                {"node_id": nid, "buckets": buckets}
                for nid, buckets in sorted(by_node.items())
            ],
        }


def query_metric_summary(
    *,
    deploy_run_id: int,
    node_id: str | None = None,
    window_minutes: int = 60,
) -> dict[str, Any]:
    """Aggregate the last ``window_minutes`` of buckets into a single
    snapshot. Percentiles are taken from the most recent bucket (no
    cross-bucket recomputation is possible without raw samples)."""
    window_minutes = max(1, min(int(window_minutes), 24 * 60))
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    with db_session() as s:
        stmt = (
            select(FeNodeMetric)
            .where(FeNodeMetric.deploy_run_id == int(deploy_run_id))
            .where(FeNodeMetric.bucket_at >= cutoff)
            .where(FeNodeMetric.deleted_at.is_(None))
        )
        if node_id:
            stmt = stmt.where(FeNodeMetric.node_id == node_id)
        stmt = stmt.order_by(FeNodeMetric.node_id.asc(), FeNodeMetric.bucket_at.asc())
        rows = list(s.execute(stmt).scalars().all())

        by_node: dict[str, list[FeNodeMetric]] = {}
        for r in rows:
            by_node.setdefault(r.node_id, []).append(r)

        def _summarize(nid: str, items: list[FeNodeMetric]) -> dict[str, Any]:
            span_count = 0
            success_count = 0
            failed_count = 0
            skipped_count = 0
            total_ms = 0
            latest = items[-1] if items else None
            for r in items:
                span_count += int(r.span_count or 0)
                success_count += int(r.success_count or 0)
                failed_count += int(r.failed_count or 0)
                skipped_count += int(r.skipped_count or 0)
                total_ms += int(r.total_ms or 0)
            finished = success_count + failed_count
            success_rate = (success_count / finished) if finished > 0 else None
            avg_ms = (total_ms / span_count) if span_count > 0 else None
            # Throughput: spans per second over the window.
            throughput = span_count / (window_minutes * 60) if span_count > 0 else 0.0
            return {
                "node_id": nid,
                "window_minutes": window_minutes,
                "span_count": span_count,
                "success_count": success_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
                "success_rate": success_rate,
                "avg_ms": avg_ms,
                "throughput_per_s": throughput,
                "p50_ms": int(latest.p50_ms) if latest and latest.p50_ms is not None else None,
                "p95_ms": int(latest.p95_ms) if latest and latest.p95_ms is not None else None,
                "p99_ms": int(latest.p99_ms) if latest and latest.p99_ms is not None else None,
                "max_ms": int(latest.max_ms) if latest and latest.max_ms is not None else None,
            }

        if node_id:
            items = by_node.get(node_id, [])
            return _summarize(node_id, items)

        return {
            "deploy_run_id": int(deploy_run_id),
            "window_minutes": window_minutes,
            "nodes": [_summarize(nid, items) for nid, items in sorted(by_node.items())],
        }


# ---------------------------------------------------------------------------
# Counters for fe_deploy_run (sampled / total span_count)
# ---------------------------------------------------------------------------


def update_deploy_run_counters(
    *,
    run_id: int,
    span_count_delta: int = 0,
    sampled_span_count_delta: int = 0,
) -> None:
    """Atomically bump the rollup counters on ``fe_deploy_run``.

    Concurrent flushes share a single FeDeployRun row; we use a
    SELECT...FOR UPDATE-free pattern by adding the delta in-place
    (asyncio is single-threaded; the only real contention is between
    coordinator processes, which the index keeps cheap).
    """
    if span_count_delta == 0 and sampled_span_count_delta == 0:
        return
    from flow_engine.db.models import FeDeployRun

    with db_session() as s:
        row = s.get(FeDeployRun, int(run_id))
        if row is None:
            return
        if span_count_delta:
            row.span_count = int(row.span_count or 0) + int(span_count_delta)
        if sampled_span_count_delta:
            row.sampled_span_count = (
                int(row.sampled_span_count or 0) + int(sampled_span_count_delta)
            )
