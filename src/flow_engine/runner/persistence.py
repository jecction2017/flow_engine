"""Persist FlowRunResult into ``fe_flow_run``.

Resident vs once/cron/test 写入策略不同（设计文档 §7.4）：
* once/cron/test：``node_runs`` 写入完整 ``list[NodeRunInfo.to_dict()]`` JSON
* resident       ：``node_stats`` 写入聚合统计；不写 node_runs；
                    ``iteration_count`` 由 worker 后台 Task 周期更新

所有函数均同步（SQLAlchemy 是同步的）；async 调用方需用
``asyncio.to_thread`` 包装。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from statistics import mean
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from flow_engine.db.models import FeFlowRun
from flow_engine.db.session import db_session
from flow_engine.time_utils import utc_isoformat

if TYPE_CHECKING:
    from flow_engine.engine.models import FlowState
    from flow_engine.engine.orchestrator import FlowRunResult, NodeRunInfo
    from flow_engine.runner.models import RunMode


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def create_flow_run(
    *,
    deployment_id: int | None,
    test_batch_id: int | None,
    worker_id: str | None,
    flow_code: str,
    ver_no: int,
    mode: "RunMode",
    trigger_context: dict[str, Any] | None,
) -> int:
    """Insert ``FeFlowRun(status='running')`` and return the new run id."""
    now = datetime.now(timezone.utc)
    with db_session() as s:
        row = FeFlowRun(
            deployment_id=deployment_id,
            test_batch_id=test_batch_id,
            worker_id=worker_id,
            flow_code=flow_code,
            ver_no=ver_no,
            mode=mode.value,
            trigger_context=trigger_context,
            status="running",
            started_at=now,
        )
        s.add(row)
        s.flush()
        return int(row.id)


def complete_flow_run(
    run_id: int,
    result: "FlowRunResult",
    *,
    is_resident: bool,
) -> None:
    """Mark a run finished according to ``result.state`` and persist payloads.

    ``is_resident`` controls the column used:
        * False → ``node_runs`` JSON (full per-node trace)
        * True  → ``node_stats`` JSON (aggregate counters), no node_runs
    """
    from flow_engine.engine.models import FlowState

    state = result.state
    if state == FlowState.COMPLETED:
        status = "completed"
    elif state == FlowState.TERMINATED:
        status = "terminated"
    else:
        status = "failed"

    flow_logs_json = json.dumps(result.flow_logs, ensure_ascii=False, default=str)
    global_ns: dict[str, Any] | None = None
    try:
        # Keep behaviour consistent with /api/flows/{flow_id}/run: strip dictionary from output.
        global_ns = dict(getattr(result.context, "global_ns", {}) or {})
        global_ns.pop("dictionary", None)
    except Exception:  # noqa: BLE001
        global_ns = None
    payload: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc),
        "flow_logs": flow_logs_json,
    }
    if global_ns is not None:
        payload["global_ns"] = json.dumps(global_ns, ensure_ascii=False, default=str)
    if result.message:
        payload["error"] = result.message

    if is_resident:
        payload["node_stats"] = json.dumps(
            _aggregate_node_stats(result.node_runs),
            ensure_ascii=False,
            default=str,
        )
    else:
        payload["node_runs"] = json.dumps(
            [r.to_dict() for r in result.node_runs],
            ensure_ascii=False,
            default=str,
        )

    with db_session() as s:
        row = s.get(FeFlowRun, run_id)
        if row is None:
            return
        for k, v in payload.items():
            setattr(row, k, v)


def fail_flow_run(run_id: int, error: str) -> None:
    """Mark a run failed when no FlowRunResult is available (Worker exception path)."""
    with db_session() as s:
        row = s.get(FeFlowRun, run_id)
        if row is None:
            return
        row.status = "failed"
        row.finished_at = datetime.now(timezone.utc)
        row.error = error


def set_flow_run_evaluation(run_id: int, evaluation: dict[str, Any]) -> None:
    with db_session() as s:
        row = s.get(FeFlowRun, run_id)
        if row is None:
            return
        row.evaluation = evaluation


def update_iteration_count(run_id: int, count: int) -> None:
    with db_session() as s:
        row = s.get(FeFlowRun, run_id)
        if row is None:
            return
        row.iteration_count = int(count)


def update_node_stats(run_id: int, stats: dict[str, Any]) -> None:
    with db_session() as s:
        row = s.get(FeFlowRun, run_id)
        if row is None:
            return
        row.node_stats = json.dumps(stats, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Listing helpers (used by HTTP API)
# ---------------------------------------------------------------------------


def _derive_case_key(trigger_context: Any) -> str:
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


def summarize_batch_runs(test_batch_id: int, *, failure_limit: int = 10) -> dict[str, Any]:
    """Aggregate run rows while still bound to a Session (avoid DetachedInstanceError)."""
    with db_session() as s:
        stmt = (
            select(FeFlowRun)
            .where(FeFlowRun.test_batch_id == test_batch_id)
            .where(FeFlowRun.deleted_at.is_(None))
        )
        rows = list(s.execute(stmt).scalars().all())
        snapshots: list[dict[str, Any]] = []
        for r in rows:
            ev_raw = getattr(r, "evaluation", None)
            ev = ev_raw if isinstance(ev_raw, dict) else None
            tc = r.trigger_context
            snapshots.append(
                {
                    "id": int(r.id),
                    "status": str(r.status),
                    "evaluation": ev,
                    "trigger_context": tc if isinstance(tc, dict) else None,
                    "error": r.error,
                }
            )

    by_status: dict[str, int] = {}
    for snap in snapshots:
        st = snap["status"]
        by_status[st] = by_status.get(st, 0) + 1
    ordered = sorted(snapshots, key=lambda x: int(x["id"]))
    idx_map = {int(x["id"]): i + 1 for i, x in enumerate(ordered)}
    verdict_counts = {"pass": 0, "fail": 0, "none": 0}
    first_failures: list[dict[str, Any]] = []
    for snap in ordered:
        ev = snap.get("evaluation")
        verdict = (ev or {}).get("verdict") if ev else None
        if verdict == "pass":
            verdict_counts["pass"] += 1
        elif verdict == "fail":
            verdict_counts["fail"] += 1
        else:
            verdict_counts["none"] += 1

        st = snap["status"]
        flow_bad = st in ("failed", "terminated")
        assert_bad = verdict == "fail"
        if (flow_bad or assert_bad) and len(first_failures) < failure_limit:
            tc = snap.get("trigger_context")
            err = snap.get("error")
            first_failures.append(
                {
                    "run_id": int(snap["id"]),
                    "case_index": idx_map.get(int(snap["id"]), 0),
                    "case_key": _derive_case_key(tc),
                    "status": st,
                    "verdict": verdict,
                    "error": (err or "")[:2000] if err else None,
                }
            )
    return {
        "by_status": by_status,
        "verdict_counts": verdict_counts,
        "first_failures": first_failures,
    }


def compare_test_batches(left_batch_id: int, right_batch_id: int) -> dict[str, Any]:
    """Align runs by ``case_key`` and compare status / assertion verdict."""

    def _load_snapshots(batch_id: int) -> list[dict[str, Any]]:
        with db_session() as s:
            stmt = (
                select(FeFlowRun)
                .where(FeFlowRun.test_batch_id == batch_id)
                .where(FeFlowRun.deleted_at.is_(None))
            )
            rows = list(s.execute(stmt).scalars().all())
            out: list[dict[str, Any]] = []
            for r in rows:
                ev_raw = getattr(r, "evaluation", None)
                ev = ev_raw if isinstance(ev_raw, dict) else {}
                tc = r.trigger_context
                out.append(
                    {
                        "id": int(r.id),
                        "status": str(r.status),
                        "verdict": ev.get("verdict"),
                        "trigger_context": tc if isinstance(tc, dict) else None,
                    }
                )
            return out

    def _index(snaps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        keyed: dict[str, dict[str, Any]] = {}
        for snap in snaps:
            tc = snap.get("trigger_context")
            k = _derive_case_key(tc) if isinstance(tc, dict) else ""
            if not k:
                k = f"run:{snap['id']}"
            keyed[k] = snap
        return keyed

    left_snaps = _load_snapshots(left_batch_id)
    right_snaps = _load_snapshots(right_batch_id)
    lm, rm = _index(left_snaps), _index(right_snaps)

    def _brief(snap: dict[str, Any] | None) -> dict[str, Any] | None:
        if snap is None:
            return None
        return {
            "run_id": int(snap["id"]),
            "status": snap["status"],
            "verdict": snap.get("verdict"),
        }

    keys = sorted(set(lm.keys()) | set(rm.keys()))
    cases: list[dict[str, Any]] = []
    for k in keys:
        l_snap, r_snap = lm.get(k), rm.get(k)
        sl, sr = _brief(l_snap), _brief(r_snap)
        changed = sl != sr
        cases.append({"case_key": k, "left": sl, "right": sr, "changed": changed})
    return {
        "left_batch_id": int(left_batch_id),
        "right_batch_id": int(right_batch_id),
        "cases": cases,
    }


def list_flow_runs(
    *,
    deployment_id: int | None = None,
    test_batch_id: int | None = None,
    source: str | None = None,
    flow_code: str | None = None,
    mode: str | None = None,
    status: str | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    with db_session() as s:
        stmt = select(FeFlowRun).where(FeFlowRun.deleted_at.is_(None))
        if source:
            src = source.strip().lower()
            if src in {"deployment", "prod", "production"}:
                stmt = stmt.where(FeFlowRun.deployment_id.is_not(None))
            elif src in {"test_batch", "test", "batch"}:
                stmt = stmt.where(FeFlowRun.test_batch_id.is_not(None))
            elif src in {"adhoc", "ad_hoc", "debug"}:
                stmt = stmt.where(FeFlowRun.deployment_id.is_(None)).where(
                    FeFlowRun.test_batch_id.is_(None)
                )
            else:
                raise ValueError(
                    "source must be one of: deployment | test_batch | adhoc"
                )
        if deployment_id is not None:
            stmt = stmt.where(FeFlowRun.deployment_id == deployment_id)
        if test_batch_id is not None:
            stmt = stmt.where(FeFlowRun.test_batch_id == test_batch_id)
        if flow_code:
            stmt = stmt.where(FeFlowRun.flow_code == flow_code)
        if mode:
            stmt = stmt.where(FeFlowRun.mode == mode)
        if status:
            stmt = stmt.where(FeFlowRun.status == status)
        if started_after is not None:
            stmt = stmt.where(FeFlowRun.started_at >= started_after)
        if started_before is not None:
            stmt = stmt.where(FeFlowRun.started_at < started_before)
        stmt = stmt.order_by(FeFlowRun.started_at.desc())

        all_rows = list(s.execute(stmt).scalars().all())
        total = len(all_rows)
        page = all_rows[offset : offset + limit]
        case_index_by_id: dict[int, int] = {}
        if test_batch_id is not None and all_rows:
            ordered = sorted(all_rows, key=lambda x: int(x.id))
            case_index_by_id = {int(r.id): i + 1 for i, r in enumerate(ordered)}

        def _run_dict(r: FeFlowRun) -> dict[str, Any]:
            ev_raw = getattr(r, "evaluation", None)
            ev = ev_raw if isinstance(ev_raw, dict) else None
            if r.deployment_id is not None:
                run_source = "deployment"
            elif r.test_batch_id is not None:
                run_source = "test_batch"
            else:
                run_source = "adhoc"
            base: dict[str, Any] = {
                "id": r.id,
                "deployment_id": r.deployment_id,
                "test_batch_id": r.test_batch_id,
                "source": run_source,
                "flow_code": r.flow_code,
                "ver_no": r.ver_no,
                "mode": r.mode,
                "status": r.status,
                "worker_id": r.worker_id,
                "started_at": utc_isoformat(r.started_at),
                "finished_at": utc_isoformat(r.finished_at),
                "iteration_count": r.iteration_count,
                "error": r.error,
            }
            if test_batch_id is not None:
                base["case_index"] = case_index_by_id.get(int(r.id))
                base["case_key"] = _derive_case_key(
                    r.trigger_context if isinstance(r.trigger_context, dict) else None
                )
                base["verdict"] = (ev or {}).get("verdict") if ev else None
            return base

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "runs": [_run_dict(r) for r in page],
        }


def get_flow_run_detail(run_id: int) -> dict[str, Any] | None:
    with db_session() as s:
        row = s.get(FeFlowRun, run_id)
        if row is None or row.deleted_at is not None:
            return None
        node_runs = _safe_json_load(row.node_runs)
        node_stats = _safe_json_load(row.node_stats)
        flow_logs = _safe_json_load(row.flow_logs)
        global_ns = _safe_json_load(row.global_ns)
        ev_raw = getattr(row, "evaluation", None)
        evaluation = ev_raw if isinstance(ev_raw, dict) else None
        if row.deployment_id is not None:
            run_source = "deployment"
        elif row.test_batch_id is not None:
            run_source = "test_batch"
        else:
            run_source = "adhoc"
        return {
            "id": row.id,
            "deployment_id": row.deployment_id,
            "test_batch_id": row.test_batch_id,
            "source": run_source,
            "worker_id": row.worker_id,
            "flow_code": row.flow_code,
            "ver_no": row.ver_no,
            "mode": row.mode,
            "trigger_context": row.trigger_context,
            "status": row.status,
            "started_at": utc_isoformat(row.started_at),
            "finished_at": utc_isoformat(row.finished_at),
            "iteration_count": row.iteration_count,
            "node_runs": node_runs,
            "node_stats": node_stats,
            "flow_logs": flow_logs,
            "global_ns": global_ns,
            "error": row.error,
            "evaluation": evaluation,
        }


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _aggregate_node_stats(runs: "list[NodeRunInfo]") -> dict[str, Any]:
    """Roll ``NodeRunInfo`` list into per-node counters for resident persistence."""
    from flow_engine.engine.models import NodeState

    per_node: dict[str, dict[str, Any]] = {}
    for r in runs:
        rec = per_node.setdefault(
            r.node_id,
            {"count": 0, "success": 0, "failed": 0, "_durations": []},
        )
        rec["count"] += 1
        if r.final_state == NodeState.SUCCESS:
            rec["success"] += 1
        elif r.final_state == NodeState.FAILED:
            rec["failed"] += 1
        if r.duration_ms is not None:
            rec["_durations"].append(r.duration_ms)
    out_per_node: dict[str, Any] = {}
    for node_id, rec in per_node.items():
        durs: list[int] = rec.pop("_durations")
        rec["avg_ms"] = int(round(mean(durs))) if durs else 0
        rec["p99_ms"] = _percentile(durs, 0.99) if durs else 0
        out_per_node[node_id] = rec
    return {
        "per_node": out_per_node,
        "last_updated_at": utc_isoformat(datetime.now(timezone.utc)),
    }


def _percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    idx = int(round(q * (len(s) - 1)))
    return int(s[max(0, min(idx, len(s) - 1))])


def _safe_json_load(value: str | None) -> Any:
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value
