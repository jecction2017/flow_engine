"""Persist test executions into ``fe_test_run`` (Test Center domain).

Per-node execution detail lives in ``fe_run_span`` keyed by ``test_run_id``.
This module handles lifecycle, ``flow_logs``, ``global_ns``, and listing.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from flow_engine.db.models import FeTestRun
from flow_engine.db.session import db_session
from flow_engine.time_utils import utc_isoformat


def _derive_case_key(trigger_context: Any) -> str:
    """Best-effort derive a stable case key from trigger_context."""
    if not isinstance(trigger_context, dict):
        return ""
    row = trigger_context.get("row")
    if not isinstance(row, dict):
        return ""
    for key in ("id", "code", "key", "case_id"):
        if key in row and row[key] is not None:
            return str(row[key])
    for k in sorted(row.keys()):
        if str(k).startswith("_expect"):
            continue
        v = row[k]
        if isinstance(v, (str, int, float, bool)) and not str(k).startswith("_"):
            return f"{k}={v}"
    try:
        raw = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    except (TypeError, ValueError):
        return ""


def create_test_run(
    *,
    test_batch_id: int,
    worker_id: str | None,
    flow_code: str,
    ver_no: int,
    trigger_context: dict[str, Any] | None,
) -> int:
    now = datetime.now(timezone.utc)
    case_key = _derive_case_key(trigger_context)
    with db_session() as s:
        row = FeTestRun(
            test_batch_id=int(test_batch_id),
            worker_id=worker_id,
            flow_code=flow_code,
            ver_no=int(ver_no),
            mode="debug",
            case_key=case_key,
            case_index=0,
            trigger_context=trigger_context,
            status="running",
            started_at=now,
        )
        s.add(row)
        s.flush()
        return int(row.id)


def complete_test_run(
    run_id: int,
    *,
    status: str,
    error: str | None,
    failure_detail: dict[str, Any] | None = None,
    flow_logs: list[dict[str, Any]] | None = None,
    global_ns: dict[str, Any] | None = None,
) -> None:
    """Finalize a test run. Detailed execution data is in ``fe_run_span``."""
    from flow_engine.runner.deploy_persistence import _normalize_flow_logs

    with db_session() as s:
        row = s.get(FeTestRun, int(run_id))
        if row is None:
            return
        row.status = status
        row.finished_at = datetime.now(timezone.utc)
        if error:
            row.error = error
        if failure_detail:
            row.failure_detail = dict(failure_detail)
        row.flow_logs = _normalize_flow_logs(flow_logs)
        row.global_ns = dict(global_ns) if global_ns else None


def fail_test_run(run_id: int, error: str) -> None:
    with db_session() as s:
        row = s.get(FeTestRun, int(run_id))
        if row is None:
            return
        row.status = "failed"
        row.finished_at = datetime.now(timezone.utc)
        row.error = error


def set_test_run_evaluation(run_id: int, evaluation: dict[str, Any]) -> None:
    with db_session() as s:
        row = s.get(FeTestRun, int(run_id))
        if row is None:
            return
        row.evaluation = evaluation


def list_test_runs(
    *,
    test_batch_id: int,
    status: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    with db_session() as s:
        stmt = (
            select(FeTestRun)
            .where(FeTestRun.deleted_at.is_(None))
            .where(FeTestRun.test_batch_id == int(test_batch_id))
            .order_by(FeTestRun.id.asc())
        )
        if status:
            stmt = stmt.where(FeTestRun.status == status)
        rows = list(s.execute(stmt).scalars().all())
        # Provide stable batch-local indices if missing.
        for i, r in enumerate(rows):
            if not int(getattr(r, "case_index", 0) or 0):
                r.case_index = i + 1
        total = len(rows)
        page = rows[offset : offset + limit]

        def _brief(r: FeTestRun) -> dict[str, Any]:
            ev_raw = getattr(r, "evaluation", None)
            ev = ev_raw if isinstance(ev_raw, dict) else None
            return {
                "id": int(r.id),
                "test_batch_id": int(r.test_batch_id),
                "flow_code": r.flow_code,
                "ver_no": int(r.ver_no),
                "mode": r.mode,
                "status": r.status,
                "worker_id": r.worker_id,
                "started_at": utc_isoformat(r.started_at),
                "finished_at": utc_isoformat(r.finished_at),
                "case_index": int(r.case_index or 0) or None,
                "case_key": r.case_key or None,
                "verdict": (ev or {}).get("verdict") if ev else None,
            }

        return {"total": total, "offset": offset, "limit": limit, "runs": [_brief(r) for r in page]}


def get_test_run_detail(run_id: int) -> dict[str, Any] | None:
    with db_session() as s:
        row = s.get(FeTestRun, int(run_id))
        if row is None or row.deleted_at is not None:
            return None
        ev_raw = getattr(row, "evaluation", None)
        evaluation = ev_raw if isinstance(ev_raw, dict) else None
        return {
            "id": int(row.id),
            "test_batch_id": int(row.test_batch_id),
            "worker_id": row.worker_id,
            "flow_code": row.flow_code,
            "ver_no": int(row.ver_no),
            "mode": row.mode,
            "case_key": row.case_key,
            "case_index": int(row.case_index or 0) or None,
            "trigger_context": row.trigger_context,
            "status": row.status,
            "started_at": utc_isoformat(row.started_at),
            "finished_at": utc_isoformat(row.finished_at),
            "error": row.error,
            "failure_detail": (
                dict(row.failure_detail) if row.failure_detail else None
            ),
            "evaluation": evaluation,
            "flow_logs": list(row.flow_logs) if row.flow_logs else None,
            "global_ns": dict(row.global_ns) if row.global_ns else None,
        }


def summarize_batch_runs(test_batch_id: int, *, failure_limit: int = 10) -> dict[str, Any]:
    # Build immutable snapshots inside the Session to avoid DetachedInstanceError.
    with db_session() as s:
        stmt = (
            select(FeTestRun)
            .where(FeTestRun.test_batch_id == int(test_batch_id))
            .where(FeTestRun.deleted_at.is_(None))
            .order_by(FeTestRun.id.asc())
        )
        rows = list(s.execute(stmt).scalars().all())
        snaps: list[dict[str, Any]] = []
        for i, r in enumerate(rows):
            ev_raw = getattr(r, "evaluation", None)
            ev = ev_raw if isinstance(ev_raw, dict) else None
            snaps.append(
                {
                    "id": int(r.id),
                    "status": str(r.status),
                    "case_index": int(r.case_index or 0) or (i + 1),
                    "case_key": (r.case_key or "")[:2000] or None,
                    "evaluation": ev,
                    "error": (r.error or "")[:2000] if r.error else None,
                }
            )

    by_status: dict[str, int] = {}
    verdict_counts = {"pass": 0, "fail": 0, "none": 0}
    first_failures: list[dict[str, Any]] = []
    for snap in snaps:
        st = snap["status"]
        by_status[st] = by_status.get(st, 0) + 1
        ev = snap.get("evaluation") or {}
        verdict = ev.get("verdict") if isinstance(ev, dict) else None
        if verdict == "pass":
            verdict_counts["pass"] += 1
        elif verdict == "fail":
            verdict_counts["fail"] += 1
        else:
            verdict_counts["none"] += 1

        flow_bad = st in ("failed", "terminated")
        assert_bad = verdict == "fail"
        if (flow_bad or assert_bad) and len(first_failures) < failure_limit:
            first_failures.append(
                {
                    "run_id": int(snap["id"]),
                    "case_index": int(snap["case_index"]),
                    "case_key": snap.get("case_key"),
                    "status": st,
                    "verdict": verdict,
                    "error": snap.get("error"),
                }
            )

    return {"by_status": by_status, "verdict_counts": verdict_counts, "first_failures": first_failures}


def compare_test_batches(left_batch_id: int, right_batch_id: int) -> dict[str, Any]:
    def _load(batch_id: int) -> dict[str, dict[str, Any]]:
        with db_session() as s:
            stmt = (
                select(FeTestRun)
                .where(FeTestRun.test_batch_id == int(batch_id))
                .where(FeTestRun.deleted_at.is_(None))
            )
            rows = list(s.execute(stmt).scalars().all())
            out: dict[str, dict[str, Any]] = {}
            for r in rows:
                ev_raw = getattr(r, "evaluation", None)
                ev = ev_raw if isinstance(ev_raw, dict) else {}
                k = (r.case_key or "").strip() or f"run:{int(r.id)}"
                out[k] = {"id": int(r.id), "status": str(r.status), "verdict": ev.get("verdict")}
            return out

    lm, rm = _load(left_batch_id), _load(right_batch_id)

    def _brief(snap: dict[str, Any] | None) -> dict[str, Any] | None:
        if snap is None:
            return None
        return {"run_id": int(snap["id"]), "status": snap.get("status"), "verdict": snap.get("verdict")}

    keys = sorted(set(lm.keys()) | set(rm.keys()))
    cases: list[dict[str, Any]] = []
    for k in keys:
        l, r = lm.get(k), rm.get(k)
        sl, sr = _brief(l), _brief(r)
        cases.append({"case_key": k, "left": sl, "right": sr, "changed": sl != sr})
    return {"left_batch_id": int(left_batch_id), "right_batch_id": int(right_batch_id), "cases": cases}
