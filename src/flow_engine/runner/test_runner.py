"""Lookup-namespace-driven test runner.

每行 lookup namespace 数据 → 一次 ``RunMode.DEBUG`` 流程运行 → 一条
``fe_test_run``；可选断言规则写入 ``FeTestRun.evaluation``，详细执行
轨迹写入 ``fe_run_span``（test_run_id=run_id）。

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

from flow_engine.db.models import FeFlowTestBatch, FeFlowTestBatchPlan, FeFlowTestPlan, FeFlowVersion
from flow_engine.db.session import db_session
from flow_engine.engine.exceptions import FlowEngineError
from flow_engine.engine.loader import load_flow_from_dict
from flow_engine.engine.orchestrator import FlowRuntime
from flow_engine.lookup.lookup_service import lookup_query_page
from flow_engine.runner import assertions as assertions_mod
from flow_engine.runner import test_persistence
from flow_engine.runner.models import CapabilityRule, MockConfig, RunMode, RunOptions
from flow_engine.stores import data_dict
from flow_engine.stores.profile_store import profile_scope, store as profile_store
from flow_engine.time_utils import utc_isoformat

logger = logging.getLogger(__name__)


def apply_lookup_row_to_context(
    row: dict[str, Any],
    mapping: dict[str, Any] | None,
) -> dict[str, Any]:
    """Map a lookup row to a context fragment that will be merged into global_ns."""
    if not mapping:
        return dict(row)
    mode = str(mapping.get("mode") or "spread")
    if mode == "spread":
        return dict(row)
    if mode == "wrap":
        key = str(mapping.get("wrap_key") or "input").strip() or "input"
        wrap_as_list = bool(mapping.get("wrap_as_list"))
        return {key: [dict(row)] if wrap_as_list else dict(row)}
    if mode == "rules":
        rules = mapping.get("rules") or []
        if not isinstance(rules, list):
            return dict(row)
        out: dict[str, Any] = {}

        def set_dotted(root: dict[str, Any], path: str, value: Any) -> None:
            parts = [p.strip() for p in path.split(".") if p.strip()]
            if not parts:
                return
            cur: dict[str, Any] = root
            for p in parts[:-1]:
                nxt = cur.get(p)
                if nxt is None or not isinstance(nxt, dict):
                    fresh: dict[str, Any] = {}
                    cur[p] = fresh
                    cur = fresh
                else:
                    cur = nxt
            cur[parts[-1]] = value

        for r in rules:
            if not isinstance(r, dict):
                continue
            src = str(r.get("source") or "").strip()
            tgt = str(r.get("target") or "").strip()
            if not src or not tgt:
                continue
            if src not in row:
                continue
            set_dotted(out, tgt, row.get(src))
        return out
    return dict(row)


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
        res = s.execute(
            update(FeFlowTestBatch)
            .where(FeFlowTestBatch.id == batch_id)
            .values({col: col + 1})
        )
        res.close()


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
    assertions: list[dict[str, Any]] | None = None,
    capability_policy: list[dict[str, Any]] | None = None,
) -> int:
    """触发一次测试批次，立即创建批次行并并发运行；返回 ``batch_id``。

    每行 lookup namespace 数据被注入到 ``runtime.ctx.global_ns``（覆盖式合并）。
    每次运行写入一条 ``fe_flow_run``；批次结束更新 ``fe_flow_test_batch``。

    ``capability_policy`` 透传到 ``RunOptions.deployment_capability_policy``，
    优先级高于 RunMode.DEBUG 系统默认；空 / None 时仅生效系统默认（抑制
    ``integration`` / ``db_write`` / ``mq_publish`` 类副作用）。
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
    dictionary = await asyncio.to_thread(data_dict.tree_copy, profile_code)

    sem = asyncio.Semaphore(max(1, int(concurrency)))
    parsed_policy = [CapabilityRule.model_validate(r) for r in (capability_policy or [])]
    profile_policy = await asyncio.to_thread(
        lambda: profile_store().get_system_capability_policy(profile_code, run_mode=RunMode.DEBUG.value)
    )
    parsed_profile_policy = [CapabilityRule.model_validate(r) for r in profile_policy]

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
                assertions=assertions,
                capability_policy=parsed_policy,
                profile_system_policy=parsed_profile_policy,
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
    context_mapping: dict[str, Any] | None = None,
    assertions: list[dict[str, Any]] | None = None,
    capability_policy: list[CapabilityRule] | None = None,
    profile_system_policy: list[CapabilityRule] | None = None,
) -> bool:
    flow = load_flow_from_dict(copy.deepcopy(flow_data))
    run_opts = RunOptions(
        mode=RunMode.DEBUG,
        mock_overrides=mock_config,
        deployment_capability_policy=list(capability_policy or []),
        profile_system_capability_policy=list(profile_system_policy or []),
    )
    runtime = FlowRuntime(flow, dictionary=dictionary, run_opts=run_opts)
    row_clean = assertions_mod.strip_expect_keys(test_input)
    mapped_ctx = apply_lookup_row_to_context(row_clean, context_mapping)
    runtime.ctx.global_ns.update(mapped_ctx)

    run_id = await asyncio.to_thread(
        test_persistence.create_test_run,
        test_batch_id=batch_id,
        worker_id=None,
        flow_code=flow_code,
        ver_no=ver_no,
        trigger_context={"row": test_input, "mapped": mapped_ctx},
    )

    # Wire an observability backend so the test domain also produces
    # spans in ``fe_run_span`` (keyed by test_run_id). Tests always run
    # at full sampling — they are bounded and the user is intentionally
    # inspecting them.
    from flow_engine.engine.observability import RunRef
    from flow_engine.runner.obs_backend import (
        AsyncBufferedDBBackend,
        ObsRuntimeConfig,
    )

    obs_cfg = ObsRuntimeConfig()  # defaults: 1.0 rate, ERROR-only logs
    backend = AsyncBufferedDBBackend(
        run_ref=RunRef(test_run_id=run_id),
        flow_code=flow_code,
        obs_cfg=obs_cfg,
    )
    runtime.obs = backend
    runtime.flow_code = flow_code
    runtime._obs_run_ref = RunRef(test_run_id=run_id)  # type: ignore[attr-defined]

    success = False
    try:
        await backend.start()
        try:
            with profile_scope(profile_code):
                result = await runtime.run()
        finally:
            try:
                await backend.drain()
            except Exception:  # noqa: BLE001
                logger.exception("obs drain failed for test run_id=%s", run_id)
        gns = dict(getattr(result.context, "global_ns", {}) or {})
        gns.pop("dictionary", None)
        from flow_engine.engine.models import FlowState as _FS

        status = "completed" if result.state == _FS.COMPLETED else ("terminated" if result.state == _FS.TERMINATED else "failed")
        await asyncio.to_thread(
            test_persistence.complete_test_run,
            run_id,
            status=status,
            error=result.message,
        )
        rules = list(assertions or []) + assertions_mod.row_derived_assertion_rules(
            test_input
        )
        ev = assertions_mod.evaluate_assertions(
            flow_state=result.state,
            global_ns=gns,
            rules=rules,
        )
        await asyncio.to_thread(test_persistence.set_test_run_evaluation, run_id, ev)
        success = result.state == _FS.COMPLETED
    except Exception as e:  # noqa: BLE001
        logger.exception("test run failed (run_id=%s)", run_id)
        try:
            await backend.drain()
        except Exception:  # noqa: BLE001
            pass
        await asyncio.to_thread(test_persistence.fail_test_run, run_id, str(e))
        await asyncio.to_thread(
            test_persistence.set_test_run_evaluation,
            run_id,
            {"verdict": "fail", "reason": "exception", "message": str(e), "rules": []},
        )
    finally:
        await asyncio.to_thread(_bump_test_batch_counter, batch_id, success=success)
    return success


def get_test_batch(batch_id: int) -> dict[str, Any] | None:
    with db_session() as s:
        row = s.get(FeFlowTestBatch, batch_id)
        if row is None or row.deleted_at is not None:
            return None
        plan_link = (
            s.execute(
                select(FeFlowTestBatchPlan)
                .where(FeFlowTestBatchPlan.batch_id == batch_id)
                .where(FeFlowTestBatchPlan.deleted_at.is_(None))
            )
            .scalars()
            .one_or_none()
        )
        plan_brief: dict[str, Any] | None = None
        if plan_link is not None:
            plan_row = s.get(FeFlowTestPlan, int(plan_link.plan_id))
            if plan_row is not None and plan_row.deleted_at is None:
                plan_brief = {"id": int(plan_row.id), "name": plan_row.name}
        out: dict[str, Any] = {
            "id": row.id,
            "flow_code": row.flow_code,
            "ver_no": row.ver_no,
            "test_ns_code": row.test_ns_code,
            "profile_code": row.profile_code,
            "status": row.status,
            "total_runs": row.total_runs,
            "completed_runs": row.completed_runs,
            "error_runs": row.error_runs,
            "started_at": utc_isoformat(row.started_at),
            "finished_at": utc_isoformat(row.finished_at),
            "plan": plan_brief,
        }
        try:
            out["summary"] = test_persistence.summarize_batch_runs(int(row.id))
        except Exception:  # noqa: BLE001
            out["summary"] = None
        return out


def attach_plan_to_batch(
    *,
    batch_id: int,
    plan_id: int,
    plan_snapshot: dict[str, Any],
) -> None:
    snap = json.dumps(plan_snapshot, ensure_ascii=False, default=str)
    with db_session() as s:
        # Soft-delete any existing link (shouldn't happen, but keeps it idempotent).
        res = s.execute(
            select(FeFlowTestBatchPlan)
            .where(FeFlowTestBatchPlan.batch_id == batch_id)
            .where(FeFlowTestBatchPlan.deleted_at.is_(None))
        )
        old = res.scalars().first()
        res.close()
        if old is not None:
            old.deleted_at = datetime.now(timezone.utc)
        s.add(
            FeFlowTestBatchPlan(
                batch_id=int(batch_id),
                plan_id=int(plan_id),
                plan_snapshot=snap,
            )
        )
