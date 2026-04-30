"""Lookup-namespace-driven test runner.

每行 lookup namespace 数据 → 一次 ``RunMode.DEBUG`` 流程运行 → 一条
``fe_flow_run``；本模块不做自动断言（用户自行分析输出）。

并发由 ``asyncio.Semaphore`` 控制；DB 访问全部经 ``asyncio.to_thread``。
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from flow_engine.db.models import FeFlowTestBatch, FeFlowVersion
from flow_engine.db.session import db_session
from flow_engine.engine.exceptions import FlowEngineError
from flow_engine.engine.loader import load_flow_from_dict
from flow_engine.engine.orchestrator import FlowRuntime
from flow_engine.lookup.lookup_service import lookup_query_page
from flow_engine.runner import persistence
from flow_engine.runner.models import MockConfig, RunMode, RunOptions
from flow_engine.stores import data_dict
from flow_engine.stores.profile_store import profile_scope, store as profile_store

logger = logging.getLogger(__name__)


def _read_flow_version_body(flow_code: str, ver_no: int) -> dict[str, Any]:
    with db_session() as s:
        stmt = (
            select(FeFlowVersion)
            .where(FeFlowVersion.flow_code == flow_code)
            .where(FeFlowVersion.ver_no == ver_no)
            .where(FeFlowVersion.deleted_at.is_(None))
        )
        row = s.execute(stmt).scalar_one_or_none()
        if row is None:
            raise FlowEngineError(
                f"flow version not found: flow_code={flow_code} ver_no={ver_no}"
            )
        return json.loads(row.body)


def _create_test_batch(
    *,
    flow_code: str,
    ver_no: int,
    test_ns_code: str,
    profile_code: str,
    mock_config: dict[str, MockConfig],
    total_runs: int,
) -> int:
    serialized = {nid: cfg.model_dump() for nid, cfg in mock_config.items()}
    with db_session() as s:
        row = FeFlowTestBatch(
            flow_code=flow_code,
            ver_no=ver_no,
            test_ns_code=test_ns_code,
            profile_code=profile_code,
            mock_config=json.dumps(serialized, ensure_ascii=False, default=str),
            status="running",
            started_at=datetime.now(timezone.utc),
            total_runs=total_runs,
            completed_runs=0,
            error_runs=0,
        )
        s.add(row)
        s.flush()
        return int(row.id)


def _bump_test_batch_counter(batch_id: int, *, success: bool) -> None:
    """Atomic counter increment to avoid lost updates under concurrent runs.

    Several runner Tasks invoke ``asyncio.to_thread(_bump_..., ...)`` concurrently,
    each landing on its own DB connection — a read-modify-write pattern would
    drop updates. ``UPDATE ... SET col = col + 1`` is atomic per-row.
    """
    col = FeFlowTestBatch.completed_runs if success else FeFlowTestBatch.error_runs
    with db_session() as s:
        s.execute(
            update(FeFlowTestBatch)
            .where(FeFlowTestBatch.id == batch_id)
            .values({col: col + 1})
        )


def _finalize_test_batch(batch_id: int, *, status: str) -> None:
    with db_session() as s:
        row = s.get(FeFlowTestBatch, batch_id)
        if row is None:
            return
        row.status = status
        row.finished_at = datetime.now(timezone.utc)


def _read_test_rows(test_ns_code: str, profile_code: str) -> list[dict[str, Any]]:
    """Pull all rows from the test namespace (capped by lookup_query_page server-side)."""
    out: list[dict[str, Any]] = []
    offset = 0
    page_size = 500
    with profile_scope(profile_code):
        while True:
            page = lookup_query_page(
                test_ns_code, {}, offset=offset, limit=page_size
            )
            rows = page.get("rows", [])
            out.extend(rows)
            if not page.get("has_more"):
                break
            offset += page_size
    return out


async def run_test_batch(
    flow_code: str,
    ver_no: int,
    test_ns_code: str,
    profile_code: str,
    mock_config: dict[str, MockConfig],
    *,
    concurrency: int = 4,
) -> int:
    """触发一次测试批次，立即创建批次行并并发运行；返回 ``batch_id``。

    每行 lookup namespace 数据被注入到 ``runtime.ctx.global_ns``（覆盖式合并）。
    每次运行写入一条 ``fe_flow_run``；批次结束更新 ``fe_flow_test_batch``。
    """
    rows = await asyncio.to_thread(_read_test_rows, test_ns_code, profile_code)
    batch_id = await asyncio.to_thread(
        _create_test_batch,
        flow_code=flow_code,
        ver_no=ver_no,
        test_ns_code=test_ns_code,
        profile_code=profile_code,
        mock_config=mock_config,
        total_runs=len(rows),
    )

    if not rows:
        await asyncio.to_thread(_finalize_test_batch, batch_id, status="completed")
        return batch_id

    flow_data = await asyncio.to_thread(_read_flow_version_body, flow_code, ver_no)
    resolved = await asyncio.to_thread(data_dict.resolve, profile_code)
    dictionary = resolved["resolved_dictionary"]

    sem = asyncio.Semaphore(max(1, int(concurrency)))

    async def one(row: dict[str, Any]) -> bool:
        async with sem:
            return await _run_single_test_case(
                batch_id=batch_id,
                flow_code=flow_code,
                ver_no=ver_no,
                profile_code=profile_code,
                flow_data=flow_data,
                dictionary=dictionary,
                mock_config=mock_config,
                test_input=row,
            )

    results = await asyncio.gather(*(one(r) for r in rows), return_exceptions=True)
    final_status = "completed"
    for r in results:
        if isinstance(r, BaseException):
            logger.exception("test case crashed: %r", r)
            final_status = "failed"
            break
    await asyncio.to_thread(_finalize_test_batch, batch_id, status=final_status)
    return batch_id


async def _run_single_test_case(
    *,
    batch_id: int,
    flow_code: str,
    ver_no: int,
    profile_code: str,
    flow_data: dict[str, Any],
    dictionary: dict[str, Any],
    mock_config: dict[str, MockConfig],
    test_input: dict[str, Any],
) -> bool:
    flow = load_flow_from_dict(copy.deepcopy(flow_data))
    run_opts = RunOptions(
        mode=RunMode.DEBUG,
        mock_overrides=mock_config,
        deployment_capability_policy=[],
    )
    runtime = FlowRuntime(flow, dictionary=dictionary, run_opts=run_opts)
    runtime.ctx.global_ns.update(test_input)

    run_id = await asyncio.to_thread(
        persistence.create_flow_run,
        deployment_id=None,
        test_batch_id=batch_id,
        worker_id=None,
        flow_code=flow_code,
        ver_no=ver_no,
        mode=RunMode.DEBUG,
        trigger_context=test_input,
    )

    success = False
    try:
        with profile_scope(profile_code):
            result = await runtime.run()
        await asyncio.to_thread(
            persistence.complete_flow_run, run_id, result, is_resident=False
        )
        from flow_engine.engine.models import FlowState as _FS

        success = result.state == _FS.COMPLETED
    except Exception as e:  # noqa: BLE001
        logger.exception("test run failed (run_id=%s)", run_id)
        await asyncio.to_thread(persistence.fail_flow_run, run_id, str(e))
    finally:
        await asyncio.to_thread(_bump_test_batch_counter, batch_id, success=success)
    return success


def get_test_batch(batch_id: int) -> dict[str, Any] | None:
    with db_session() as s:
        row = s.get(FeFlowTestBatch, batch_id)
        if row is None or row.deleted_at is not None:
            return None
        return {
            "id": row.id,
            "flow_code": row.flow_code,
            "ver_no": row.ver_no,
            "test_ns_code": row.test_ns_code,
            "profile_code": row.profile_code,
            "status": row.status,
            "total_runs": row.total_runs,
            "completed_runs": row.completed_runs,
            "error_runs": row.error_runs,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }
