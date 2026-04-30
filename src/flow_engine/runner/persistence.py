"""Persist FlowRunResult into ``fe_flow_run``.

Resident vs once/cron/test 写入策略不同（设计文档 §7.4）：
* once/cron/test：``node_runs`` 写入完整 ``list[NodeRunInfo.to_dict()]`` JSON
* resident       ：``node_stats`` 写入聚合统计；不写 node_runs；
                    ``iteration_count`` 由 worker 后台 Task 周期更新

所有函数均同步（SQLAlchemy 是同步的）；async 调用方需用
``asyncio.to_thread`` 包装。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from statistics import mean
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from flow_engine.db.models import FeFlowRun
from flow_engine.db.session import db_session

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
    payload: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc),
        "flow_logs": flow_logs_json,
    }
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


def list_flow_runs(
    *,
    deployment_id: int | None = None,
    test_batch_id: int | None = None,
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
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "runs": [
                {
                    "id": r.id,
                    "deployment_id": r.deployment_id,
                    "test_batch_id": r.test_batch_id,
                    "flow_code": r.flow_code,
                    "ver_no": r.ver_no,
                    "mode": r.mode,
                    "status": r.status,
                    "worker_id": r.worker_id,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                    "iteration_count": r.iteration_count,
                    "error": r.error,
                }
                for r in page
            ],
        }


def get_flow_run_detail(run_id: int) -> dict[str, Any] | None:
    with db_session() as s:
        row = s.get(FeFlowRun, run_id)
        if row is None or row.deleted_at is not None:
            return None
        node_runs = _safe_json_load(row.node_runs)
        node_stats = _safe_json_load(row.node_stats)
        flow_logs = _safe_json_load(row.flow_logs)
        return {
            "id": row.id,
            "deployment_id": row.deployment_id,
            "test_batch_id": row.test_batch_id,
            "worker_id": row.worker_id,
            "flow_code": row.flow_code,
            "ver_no": row.ver_no,
            "mode": row.mode,
            "trigger_context": row.trigger_context,
            "status": row.status,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "iteration_count": row.iteration_count,
            "node_runs": node_runs,
            "node_stats": node_stats,
            "flow_logs": flow_logs,
            "error": row.error,
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
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
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
