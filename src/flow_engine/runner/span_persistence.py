"""Persistence layer for ``fe_run_span``.

Only synchronous SQLAlchemy I/O — async callers wrap with
``asyncio.to_thread``. Designed for hot-path bulk writes from the
:class:`~flow_engine.runner.obs_backend.AsyncBufferedDBBackend` flush
loop and read-side serving of HTTP queries.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import delete, func, select, text as sql_text

from flow_engine.db.models import FeRunSpan
from flow_engine.db.session import db_session
from flow_engine.time_utils import utc_isoformat


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def batch_insert_spans(spans: Iterable[dict[str, Any]]) -> int:
    """Bulk-insert ``fe_run_span`` rows. Returns inserted count.

    Each input is a dict with the same keys as ``FeRunSpan``'s columns
    (the backend constructs them from :class:`SpanRecord`). Missing
    optional fields are filled with safe defaults.
    """
    rows: list[FeRunSpan] = []
    for spec in spans:
        rows.append(
            FeRunSpan(
                deploy_run_id=spec.get("deploy_run_id"),
                test_run_id=spec.get("test_run_id"),
                flow_code=spec.get("flow_code", "") or "",
                node_id=spec.get("node_id", "") or "",
                node_type=spec.get("node_type", "task") or "task",
                span_seq=int(spec.get("span_seq", 0) or 0),
                parent_span_id=spec.get("parent_span_id"),
                scope_key=spec.get("scope_key", "") or "",
                started_at=spec.get("started_at") or datetime.now(timezone.utc),
                finished_at=spec.get("finished_at"),
                duration_ms=spec.get("duration_ms"),
                status=spec.get("status", "running") or "running",
                error=spec.get("error"),
                child_spans=spec.get("child_spans"),
                logs=spec.get("logs"),
                attributes=spec.get("attributes"),
                sampled=int(bool(spec.get("sampled", True))),
            )
        )
    if not rows:
        return 0
    with db_session() as s:
        s.add_all(rows)
    return len(rows)


def update_span_parent(handle_to_id: dict[int, int]) -> None:
    """Rewrite parent_span_id from in-memory handles to DB ids.

    The backend assigns local sequence handles before flush; when a
    child span is flushed it stores the parent's HANDLE, not the DB id
    (the parent might not exist yet). After bulk INSERT we look up each
    inserted row's id and patch the children whose parent handle maps
    to it.

    In practice the backend handles this mapping in-memory during the
    flush loop and writes the final DB ids directly; this helper is
    retained for migration scripts / advanced use cases.
    """
    if not handle_to_id:
        return
    # No-op stub; the backend does the mapping in-memory now.
    return


# ---------------------------------------------------------------------------
# Reads (HTTP API)
# ---------------------------------------------------------------------------


def _log_count(r: FeRunSpan) -> int:
    raw = r.logs
    if raw is None:
        return 0
    if isinstance(raw, list):
        return len(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return 0
        return len(parsed) if isinstance(parsed, list) else 0
    return 0


def _row_to_summary(r: FeRunSpan) -> dict[str, Any]:
    return {
        "id": int(r.id),
        "deploy_run_id": int(r.deploy_run_id) if r.deploy_run_id is not None else None,
        "test_run_id": int(r.test_run_id) if r.test_run_id is not None else None,
        "flow_code": r.flow_code,
        "node_id": r.node_id,
        "node_type": r.node_type,
        "span_seq": int(r.span_seq or 0),
        "parent_span_id": int(r.parent_span_id) if r.parent_span_id is not None else None,
        "scope_key": r.scope_key or "",
        "started_at": utc_isoformat(r.started_at),
        "finished_at": utc_isoformat(r.finished_at),
        "duration_ms": int(r.duration_ms) if r.duration_ms is not None else None,
        "status": r.status,
        "error": r.error,
        "sampled": bool(r.sampled),
        "log_count": _log_count(r),
    }


def _row_to_detail(r: FeRunSpan) -> dict[str, Any]:
    out = _row_to_summary(r)
    out["child_spans"] = _normalize_json(r.child_spans)
    out["logs"] = _normalize_json(r.logs)
    out["attributes"] = _normalize_json(r.attributes)
    return out


def _normalize_json(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None
    return value


def list_spans(
    *,
    deploy_run_id: int | None = None,
    test_run_id: int | None = None,
    node_id: str | None = None,
    node_id_contains: str | None = None,
    status: str | None = None,
    scope_key: str | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    duration_min_ms: int | None = None,
    duration_max_ms: int | None = None,
    log_level: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Page through spans of a run with optional filters."""
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    if deploy_run_id is None and test_run_id is None:
        raise ValueError("list_spans requires deploy_run_id or test_run_id")
    with db_session() as s:
        stmt = select(FeRunSpan).where(FeRunSpan.deleted_at.is_(None))
        if deploy_run_id is not None:
            stmt = stmt.where(FeRunSpan.deploy_run_id == int(deploy_run_id))
        if test_run_id is not None:
            stmt = stmt.where(FeRunSpan.test_run_id == int(test_run_id))
        if node_id:
            stmt = stmt.where(FeRunSpan.node_id == node_id)
        elif node_id_contains and node_id_contains.strip():
            stmt = stmt.where(FeRunSpan.node_id.contains(node_id_contains.strip()))
        if status:
            stmt = stmt.where(FeRunSpan.status == status)
        if scope_key:
            stmt = stmt.where(FeRunSpan.scope_key == scope_key)
        if started_after is not None:
            stmt = stmt.where(FeRunSpan.started_at >= started_after)
        if started_before is not None:
            stmt = stmt.where(FeRunSpan.started_at < started_before)
        if duration_min_ms is not None:
            stmt = stmt.where(
                FeRunSpan.duration_ms.isnot(None),
                FeRunSpan.duration_ms >= int(duration_min_ms),
            )
        if duration_max_ms is not None:
            stmt = stmt.where(
                FeRunSpan.duration_ms.isnot(None),
                FeRunSpan.duration_ms <= int(duration_max_ms),
            )
        if log_level and log_level.strip():
            lvl = log_level.strip().lower()
            stmt = stmt.where(
                sql_text(
                    "JSON_SEARCH(fe_run_span.logs, 'one', :log_lvl, NULL, '$[*].level') IS NOT NULL",
                ).bindparams(log_lvl=lvl),
            )

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int(s.execute(count_stmt).scalar_one() or 0)

        page_stmt = stmt.order_by(FeRunSpan.started_at.desc(), FeRunSpan.id.desc()).offset(offset).limit(limit)
        rows = list(s.execute(page_stmt).scalars().all())
        items = [_row_to_summary(r) for r in rows]

        # Surface available node_ids so the UI can populate a filter
        # dropdown without an extra round-trip.
        node_ids_stmt = stmt.with_only_columns(FeRunSpan.node_id).distinct()
        node_ids = [str(x) for x in s.execute(node_ids_stmt).scalars().all() if x]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "node_ids": sorted(set(node_ids)),
        "items": items,
    }


def get_span(span_id: int) -> dict[str, Any] | None:
    with db_session() as s:
        row = s.get(FeRunSpan, int(span_id))
        if row is None or row.deleted_at is not None:
            return None
        return _row_to_detail(row)


def get_span_children(parent_span_id: int, *, limit: int = 200) -> list[dict[str, Any]]:
    """Return spans whose ``parent_span_id`` equals the given handle.

    Useful for nested-loop drill-down: a single parent span (e.g. outer
    customer iteration) can spawn many inner spans (e.g. per-order
    iterations).
    """
    limit = max(1, min(int(limit), 1000))
    with db_session() as s:
        stmt = (
            select(FeRunSpan)
            .where(FeRunSpan.parent_span_id == int(parent_span_id))
            .where(FeRunSpan.deleted_at.is_(None))
            .order_by(FeRunSpan.started_at.asc(), FeRunSpan.id.asc())
            .limit(limit)
        )
        return [_row_to_summary(r) for r in s.execute(stmt).scalars().all()]


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def purge_old_spans(
    *,
    retention_days: int,
    deploy_run_id: int | None = None,
    batch_size: int = 5000,
) -> int:
    """Delete spans older than ``retention_days``. Returns deleted count.

    Uses chunked DELETE WHERE id IN (...) for index-friendly deletion on
    MySQL; SQLite handles a single DELETE statement fine.
    """
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(retention_days))
    deleted_total = 0
    while True:
        with db_session() as s:
            sel = (
                select(FeRunSpan.id)
                .where(FeRunSpan.started_at < cutoff)
                .limit(batch_size)
            )
            if deploy_run_id is not None:
                sel = sel.where(FeRunSpan.deploy_run_id == int(deploy_run_id))
            ids = [int(x) for x in s.execute(sel).scalars().all()]
            if not ids:
                break
            res = s.execute(delete(FeRunSpan).where(FeRunSpan.id.in_(ids)))
            deleted_total += int(res.rowcount or 0)
        if len(ids) < batch_size:
            break
    return deleted_total
