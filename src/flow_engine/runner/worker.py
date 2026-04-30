"""Worker process: register, heartbeat, run assigned deployments.

设计文档 §8.3。Worker 是一个独立 asyncio 进程：
* 启动：注册 ``FeWorker`` + 启动心跳与轮询两个后台 Task；
* 运行：每个 ``FeWorkerAssignment`` 关联一个 asyncio.Task，按 schedule_type
  执行 once / cron / resident 流程；
* 停止：取消所有 Task、回写 ``FeWorker.status='dead'``。

DB 操作均同步（SQLAlchemy）；async 调用方使用 ``asyncio.to_thread``。
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import socket
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from flow_engine.db.models import (
    FeFlowDeployment,
    FeFlowVersion,
    FeWorker,
    FeWorkerAssignment,
)
from flow_engine.db.session import db_session
from flow_engine.engine.exceptions import FlowEngineError
from flow_engine.engine.loader import load_flow_from_dict
from flow_engine.engine.models import FlowState
from flow_engine.engine.orchestrator import FlowRuntime
from flow_engine.runner import persistence
from flow_engine.runner.exceptions import RunnerConfigError
from flow_engine.runner.models import CapabilityRule, RunMode, RunOptions
from flow_engine.stores import data_dict
from flow_engine.stores.profile_store import DEFAULT_PROFILE_ID, profile_scope

logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:  # pragma: no cover - optional dependency guard
        return
    load_dotenv()


_load_dotenv()

# Tunables (override via env where useful for tests / staging).
HEARTBEAT_INTERVAL_S = float(os.environ.get("FLOW_WORKER_HEARTBEAT_S", "10"))
ASSIGNMENT_POLL_INTERVAL_S = float(os.environ.get("FLOW_WORKER_POLL_S", "2"))
DEAD_THRESHOLD_S = float(os.environ.get("FLOW_WORKER_DEAD_THRESHOLD_S", "30"))
RESIDENT_STATS_INTERVAL_S = float(os.environ.get("FLOW_WORKER_RESIDENT_STATS_S", "60"))


# ---------------------------------------------------------------------------
# Sync helpers (call via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _register_worker(worker_id: str, capabilities: dict[str, Any]) -> int:
    now = datetime.now(timezone.utc)
    host = socket.gethostname()
    pid = os.getpid()
    with db_session() as s:
        existing = (
            s.execute(select(FeWorker).where(FeWorker.worker_id == worker_id))
            .scalar_one_or_none()
        )
        if existing is None:
            row = FeWorker(
                worker_id=worker_id,
                host=host,
                pid=pid,
                status="active",
                last_heartbeat=now,
                capabilities=capabilities,
            )
            s.add(row)
            s.flush()
            return int(row.id)
        existing.host = host
        existing.pid = pid
        existing.status = "active"
        existing.last_heartbeat = now
        existing.capabilities = capabilities
        existing.deleted_at = None
        return int(existing.id)


def _heartbeat(worker_id: str) -> None:
    with db_session() as s:
        row = (
            s.execute(select(FeWorker).where(FeWorker.worker_id == worker_id))
            .scalar_one_or_none()
        )
        if row is None:
            return
        row.last_heartbeat = datetime.now(timezone.utc)
        if row.status == "dead":
            row.status = "active"


def _mark_worker_dead(worker_id: str) -> None:
    with db_session() as s:
        row = (
            s.execute(select(FeWorker).where(FeWorker.worker_id == worker_id))
            .scalar_one_or_none()
        )
        if row:
            row.status = "dead"


def _list_assignments(worker_id: str) -> list[dict[str, Any]]:
    with db_session() as s:
        stmt = (
            select(FeWorkerAssignment)
            .where(FeWorkerAssignment.worker_id == worker_id)
            .where(FeWorkerAssignment.deleted_at.is_(None))
        )
        return [
            {
                "id": r.id,
                "deployment_id": r.deployment_id,
                "role": r.role,
                "lease_expires_at": r.lease_expires_at,
            }
            for r in s.execute(stmt).scalars().all()
        ]


def _read_deployment(deployment_id: int) -> dict[str, Any] | None:
    with db_session() as s:
        row = s.get(FeFlowDeployment, deployment_id)
        if row is None or row.deleted_at is not None:
            return None
        return {
            "id": row.id,
            "flow_code": row.flow_code,
            "ver_no": row.ver_no,
            "mode": row.mode,
            "schedule_type": row.schedule_type,
            "schedule_config": row.schedule_config,
            "worker_policy": row.worker_policy,
            "capability_policy": row.capability_policy,
            "status": row.status,
            "env_profile_code": row.env_profile_code,
            "parent_deployment_id": row.parent_deployment_id,
        }


def _read_flow_body(flow_code: str, ver_no: int) -> dict[str, Any]:
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


def _set_deployment_status(deployment_id: int, status: str) -> None:
    with db_session() as s:
        row = s.get(FeFlowDeployment, deployment_id)
        if row is None:
            return
        row.status = status


# ---------------------------------------------------------------------------
# Worker class
# ---------------------------------------------------------------------------


class Worker:
    """Single Worker process. Use ``await worker.start()`` to begin running."""

    def __init__(
        self,
        *,
        worker_id: str | None = None,
        max_concurrent_flows: int = 8,
    ) -> None:
        self.worker_id = worker_id or str(uuid.uuid4())
        self.capabilities = {"max_concurrent_flows": int(max_concurrent_flows)}
        self._assignments: dict[int, asyncio.Task[Any]] = {}
        self._stop_evt = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []
        self._started = False

    # ---------------- lifecycle ----------------

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await asyncio.to_thread(_register_worker, self.worker_id, self.capabilities)
        logger.info("worker started worker_id=%s", self.worker_id)
        self._tasks.append(asyncio.create_task(self._heartbeat_loop()))
        self._tasks.append(asyncio.create_task(self._poll_assignments()))

    async def stop(self) -> None:
        self._stop_evt.set()
        # Cancel running deployments first; pollers next
        for tid, t in list(self._assignments.items()):
            t.cancel()
        for t in list(self._assignments.values()):
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await asyncio.to_thread(_mark_worker_dead, self.worker_id)
        logger.info("worker stopped worker_id=%s", self.worker_id)

    async def run_forever(self) -> None:
        await self.start()
        await self._stop_evt.wait()
        await self.stop()

    # ---------------- background loops ----------------

    async def _heartbeat_loop(self) -> None:
        try:
            while not self._stop_evt.is_set():
                try:
                    await asyncio.to_thread(_heartbeat, self.worker_id)
                except Exception:  # noqa: BLE001
                    logger.exception("heartbeat failed")
                try:
                    await asyncio.wait_for(
                        self._stop_evt.wait(), timeout=HEARTBEAT_INTERVAL_S
                    )
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    async def _poll_assignments(self) -> None:
        try:
            while not self._stop_evt.is_set():
                try:
                    rows = await asyncio.to_thread(
                        _list_assignments, self.worker_id
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("assignment poll failed")
                    rows = []

                current = {r["deployment_id"]: r for r in rows}
                # New assignments
                for dep_id, info in current.items():
                    if dep_id not in self._assignments:
                        self._start_assignment(dep_id, info)
                # Removed assignments → cancel
                for dep_id in list(self._assignments.keys()):
                    if dep_id not in current:
                        t = self._assignments.pop(dep_id)
                        t.cancel()

                try:
                    await asyncio.wait_for(
                        self._stop_evt.wait(), timeout=ASSIGNMENT_POLL_INTERVAL_S
                    )
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    # ---------------- deployment dispatch ----------------

    def _start_assignment(self, deployment_id: int, info: dict[str, Any]) -> None:
        async def runner() -> None:
            try:
                await self._run_assignment(deployment_id)
            except asyncio.CancelledError:
                logger.info("assignment cancelled deployment_id=%s", deployment_id)
                raise
            except Exception:  # noqa: BLE001
                logger.exception(
                    "assignment crashed deployment_id=%s", deployment_id
                )
            finally:
                self._assignments.pop(deployment_id, None)

        self._assignments[deployment_id] = asyncio.create_task(runner())

    async def _run_assignment(self, deployment_id: int) -> None:
        deployment = await asyncio.to_thread(_read_deployment, deployment_id)
        if deployment is None:
            logger.warning("deployment %s vanished before run", deployment_id)
            return
        st = deployment["schedule_type"]
        if st == "resident":
            await self._run_resident(deployment)
        elif st in ("once", "cron"):
            # cron 部署本身是“模板”：实际由 Scheduler 克隆出 once 子部署交给 Coordinator；
            # 一个 cron 模板自身落到 Worker 时按 once 语义跑一次（兼容直接触发场景）。
            await self._run_once_flow(deployment)
        else:
            logger.error("unknown schedule_type=%s for deployment %s", st, deployment_id)
            await asyncio.to_thread(_set_deployment_status, deployment_id, "failed")

    # ---------------- run modes ----------------

    async def _run_once_flow(self, deployment: dict[str, Any]) -> None:
        deployment_id = int(deployment["id"])
        run_id: int | None = None
        try:
            run_id, runtime, profile_id = await self._prepare_runtime(
                deployment, trigger_context=None
            )
            with profile_scope(profile_id):
                result = await runtime.run()
            await asyncio.to_thread(
                persistence.complete_flow_run, run_id, result, is_resident=False
            )
            final = "stopped" if result.state == FlowState.COMPLETED else "failed"
            await asyncio.to_thread(_set_deployment_status, deployment_id, final)
        except asyncio.CancelledError:
            if run_id is not None:
                await asyncio.to_thread(persistence.fail_flow_run, run_id, "cancelled")
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("once/cron run failed deployment_id=%s", deployment_id)
            if run_id is not None:
                await asyncio.to_thread(persistence.fail_flow_run, run_id, str(e))
            await asyncio.to_thread(_set_deployment_status, deployment_id, "failed")

    async def _run_resident(self, deployment: dict[str, Any]) -> None:
        deployment_id = int(deployment["id"])
        wp = deployment["worker_policy"] or {}
        max_restarts = int(wp.get("max_restarts", 5))
        backoff_base = int(wp.get("restart_backoff_s", 30))
        restart_count = 0

        while not self._stop_evt.is_set():
            run_id: int | None = None
            stats_task: asyncio.Task[Any] | None = None
            try:
                run_id, runtime, profile_id = await self._prepare_runtime(
                    deployment, trigger_context=None
                )
                stats_task = asyncio.create_task(
                    self._resident_stats_loop(run_id, runtime)
                )
                with profile_scope(profile_id):
                    result = await runtime.run()
                # Stop the stats loop and persist a final aggregate
                stats_task.cancel()
                try:
                    await stats_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
                await asyncio.to_thread(
                    persistence.complete_flow_run, run_id, result, is_resident=True
                )
                # resident 流程正常退出（用户主动 terminate）：标记 stopped 并退出循环。
                await asyncio.to_thread(_set_deployment_status, deployment_id, "stopped")
                return
            except asyncio.CancelledError:
                if stats_task and not stats_task.done():
                    stats_task.cancel()
                if run_id is not None:
                    await asyncio.to_thread(persistence.fail_flow_run, run_id, "cancelled")
                raise
            except Exception as e:  # noqa: BLE001
                logger.exception("resident run failed deployment_id=%s", deployment_id)
                if stats_task and not stats_task.done():
                    stats_task.cancel()
                    try:
                        await stats_task
                    except (asyncio.CancelledError, Exception):  # noqa: BLE001
                        pass
                if run_id is not None:
                    await asyncio.to_thread(persistence.fail_flow_run, run_id, str(e))
                restart_count += 1
                if restart_count > max_restarts:
                    await asyncio.to_thread(
                        _set_deployment_status, deployment_id, "failed"
                    )
                    return
                delay = backoff_base * (2 ** (restart_count - 1))
                logger.warning(
                    "resident restart in %.1fs (attempt %d/%d) deployment_id=%s",
                    delay,
                    restart_count,
                    max_restarts,
                    deployment_id,
                )
                try:
                    await asyncio.wait_for(self._stop_evt.wait(), timeout=delay)
                    return  # stop requested during backoff
                except asyncio.TimeoutError:
                    continue

    async def _resident_stats_loop(
        self, run_id: int, runtime: FlowRuntime
    ) -> None:
        """Periodically flush iteration_count + node_stats while runtime is alive.

        Reads from the live ``runtime._node_runs`` snapshot — non-invasive, no
        engine hook changes needed.
        """
        try:
            while True:
                await asyncio.sleep(RESIDENT_STATS_INTERVAL_S)
                try:
                    runs = list(runtime._node_runs.values())  # noqa: SLF001
                    stats = persistence._aggregate_node_stats(runs)  # noqa: SLF001
                    iter_count = sum(r.execution_count for r in runs)
                    await asyncio.to_thread(
                        persistence.update_node_stats, run_id, stats
                    )
                    await asyncio.to_thread(
                        persistence.update_iteration_count, run_id, iter_count
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("resident stats flush failed")
        except asyncio.CancelledError:
            return

    # ---------------- runtime construction ----------------

    async def _prepare_runtime(
        self,
        deployment: dict[str, Any],
        *,
        trigger_context: dict[str, Any] | None,
    ) -> tuple[int, FlowRuntime, str]:
        flow_code = deployment["flow_code"]
        ver_no = int(deployment["ver_no"])
        flow_data = await asyncio.to_thread(_read_flow_body, flow_code, ver_no)
        flow = load_flow_from_dict(copy.deepcopy(flow_data))

        try:
            mode = RunMode(deployment["mode"])
        except ValueError as e:
            raise RunnerConfigError(f"invalid run mode: {deployment['mode']!r}") from e

        rules = [
            CapabilityRule.model_validate(r)
            for r in (deployment.get("capability_policy") or [])
        ]
        run_opts = RunOptions(
            mode=mode,
            mock_overrides={},
            deployment_capability_policy=rules,
        )

        profile_id = deployment.get("env_profile_code") or DEFAULT_PROFILE_ID
        resolved = await asyncio.to_thread(data_dict.resolve, profile_id)
        runtime = FlowRuntime(
            flow,
            dictionary=resolved["resolved_dictionary"],
            run_opts=run_opts,
        )
        if trigger_context:
            runtime.ctx.global_ns.update(trigger_context)

        run_id = await asyncio.to_thread(
            persistence.create_flow_run,
            deployment_id=int(deployment["id"]),
            test_batch_id=None,
            worker_id=self.worker_id,
            flow_code=flow_code,
            ver_no=ver_no,
            mode=mode,
            trigger_context=trigger_context,
        )
        return run_id, runtime, profile_id


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------


async def main_async(*, max_concurrent_flows: int = 8) -> None:
    worker = Worker(max_concurrent_flows=max_concurrent_flows)
    loop = asyncio.get_running_loop()
    stop_evt = worker._stop_evt  # noqa: SLF001

    def _on_signal() -> None:
        if not stop_evt.is_set():
            logger.info("signal received, stopping worker")
            stop_evt.set()

    # SIGINT / SIGTERM — best-effort; Windows lacks SIGTERM on non-main threads.
    try:
        import signal

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _on_signal)
            except (NotImplementedError, RuntimeError):
                signal.signal(sig, lambda *_: _on_signal())
    except Exception:  # noqa: BLE001
        logger.debug("signal handlers not installed", exc_info=True)

    await worker.run_forever()


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="flow-worker", description="Flow Engine Worker")
    sub = p.add_subparsers(dest="cmd", required=True)
    p_start = sub.add_parser("start", help="start a worker process")
    p_start.add_argument(
        "--max-concurrent-flows",
        type=int,
        default=int(os.environ.get("FLOW_WORKER_MAX_CONCURRENT", "8")),
    )
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.cmd == "start":
        asyncio.run(main_async(max_concurrent_flows=args.max_concurrent_flows))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
