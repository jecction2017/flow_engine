"""Async orchestrator: scheduling, barriers, hierarchical trackers, and control flow."""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future as ConcurrentFuture
from dataclasses import dataclass
from typing import Any

import starlark as sl

from flow_engine.context import ContextFrame, ContextStack
from flow_engine.exceptions import (
    BreakInterrupt,
    ContinueInterrupt,
    FlowEngineError,
    JumpTarget,
    TerminateInterrupt,
)
from flow_engine.models import (
    ExecutionStrategy,
    FlowDefinition,
    FlowMember,
    FlowState,
    LoopHooks,
    LoopNode,
    NodeState,
    OnErrorAction,
    StrategyMode,
    SubflowNode,
    TaskNode,
)
from flow_engine.data_dict import tree_copy
from flow_engine.resources import GlobalConcurrencyGate, StrategyExecutors, asyncio_main_cancel, install_signal_handlers
from flow_engine.starlark_glue import (
    apply_outputs,
    eval_condition,
    eval_iterable_expr,
    process_starlark_task,
    run_hook_script,
    run_task_script,
)
from flow_engine.tracker import TaskTracker

logger = logging.getLogger(__name__)


def _strategy_mode(st: ExecutionStrategy) -> StrategyMode:
    m = st.mode
    if isinstance(m, StrategyMode):
        return m
    return StrategyMode(str(m).lower())


def _serialize_inputs(ctx: ContextStack, boundary_inputs: dict[str, str]) -> dict[str, Any]:
    return {var: ctx.get_path(path) for path, var in boundary_inputs.items()}


@dataclass
class FlowRunResult:
    state: FlowState
    context: ContextStack
    message: str | None = None


class FlowRuntime:
    """Runs a compiled `FlowDefinition`."""

    def __init__(self, flow: FlowDefinition) -> None:
        self.flow = flow
        self.ctx = ContextStack()
        if flow.initial_context:
            self.ctx.global_ns.update(flow.initial_context)
        if "dictionary" not in self.ctx.global_ns:
            self.ctx.global_ns["dictionary"] = tree_copy()
        self.flow_state: FlowState = FlowState.PENDING
        self.node_state: dict[str, NodeState] = {}
        self._root_tracker = TaskTracker()
        self._gate = GlobalConcurrencyGate(limit=256)
        self.executors = StrategyExecutors(flow.strategies, self._gate)
        self._ctx_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending_async_err: list[BaseException] = []

    def _nid(self, m: FlowMember) -> str:
        return m.id or m.name

    def _mark(self, nid: str, st: NodeState) -> None:
        self.node_state[nid] = st

    def _apply_outputs_safe(self, ctx: ContextStack, result: dict[str, Any], outputs: dict[str, str]) -> None:
        with self._ctx_lock:
            apply_outputs(result, outputs, ctx)

    async def run(self) -> FlowRunResult:
        install_signal_handlers()
        self._loop = asyncio.get_running_loop()
        asyncio_main_cancel(self._loop)
        self.flow_state = FlowState.RUNNING
        if self.flow.hooks and self.flow.hooks.on_start:
            run_hook_script(self.flow.hooks.on_start, self.ctx)
        try:
            await self._run_members(self.flow.nodes, self.ctx, self._root_tracker)
            await self._root_tracker.wait_all()
            self._flush_async_exceptions()
            self.flow_state = FlowState.COMPLETED
            if self.flow.hooks and self.flow.hooks.on_complete:
                run_hook_script(self.flow.hooks.on_complete, self.ctx)
            return FlowRunResult(self.flow_state, self.ctx, None)
        except TerminateInterrupt:
            self.flow_state = FlowState.TERMINATED
            return FlowRunResult(self.flow_state, self.ctx, "terminated")
        except JumpTarget:
            raise
        except FlowEngineError as e:
            self.flow_state = FlowState.FAILED
            if self.flow.hooks and self.flow.hooks.on_failure:
                run_hook_script(self.flow.hooks.on_failure, self.ctx, {"error": str(e)})
            return FlowRunResult(self.flow_state, self.ctx, str(e))
        except Exception as e:  # noqa: BLE001
            logger.exception("Flow failed")
            self.flow_state = FlowState.FAILED
            if self.flow.hooks and self.flow.hooks.on_failure:
                run_hook_script(self.flow.hooks.on_failure, self.ctx, {"error": str(e)})
            return FlowRunResult(self.flow_state, self.ctx, str(e))
        finally:
            self.executors.shutdown()

    def _flush_async_exceptions(self) -> None:
        if self._pending_async_err:
            err = self._pending_async_err.pop(0)
            raise err

    def _schedule_error(self, exc: BaseException) -> None:
        self._pending_async_err.append(exc)

    async def _run_members(self, members: list[FlowMember], ctx: ContextStack, tracker: TaskTracker) -> None:
        i = 0
        while i < len(members):
            m = members[i]
            try:
                await self._dispatch_member(m, ctx, tracker)
            except JumpTarget as j:
                idx = self._index_by_id(members, j.target)
                if idx is not None:
                    i = idx
                    continue
                raise
            i += 1

    def _index_by_id(self, members: list[FlowMember], target: str) -> int | None:
        for idx, mm in enumerate(members):
            if self._nid(mm) == target:
                return idx
        return None

    async def _dispatch_member(self, m: FlowMember, ctx: ContextStack, tracker: TaskTracker) -> None:
        nid = self._nid(m)
        if m.wait_before:
            await tracker.wait_all()

        if not eval_condition(m.condition, ctx):
            self._mark(nid, NodeState.SKIPPED)
            return

        st = self.flow.strategies[m.strategy_ref]
        mode = _strategy_mode(st)

        self._mark(nid, NodeState.STAGING)

        if isinstance(m, TaskNode):
            if mode == StrategyMode.SYNC:
                self._mark(nid, NodeState.RUNNING)
                await self._execute_task_node(m, ctx, tracker, await_result=True)
            else:
                self._mark(nid, NodeState.DISPATCHED)
                await self._execute_task_node(m, ctx, tracker, await_result=False)
        elif isinstance(m, LoopNode):
            await self._execute_loop(m, ctx, tracker)
        elif isinstance(m, SubflowNode):
            await self._execute_subflow(m, ctx, tracker)
        else:
            raise FlowEngineError(f"Unknown member type: {type(m)}")

    async def _with_timeout(
        self,
        aw: Any,
        timeout: float | None,
        nid: str,
    ) -> Any:
        if timeout is None:
            return await aw
        return await asyncio.wait_for(aw, timeout=timeout)

    async def _run_task_once_blocking(
        self,
        node: TaskNode,
        ctx: ContextStack,
        st: ExecutionStrategy,
    ) -> dict[str, Any]:
        """Awaited execution path (Sync / degraded pool), honors timeout and hooks."""
        nid = self._nid(node)
        if node.hooks and getattr(node.hooks, "pre_exec", None):
            run_hook_script(node.hooks.pre_exec, ctx)
        mode_local = _strategy_mode(st)
        if mode_local in (StrategyMode.THREAD, StrategyMode.PROCESS):
            if not self._gate.try_acquire():
                mode_local = StrategyMode.SYNC
        timeout = st.timeout
        try:
            if mode_local == StrategyMode.SYNC:
                return await self._with_timeout(
                    asyncio.to_thread(run_task_script, node.script, ctx, node.boundary.inputs),
                    timeout,
                    nid,
                )
            if mode_local == StrategyMode.ASYNC:
                return await self._with_timeout(
                    asyncio.to_thread(run_task_script, node.script, ctx, node.boundary.inputs),
                    timeout,
                    nid,
                )
            if mode_local == StrategyMode.THREAD:
                loop = asyncio.get_running_loop()
                pool = self.executors.thread_pool(node.strategy_ref)

                def sync() -> dict[str, Any]:
                    return run_task_script(node.script, ctx, node.boundary.inputs)

                fut: ConcurrentFuture[dict[str, Any]] = pool.submit(sync)
                wrapped = asyncio.wrap_future(fut, loop=loop)
                return await self._with_timeout(wrapped, timeout, nid)
            if mode_local == StrategyMode.PROCESS:
                loop = asyncio.get_running_loop()
                pool = self.executors.process_pool(node.strategy_ref)
                payload = {
                    "script": node.script,
                    "inputs": node.boundary.inputs,
                    "flat_inputs": _serialize_inputs(ctx, node.boundary.inputs),
                }
                fut2 = pool.submit(process_starlark_task, payload)
                wrapped2 = asyncio.wrap_future(fut2, loop=loop)
                res = await self._with_timeout(wrapped2, timeout, nid)
                return res["result"]
        finally:
            if mode_local in (StrategyMode.THREAD, StrategyMode.PROCESS):
                self._gate.release()

        raise AssertionError("unreachable")

    async def _execute_task_node(
        self,
        node: TaskNode,
        ctx: ContextStack,
        tracker: TaskTracker,
        *,
        await_result: bool,
    ) -> None:
        nid = self._nid(node)
        st = self.flow.strategies[node.strategy_ref]
        retries = st.retry_count

        if not await_result:
            await self._spawn_background(node, ctx, tracker, st)
            return

        last_exc: BaseException | None = None
        for _ in range(retries + 1):
            try:
                result = await self._run_task_once_blocking(node, ctx, st)
                if node.hooks and getattr(node.hooks, "post_exec", None):
                    run_hook_script(node.hooks.post_exec, ctx, {"result": result})
                self._apply_outputs_safe(ctx, result, node.boundary.outputs)
                self._mark(nid, NodeState.SUCCESS)
                return
            except asyncio.TimeoutError as e:
                last_exc = e
                if self._handle_on_error(node, e):
                    continue
                self._mark(nid, NodeState.FAILED)
                raise FlowEngineError(f"Timeout in node {nid}") from e
            except JumpTarget:
                raise
            except (ContinueInterrupt, BreakInterrupt):
                raise
            except sl.StarlarkError as e:
                last_exc = e
                if self._handle_on_error(node, e):
                    continue
                self._mark(nid, NodeState.FAILED)
                raise FlowEngineError(f"Starlark error in {nid}: {e}") from e
            except Exception as e:  # noqa: BLE001
                last_exc = e
                if self._handle_on_error(node, e):
                    continue
                self._mark(nid, NodeState.FAILED)
                raise FlowEngineError(f"Error in {nid}: {e}") from e

        raise FlowEngineError(f"Node {nid} failed after retries: {last_exc!r}")

    def _handle_on_error(self, node: TaskNode, exc: BaseException) -> bool:
        """Return True if the engine should retry."""
        cfg = node.on_error
        if not cfg:
            return False
        act = cfg.action
        if isinstance(act, str):
            try:
                act = OnErrorAction(act)
            except ValueError:
                return False
        if act == OnErrorAction.RETRY:
            return True
        if act == OnErrorAction.IGNORE:
            return False
        if act == OnErrorAction.JUMP and cfg.target:
            raise JumpTarget(cfg.target)
        if act == OnErrorAction.CUSTOM and cfg.script:
            run_hook_script(cfg.script, self.ctx, {"error": str(exc)})
            return False
        return False

    async def _spawn_background(
        self,
        node: TaskNode,
        ctx: ContextStack,
        tracker: TaskTracker,
        st: ExecutionStrategy,
    ) -> None:
        """Fire-and-forget for non-sync strategies; completion applies outputs under lock."""
        nid = self._nid(node)
        mode = _strategy_mode(st)
        loop = asyncio.get_running_loop()
        timeout = st.timeout

        def finish_success(result: dict[str, Any]) -> None:
            try:
                if node.hooks and getattr(node.hooks, "post_exec", None):
                    run_hook_script(node.hooks.post_exec, ctx, {"result": result})
                self._apply_outputs_safe(ctx, result, node.boundary.outputs)
                self._mark(nid, NodeState.SUCCESS)
            except BaseException as e:  # noqa: BLE001
                self._schedule_error(e)

        if mode == StrategyMode.ASYNC:

            async def coro() -> None:
                if node.hooks and getattr(node.hooks, "pre_exec", None):
                    run_hook_script(node.hooks.pre_exec, ctx)
                res = await asyncio.to_thread(run_task_script, node.script, ctx, node.boundary.inputs)
                finish_success(res)

            tracker.create_task(loop, coro())
            return

        if mode == StrategyMode.THREAD:
            pool = self.executors.thread_pool(node.strategy_ref)

            def sync() -> dict[str, Any]:
                if node.hooks and getattr(node.hooks, "pre_exec", None):
                    run_hook_script(node.hooks.pre_exec, ctx)
                return run_task_script(node.script, ctx, node.boundary.inputs)

            async def thread_coro() -> None:
                fut = pool.submit(sync)
                wrapped = asyncio.wrap_future(fut, loop=loop)
                res = await self._with_timeout(wrapped, timeout, nid)
                finish_success(res)

            tracker.create_task(loop, thread_coro())
            return

        if mode == StrategyMode.PROCESS:
            pool = self.executors.process_pool(node.strategy_ref)
            payload = {
                "script": node.script,
                "inputs": node.boundary.inputs,
                "flat_inputs": _serialize_inputs(ctx, node.boundary.inputs),
            }

            async def process_coro() -> None:
                futp = pool.submit(process_starlark_task, payload)
                wrappedp = asyncio.wrap_future(futp, loop=loop)
                raw = await self._with_timeout(wrappedp, timeout, nid)
                finish_success(raw["result"])

            tracker.create_task(loop, process_coro())
            return

        raise AssertionError("background mode expected non-sync")

    async def _execute_loop(self, node: LoopNode, ctx: ContextStack, tracker: TaskTracker) -> None:
        nid = self._nid(node)
        await tracker.wait_all()
        self._mark(nid, NodeState.RUNNING)
        items = eval_iterable_expr(node.iterable, ctx)
        hooks = node.hooks if isinstance(node.hooks, LoopHooks) else None
        for it in items:
            iter_tracker = TaskTracker(parent=tracker)
            ctx.push(ContextFrame(node_id=nid, alias=node.alias, loop_item=it, loop_alias=node.alias))
            if hooks and hooks.on_iteration_start:
                run_hook_script(hooks.on_iteration_start, ctx, {"item": it})
            try:
                try:
                    await self._run_members(node.children, ctx, iter_tracker)
                except ContinueInterrupt:
                    continue
                except BreakInterrupt:
                    break
            finally:
                await iter_tracker.wait_all()
                if hooks and hooks.on_iteration_end:
                    run_hook_script(hooks.on_iteration_end, ctx, {"item": it})
                ctx.pop()
        await tracker.wait_all()
        self._mark(nid, NodeState.SUCCESS)

    async def _execute_subflow(self, node: SubflowNode, ctx: ContextStack, tracker: TaskTracker) -> None:
        nid = self._nid(node)
        await tracker.wait_all()
        self._mark(nid, NodeState.RUNNING)
        ctx.push(ContextFrame(node_id=nid, alias=node.alias))
        try:
            await self._run_members(node.children, ctx, tracker)
        finally:
            await tracker.wait_all()
            ctx.pop()
        self._mark(nid, NodeState.SUCCESS)
