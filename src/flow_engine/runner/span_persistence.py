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

from sqlalchemy import delete, select, text as sql_text

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


_MAX_MATCHED = 10_000
"""Hard cap on the filter-hit set size before tree expansion.

Tuned for 10M-scale ``fe_run_span`` tables: bounded matched-set keeps the
recursive CTE for ancestor / descendant expansion cheap. Exceeding the cap
surfaces ``truncated.matched=True`` so the UI can prompt the user to
refine filters instead of silently dropping results.
"""

_MAX_RETURNED_PER_PAGE = 5_000
"""Hard cap on spans returned in a single page after tree expansion.

Even with bounded matched-set, a small filter hit can expand to a huge
subtree when ``include_descendants=True`` on a deep parent. This cap keeps
each page's wire + browser cost predictable; over-limit pages are
truncated by full root-subtree to preserve tree integrity, with
``truncated.returned=True`` flagged.
"""


def _apply_run_scope(
    stmt: Any,
    *,
    deploy_run_id: int | None,
    test_run_id: int | None,
) -> Any:
    """Restrict a select to a single run + non-deleted, non-synthetic spans.

    Legacy ``node_type='flow_root'`` rows (a UX scaffold previously
    emitted for once/cron/test runs) are filtered out unconditionally so
    the visible 执行链路 forest matches the new write-side behaviour for
    every run, including historical ones still on disk.
    """
    stmt = stmt.where(FeRunSpan.deleted_at.is_(None))
    stmt = stmt.where(FeRunSpan.node_type != "flow_root")
    if deploy_run_id is not None:
        stmt = stmt.where(FeRunSpan.deploy_run_id == int(deploy_run_id))
    if test_run_id is not None:
        stmt = stmt.where(FeRunSpan.test_run_id == int(test_run_id))
    return stmt


def _apply_span_filters(
    stmt: Any,
    *,
    node_id: str | None,
    node_id_contains: str | None,
    status: str | None,
    scope_key: str | None,
    started_after: datetime | None,
    started_before: datetime | None,
    duration_min_ms: int | None,
    duration_max_ms: int | None,
    log_level: str | None,
) -> Any:
    """Translate UI filter knobs into WHERE clauses."""
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
        # MySQL-only JSON_SEARCH path (SQLite tests skip log_level filter).
        stmt = stmt.where(
            sql_text(
                "JSON_SEARCH(fe_run_span.logs, 'one', :log_lvl, NULL, '$[*].level') IS NOT NULL",
            ).bindparams(log_lvl=lvl),
        )
    return stmt


_EXPAND_MAX_DEPTH = 200
"""Safety bound on iterative tree-walk depth.

Real execution trees rarely exceed a few dozen levels (loop nesting +
subflow depth). The hard cap exists only so a hypothetical cycle in
``parent_span_id`` cannot turn this function into an infinite loop —
which the ORM's referential integrity does not enforce.
"""

_EXPAND_LAYER_CAP = 50_000
"""Hard cap on the IN-list size per BFS step.

Keeps each batched query bounded so a pathological wide layer cannot
generate a multi-MB SQL statement. Layers larger than this are split
into multiple queries.
"""


def _expand_ids_iterative(
    session: Any,
    seed_ids: list[int] | set[int],
    *,
    direction: str,
) -> set[int]:
    """Breadth-first walk of ``parent_span_id`` edges from ``seed_ids``.

    ``direction='up'`` returns ``seed ∪ ancestors``; ``direction='down'``
    returns ``seed ∪ descendants``. Implemented as a sequence of
    ``WHERE id IN (...)`` / ``WHERE parent_span_id IN (...)`` queries
    instead of a recursive CTE so the code works on MySQL 5.7 (no CTE
    support) in addition to MySQL 8+ and SQLite.

    Each layer is a single indexed lookup against ``idx_fe_run_span_parent``;
    typical execution trees terminate in well under 10 iterations.
    """
    if not seed_ids:
        return set()
    visited: set[int] = {int(x) for x in seed_ids}
    frontier: set[int] = set(visited)

    for _ in range(_EXPAND_MAX_DEPTH):
        if not frontier:
            break
        # Process the frontier in chunks to keep IN-list size bounded.
        frontier_list = list(frontier)
        next_frontier: set[int] = set()
        for start in range(0, len(frontier_list), _EXPAND_LAYER_CAP):
            chunk = frontier_list[start : start + _EXPAND_LAYER_CAP]
            if direction == "up":
                # Fetch parent_span_id values for the current frontier; any
                # non-null parent that we have not visited becomes the next
                # frontier.
                q = (
                    select(FeRunSpan.parent_span_id)
                    .where(FeRunSpan.id.in_(chunk))
                    .where(FeRunSpan.parent_span_id.is_not(None))
                    .where(FeRunSpan.deleted_at.is_(None))
                )
            elif direction == "down":
                # Fetch ids of direct children of the current frontier.
                q = (
                    select(FeRunSpan.id)
                    .where(FeRunSpan.parent_span_id.in_(chunk))
                    .where(FeRunSpan.deleted_at.is_(None))
                )
            else:
                raise ValueError(
                    f"_expand_ids_iterative: invalid direction {direction!r}"
                )
            for value in session.execute(q).scalars().all():
                if value is None:
                    continue
                next_frontier.add(int(value))
        # Subtract already-visited so the loop converges; remaining ids
        # become the next BFS layer.
        next_frontier -= visited
        if not next_frontier:
            break
        visited.update(next_frontier)
        frontier = next_frontier

    return visited


def list_spans_forest(
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
    include_descendants: bool = False,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """List spans of a run as a well-formed forest, paginated by root subtree.

    Invariant: for every returned ``items[i]``, ``parent_span_id`` is either
    NULL or refers to another span present in the same ``items``. Filtering
    and pagination cannot break the tree structure.

    Modes:
      - No filter applied: directly paginate roots (``parent_span_id IS
        NULL``) of the run, then fetch each root's full subtree.
      - Filter applied: matched set → optional descendant expansion →
        mandatory ancestor expansion → paginate roots of the expanded set.
        Children that match always carry their full ancestor chain;
        ``include_descendants`` additionally pulls down a matched parent's
        whole subtree.

    Caps (``_MAX_MATCHED``, ``_MAX_RETURNED_PER_PAGE``) keep the query and
    response bounded on 10M-scale tables. Either cap hit raises a flag in
    ``truncated`` so the UI can prompt for filter refinement instead of
    silently truncating.
    """
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    if deploy_run_id is None and test_run_id is None:
        raise ValueError("list_spans_forest requires deploy_run_id or test_run_id")

    has_filter = any(
        [
            bool(node_id),
            bool(node_id_contains and node_id_contains.strip()),
            bool(status),
            bool(scope_key),
            started_after is not None,
            started_before is not None,
            duration_min_ms is not None,
            duration_max_ms is not None,
            bool(log_level and log_level.strip()),
        ]
    )

    truncated = {"matched": False, "returned": False}

    with db_session() as s:
        # Step A: build the universe of span ids the page will draw from.
        if has_filter:
            # Filter-hit set, capped to keep BFS expansion bounded.
            matched_stmt = select(FeRunSpan.id)
            matched_stmt = _apply_run_scope(
                matched_stmt,
                deploy_run_id=deploy_run_id,
                test_run_id=test_run_id,
            )
            matched_stmt = _apply_span_filters(
                matched_stmt,
                node_id=node_id,
                node_id_contains=node_id_contains,
                status=status,
                scope_key=scope_key,
                started_after=started_after,
                started_before=started_before,
                duration_min_ms=duration_min_ms,
                duration_max_ms=duration_max_ms,
                log_level=log_level,
            )
            matched_stmt = matched_stmt.order_by(
                FeRunSpan.started_at.desc(), FeRunSpan.id.desc()
            ).limit(_MAX_MATCHED + 1)
            matched_ids = [int(x) for x in s.execute(matched_stmt).scalars().all()]
            if len(matched_ids) > _MAX_MATCHED:
                truncated["matched"] = True
                matched_ids = matched_ids[:_MAX_MATCHED]
            total_matched = len(matched_ids)

            if not matched_ids:
                # No hits → empty forest. Skip expansion + node_ids work.
                final_ids: set[int] = set()
            else:
                expanded_ids: set[int]
                if include_descendants:
                    expanded_ids = _expand_ids_iterative(
                        s, matched_ids, direction="down"
                    )
                else:
                    expanded_ids = set(matched_ids)
                final_ids = _expand_ids_iterative(
                    s, expanded_ids, direction="up"
                )
        else:
            total_matched = None
            final_ids = None  # signal "all spans of this run"

        # Step B: fetch row data within the run scope, restricted to
        # ``final_ids`` if filtering was applied. The BFS expansion only
        # returned ids; we still need the column data + parent linkage.
        row_stmt = select(FeRunSpan)
        row_stmt = _apply_run_scope(
            row_stmt,
            deploy_run_id=deploy_run_id,
            test_run_id=test_run_id,
        )
        if final_ids is not None:
            if not final_ids:
                rows: list[FeRunSpan] = []
            else:
                row_stmt = row_stmt.where(FeRunSpan.id.in_(final_ids))
                rows = list(s.execute(row_stmt).scalars().all())
        else:
            rows = list(s.execute(row_stmt).scalars().all())

        # Step C: identify roots — a span is a root of the result forest
        # when its parent_span_id is either NULL or not present in the
        # current rows. Sort roots by recency (matches axis "执行先后").
        present_ids = {int(r.id) for r in rows}
        roots = [
            r
            for r in rows
            if r.parent_span_id is None or int(r.parent_span_id) not in present_ids
        ]
        roots.sort(
            key=lambda r: (
                r.started_at.timestamp() if r.started_at is not None else 0.0,
                int(r.id),
            ),
            reverse=True,
        )
        total_roots = len(roots)

        page_root_objs = roots[offset : offset + limit]
        page_root_ids = {int(r.id) for r in page_root_objs}

        # Step D: map every row to the root of its connected component
        # within ``rows``. Memoized walk: O(|rows|).
        rows_by_id = {int(r.id): r for r in rows}
        root_of: dict[int, int] = {}

        def _find_root(rid: int) -> int:
            path: list[int] = []
            cur = rid
            while cur not in root_of:
                path.append(cur)
                node = rows_by_id[cur]
                pid = (
                    int(node.parent_span_id)
                    if node.parent_span_id is not None
                    else None
                )
                if pid is None or pid not in rows_by_id:
                    for x in path:
                        root_of[x] = cur
                    return cur
                cur = pid
            for x in path:
                root_of[x] = root_of[cur]
            return root_of[cur]

        for r in rows:
            _find_root(int(r.id))

        # Step E: select rows belonging to the paginated roots. Sort for
        # deterministic wire order: per-root sub-rows by (depth, span_seq,
        # id) — frontend rebuilds the tree by parent_span_id anyway, but
        # deterministic ordering makes debugging + snapshot tests stable.
        page_rows = [r for r in rows if root_of[int(r.id)] in page_root_ids]

        # Step F: enforce per-page span cap by dropping whole root subtrees
        # from the tail. Tree integrity wins over filling the cap exactly.
        if len(page_rows) > _MAX_RETURNED_PER_PAGE:
            truncated["returned"] = True
            by_root: dict[int, list[FeRunSpan]] = {}
            for r in page_rows:
                by_root.setdefault(root_of[int(r.id)], []).append(r)
            kept: list[FeRunSpan] = []
            for root_obj in page_root_objs:
                subtree = by_root.get(int(root_obj.id), [])
                if kept and len(kept) + len(subtree) > _MAX_RETURNED_PER_PAGE:
                    break
                kept.extend(subtree)
                if len(kept) >= _MAX_RETURNED_PER_PAGE:
                    break
            page_rows = kept

        page_rows.sort(
            key=lambda r: (
                r.started_at.timestamp() if r.started_at is not None else 0.0,
                int(r.span_seq or 0),
                int(r.id),
            )
        )

        # Step G: distinct node_ids of the run (drives the filter dropdown).
        # Use unfiltered run scope so the dropdown surfaces ALL node_ids the
        # user could pick, not just those currently matching.
        node_ids_stmt = (
            select(FeRunSpan.node_id).distinct()
        )
        node_ids_stmt = _apply_run_scope(
            node_ids_stmt,
            deploy_run_id=deploy_run_id,
            test_run_id=test_run_id,
        )
        node_ids = sorted(
            {str(x) for x in s.execute(node_ids_stmt).scalars().all() if x}
        )

        # Serialize rows while the session is still open. ``_row_to_summary``
        # touches mapped attributes; once the session closes, detached
        # instances raise on attribute access.
        items = [_row_to_summary(r) for r in page_rows]
    total_returned = len(items)

    # Backwards-compatible ``total``: callers prior to the forest refactor
    # treated this as "how many things are there to page through". For
    # filtered queries that is the filter-hit count; otherwise it is the
    # forest's total root count.
    legacy_total = total_matched if has_filter else total_roots

    return {
        "items": items,
        "offset": offset,
        "limit": limit,
        "total_roots": total_roots,
        "total_matched": total_matched,
        "total_returned": total_returned,
        "total": legacy_total,
        "truncated": truncated,
        "node_ids": node_ids,
        "include_descendants": bool(include_descendants),
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
