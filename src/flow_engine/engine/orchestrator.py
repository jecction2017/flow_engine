"""Async orchestrator: scheduling, barriers, hierarchical trackers, and control flow."""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from concurrent.futures import Future as ConcurrentFuture
from contextvars import copy_context
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

import starlark as sl

from flow_engine.engine.context import ContextFrame, ContextStack
from flow_engine.engine.exceptions import (
    BreakInterrupt,
    ContinueInterrupt,
    FlowEngineError,
    JumpTarget,
    TerminateInterrupt,
)
from flow_engine.engine.models import (
    ExecutionStrategy,
    FlowDefinition,
    FlowMember,
    FlowState,
    LoopHooks,
    LoopNode,
    NodeHooks,
    NodeState,
    OnErrorAction,
    StrategyMode,
    SubflowNode,
    TaskNode,
)
from flow_engine.engine.resources import (
    GlobalConcurrencyGate,
    StrategyExecutors,
    asyncio_main_cancel,
    install_signal_handlers,
)
from flow_engine.engine.starlark_glue import (
    apply_outputs,
    eval_condition,
    eval_iterable_expr,
    process_starlark_task,
    run_hook_script,
    run_task_script,
)
from flow_engine.engine.tracker import TaskTracker
from flow_engine.stores.data_dict import dictionary_scope, tree_copy

logger = logging.getLogger(__name__)

_MAX_JUMPS_PER_SCOPE = 1024


def _strategy_mode(st: ExecutionStrategy) -> StrategyMode:
    m = st.mode
    if isinstance(m, StrategyMode):
        return m
    return StrategyMode(str(m).lower())


def _serialize_inputs(ctx: ContextStack, boundary_inputs: dict[str, str]) -> dict[str, Any]:
    return {var: ctx.get_path(path) for path, var in boundary_inputs.items()}


def _node_hook(hooks: Any, name: str) -> str | None:
    """Safely fetch a hook snippet from either NodeHooks / LoopHooks / None."""
    if hooks is None:
        return None
    return getattr(hooks, name, None)


@dataclass
class NodeRunInfo:
    """Per-node execution record captured by the orchestrator.

    Timestamps are relative milliseconds from the moment ``FlowRuntime.run``
    entered :attr:`FlowState.RUNNING` so that consumers can plot a timeline
    without knowing the wall-clock start. ``order`` is the 0-based index in
    which the node was first observed by the scheduler -- this is what drives
    the "execution sequence" column in the UI and is stable across reruns of
    deterministic flows.
    """

    node_id: str
    order: int
    first_seen_ms: int
    started_ms: int | None = None
    finished_ms: int | None = None
    final_state: NodeState = NodeState.INITIALIZED
    parent_id: str | None = None
    iterations: int | None = None
    transitions: list[dict[str, Any]] = field(default_factory=list)
    # Log entries emitted by this node's task script AND its hooks
    # (pre_exec / post_exec / on_iteration_* / on_error-custom). Each entry
    # carries ``source`` to tell them apart; retry attempts get an extra
    # ``attempt`` key (omitted on first run for brevity).
    logs: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> int | None:
        if self.started_ms is None or self.finished_ms is None:
            return None
        return max(0, self.finished_ms - self.started_ms)

    @property
    def execution_count(self) -> int:
        """How many scheduler passes this node went through.

        A pass starts with ``STAGING`` when condition checks passed. A node can
        also start and end in ``SKIPPED`` directly when the condition fails.
        Importantly, a pass that started with ``STAGING`` may still end in
        ``SKIPPED`` (for example a task calling ``flow_continue()``), and that
        must still count as just one pass.
        """
        staged = 0
        direct_skipped = 0
        prev_state: str | None = None
        for tr in self.transitions:
            state = str(tr.get("state"))
            if state == NodeState.STAGING.value:
                staged += 1
            elif state == NodeState.SKIPPED.value:
                if prev_state not in (
                    NodeState.STAGING.value,
                    NodeState.DISPATCHED.value,
                    NodeState.RUNNING.value,
                ):
                    direct_skipped += 1
            prev_state = state
        return max(1, staged + direct_skipped)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "order": self.order,
            "first_seen_ms": self.first_seen_ms,
            "started_ms": self.started_ms,
            "finished_ms": self.finished_ms,
            "duration_ms": self.duration_ms,
            "final_state": self.final_state.value,
            "parent_id": self.parent_id,
            "iterations": self.iterations,
            "execution_count": self.execution_count,
            "transitions": list(self.transitions),
            "logs": list(self.logs),
        }


@dataclass
class FlowRunResult:
    state: FlowState
    context: ContextStack
    message: str | None = None
    node_state: dict[str, NodeState] = field(default_factory=dict)
    node_runs: list[NodeRunInfo] = field(default_factory=list)
    # Flow-level hook logs (on_start / on_complete / on_failure). These
    # don't belong to any single node so we surface them separately.
    flow_logs: list[dict[str, Any]] = field(default_factory=list)


class FlowRuntime:
    """Runs a compiled `FlowDefinition`."""

    def __init__(self, flow: FlowDefinition, *, dictionary: dict[str, Any] | None = None) -> None:
        self.flow = flow
        self.ctx = ContextStack()
        if flow.initial_context:
            self.ctx.global_ns.update(flow.initial_context)
        self.dictionary = copy.deepcopy(dictionary) if dictionary is not None else tree_copy()
        self.ctx.global_ns["dictionary"] = copy.deepcopy(self.dictionary)
        self.flow_state: FlowState = FlowState.PENDING
        self.node_state: dict[str, NodeState] = {}
        self._node_runs: dict[str, NodeRunInfo] = {}
        self._flow_logs: list[dict[str, Any]] = []
        self._t0: float | None = None
        self._root_tracker = TaskTracker()
        self._gate = GlobalConcurrencyGate(limit=256)
        self.executors = StrategyExecutors(flow.strategies, self._gate)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cancel_dereg: Any = None

    def _nid(self, m: FlowMember) -> str:
        # id 是节点唯一逻辑主键；模型层已保证非空，此处无需回落 name。
        return m.id

    def _now_ms(self) -> int:
        """Milliseconds since :meth:`run` started tracking (0 before start)."""
        if self._t0 is None:
            return 0
        return max(0, int((time.monotonic() - self._t0) * 1000))

    def _mark(self, nid: str, st: NodeState, *, parent_id: str | None = None) -> None:
        self.node_state[nid] = st
        t = self._now_ms()
        info = self._node_runs.get(nid)
        if info is None:
            info = NodeRunInfo(
                node_id=nid,
                order=len(self._node_runs),
                first_seen_ms=t,
                final_state=st,
                parent_id=parent_id,
            )
            self._node_runs[nid] = info
        # `parent_id` is only authoritative on the FIRST observation. If a
        # loop child re-enters across iterations it must stay attached to
        # the loop it was first scheduled under rather than flipping to
        # whatever the current caller passes.
        info.final_state = st
        info.transitions.append({"state": st.value, "t_ms": t})
        if info.started_ms is None and st in (
            NodeState.STAGING,
            NodeState.DISPATCHED,
            NodeState.RUNNING,
        ):
            info.started_ms = t
        if st in (NodeState.SUCCESS, NodeState.FAILED, NodeState.SKIPPED):
            info.finished_ms = t

    def _strategy_for(self, m: FlowMember) -> ExecutionStrategy:
        try:
            return self.flow.strategies[m.strategy_ref]
        except KeyError as e:
            raise FlowEngineError(
                f"Node {self._nid(m)!r} references undefined strategy {m.strategy_ref!r}"
            ) from e

    def _append_node_logs(
        self,
        nid: str,
        entries: list[dict[str, Any]] | None,
        *,
        attempt: int | None = None,
    ) -> None:
        """Append collected log entries to ``NodeRunInfo.logs``.

        ``attempt`` is only attached when > 0 so the common case (no
        retries) keeps log records minimal. Missing ``nid`` is a no-op so
        callers don't need to null-check the record.
        """
        if not entries:
            return
        info = self._node_runs.get(nid)
        if info is None:
            return
        if attempt is not None and attempt > 0:
            for e in entries:
                rec = dict(e)
                rec["attempt"] = attempt
                info.logs.append(rec)
        else:
            for e in entries:
                info.logs.append(dict(e))

    def _append_flow_logs(self, entries: list[dict[str, Any]] | None) -> None:
        if not entries:
            return
        for e in entries:
            self._flow_logs.append(dict(e))

    def _apply_outputs_safe(self, ctx: ContextStack, result: dict[str, Any], outputs: dict[str, str]) -> None:
        # `ContextStack.set_path` is internally locked; this helper exists so
        # that call sites read clearly and so we can group the boundary write
        # atomically in the future if multi-key transactional semantics are
        # ever required.
        with ctx.lock:
            apply_outputs(result, outputs, ctx)

    def _result(self, message: str | None) -> FlowRunResult:
        runs = sorted(self._node_runs.values(), key=lambda r: r.order)
        return FlowRunResult(
            state=self.flow_state,
            context=self.ctx,
            message=message,
            node_state=dict(self.node_state),
            node_runs=runs,
            flow_logs=list(self._flow_logs),
        )

    async def run(self) -> FlowRunResult:
        install_signal_handlers()
        self._loop = asyncio.get_running_loop()
        self._cancel_dereg = asyncio_main_cancel(self._loop)
        self._t0 = time.monotonic()
        self.flow_state = FlowState.RUNNING
        try:
            with dictionary_scope(self.dictionary):
                return await self._run_scoped()
        finally:
            self.executors.shutdown()
            if self._cancel_dereg is not None:
                try:
                    self._cancel_dereg()
                except Exception:  # noqa: BLE001
                    logger.debug("Cancel deregister failed", exc_info=True)
                self._cancel_dereg = None

    async def _run_scoped(self) -> FlowRunResult:
        try:
            if self.flow.hooks and self.flow.hooks.on_start:
                self._append_flow_logs(
                    run_hook_script(self.flow.hooks.on_start, self.ctx, source="on_start")
                )
            await self._run_members(self.flow.nodes, self.ctx, self._root_tracker)
            await self._root_tracker.wait_all()
            self.flow_state = FlowState.COMPLETED
            if self.flow.hooks and self.flow.hooks.on_complete:
                self._append_flow_logs(
                    run_hook_script(
                        self.flow.hooks.on_complete, self.ctx, source="on_complete"
                    )
                )
            return self._result(None)
        except TerminateInterrupt:
            self.flow_state = FlowState.TERMINATED
            return self._result("terminated")
        except JumpTarget as j:
            # A jump escaped every enclosing scope -> treat as failure rather
            # than leaking a control-flow exception to the caller.
            self.flow_state = FlowState.FAILED
            msg = f"Unresolved jump target: {j.target!r}"
            if self.flow.hooks and self.flow.hooks.on_failure:
                self._append_flow_logs(
                    run_hook_script(
                        self.flow.hooks.on_failure,
                        self.ctx,
                        {"error": msg},
                        source="on_failure",
                    )
                )
            return self._result(msg)
        except FlowEngineError as e:
            self.flow_state = FlowState.FAILED
            if self.flow.hooks and self.flow.hooks.on_failure:
                self._append_flow_logs(
                    run_hook_script(
                        self.flow.hooks.on_failure,
                        self.ctx,
                        {"error": str(e)},
                        source="on_failure",
                    )
                )
            return self._result(str(e))
        except Exception as e:  # noqa: BLE001
            logger.exception("Flow failed")
            self.flow_state = FlowState.FAILED
            if self.flow.hooks and self.flow.hooks.on_failure:
                self._append_flow_logs(
                    run_hook_script(
                        self.flow.hooks.on_failure,
                        self.ctx,
                        {"error": str(e)},
                        source="on_failure",
                    )
                )
            return self._result(str(e))
    async def _run_members(
        self,
        members: list[FlowMember],
        ctx: ContextStack,
        tracker: TaskTracker,
        *,
        parent_id: str | None = None,
    ) -> None:
        i = 0
        jumps = 0
        while i < len(members):
            m = members[i]
            try:
                await self._dispatch_member(m, ctx, tracker, parent_id=parent_id)
            except JumpTarget as j:
                idx = self._index_by_id(members, j.target)
                if idx is not None:
                    jumps += 1
                    if jumps > _MAX_JUMPS_PER_SCOPE:
                        raise FlowEngineError(
                            f"Jump loop detected in scope (>{_MAX_JUMPS_PER_SCOPE} jumps to {j.target!r})"
                        ) from j
                    i = idx
                    continue
                raise
            i += 1

    def _index_by_id(self, members: list[FlowMember], target: str) -> int | None:
        for idx, mm in enumerate(members):
            if self._nid(mm) == target:
                return idx
        return None

    async def _dispatch_member(
        self,
        m: FlowMember,
        ctx: ContextStack,
        tracker: TaskTracker,
        *,
        parent_id: str | None = None,
    ) -> None:
        nid = self._nid(m)

        # `wait_before` must run BEFORE `condition`: a condition can legitimately
        # depend on outputs produced by prior background tasks, and those are
        # only visible after draining the tracker.
        if m.wait_before:
            await tracker.wait_all()

        if not eval_condition(m.condition, ctx):
            self._mark(nid, NodeState.SKIPPED, parent_id=parent_id)
            return

        st = self._strategy_for(m)
        mode = _strategy_mode(st)

        self._mark(nid, NodeState.STAGING, parent_id=parent_id)

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

    # ------------------------------------------------------------------
    # Task execution core
    # ------------------------------------------------------------------

    @staticmethod
    async def _with_timeout(aw: Any, timeout: float | None) -> Any:
        if timeout is None:
            return await aw
        return await asyncio.wait_for(aw, timeout=timeout)

    async def _run_once(
        self,
        node: TaskNode,
        ctx: ContextStack,
        st: ExecutionStrategy,
        *,
        attempt: int = 0,
    ) -> dict[str, Any]:
        """Run the task exactly once: pre_exec -> dispatch by mode -> raw result.

        Respects `GlobalConcurrencyGate` with SYNC fallback for THREAD/PROCESS,
        and applies strategy timeout uniformly across all modes. Captured
        log entries (from ``pre_exec`` and the task script itself) are
        appended to ``NodeRunInfo.logs`` as soon as each piece completes so
        that a failed retry still preserves whatever it managed to emit
        before the exception propagated.
        """
        nid = self._nid(node)
        pre = _node_hook(node.hooks, "pre_exec")
        if pre:
            self._append_node_logs(
                nid, run_hook_script(pre, ctx, source="pre_exec"), attempt=attempt
            )

        mode = _strategy_mode(st)
        timeout = st.timeout
        acquired = False
        if mode in (StrategyMode.THREAD, StrategyMode.PROCESS):
            if self._gate.try_acquire():
                acquired = True
            else:
                mode = StrategyMode.SYNC

        try:
            if mode in (StrategyMode.SYNC, StrategyMode.ASYNC):
                result, task_logs = await self._with_timeout(
                    asyncio.to_thread(run_task_script, node.script, ctx, node.boundary.inputs),
                    timeout,
                )
                self._append_node_logs(nid, task_logs, attempt=attempt)
                return result
            if mode == StrategyMode.THREAD:
                loop = asyncio.get_running_loop()
                pool = self.executors.thread_pool(node.strategy_ref)
                ctxvars = copy_context()

                def sync() -> tuple[dict[str, Any], list[dict[str, Any]]]:
                    return run_task_script(node.script, ctx, node.boundary.inputs)

                fut: ConcurrentFuture[tuple[dict[str, Any], list[dict[str, Any]]]] = pool.submit(
                    ctxvars.run, sync
                )
                result, task_logs = await self._with_timeout(
                    asyncio.wrap_future(fut, loop=loop), timeout
                )
                self._append_node_logs(nid, task_logs, attempt=attempt)
                return result
            if mode == StrategyMode.PROCESS:
                loop = asyncio.get_running_loop()
                pool = self.executors.process_pool(node.strategy_ref)
                payload = {
                    "script": node.script,
                    "inputs": node.boundary.inputs,
                    "flat_inputs": _serialize_inputs(ctx, node.boundary.inputs),
                    "dictionary": self.dictionary,
                }
                fut2 = pool.submit(process_starlark_task, payload)
                raw = await self._with_timeout(asyncio.wrap_future(fut2, loop=loop), timeout)
                self._append_node_logs(nid, raw.get("logs"), attempt=attempt)
                return raw["result"]
        finally:
            if acquired:
                self._gate.release()

        raise AssertionError("unreachable")

    async def _run_with_retries(
        self,
        node: TaskNode,
        ctx: ContextStack,
        st: ExecutionStrategy,
    ) -> dict[str, Any]:
        """Run the task applying retry budget, on_error, and post_exec hook.

        Flow-control interrupts (Terminate/Jump/Continue/Break) are never
        retried: they are propagated to the nearest handler unchanged.
        """
        nid = self._nid(node)
        retries = st.retry_count
        last_exc: BaseException | None = None
        for attempt in range(retries + 1):
            try:
                result = await self._run_once(node, ctx, st, attempt=attempt)
                post = _node_hook(node.hooks, "post_exec")
                if post:
                    self._append_node_logs(
                        nid,
                        run_hook_script(
                            post, ctx, {"result": result}, source="post_exec"
                        ),
                        attempt=attempt,
                    )
                return result
            except (TerminateInterrupt, JumpTarget, ContinueInterrupt, BreakInterrupt):
                raise
            except asyncio.TimeoutError as e:
                last_exc = e
                decision = self._handle_on_error(node, e)
                if decision == "retry":
                    continue
                if decision == "ignore":
                    return {}
                self._mark(nid, NodeState.FAILED)
                raise FlowEngineError(f"Timeout in node {nid}") from e
            except sl.StarlarkError as e:
                last_exc = e
                decision = self._handle_on_error(node, e)
                if decision == "retry":
                    continue
                if decision == "ignore":
                    return {}
                self._mark(nid, NodeState.FAILED)
                raise FlowEngineError(f"Starlark error in {nid}: {e}") from e
            except Exception as e:  # noqa: BLE001
                last_exc = e
                decision = self._handle_on_error(node, e)
                if decision == "retry":
                    continue
                if decision == "ignore":
                    return {}
                self._mark(nid, NodeState.FAILED)
                raise FlowEngineError(f"Error in {nid}: {e}") from e

        self._mark(nid, NodeState.FAILED)
        raise FlowEngineError(f"Node {nid} failed after retries: {last_exc!r}")

    async def _execute_task_node(
        self,
        node: TaskNode,
        ctx: ContextStack,
        tracker: TaskTracker,
        *,
        await_result: bool,
    ) -> None:
        nid = self._nid(node)
        st = self._strategy_for(node)

        if await_result:
            try:
                result = await self._run_with_retries(node, ctx, st)
            except (TerminateInterrupt, JumpTarget, ContinueInterrupt, BreakInterrupt):
                # A sync-mode task that invokes a flow-control builtin
                # (flow_continue / flow_break / flow_terminate / flow_jump)
                # intentionally opts out of producing output. Without this
                # handler the node would stay RUNNING because `_mark(RUNNING)`
                # was already written on entry and no terminal transition
                # follows. Mark SKIPPED so observers see a clean finish while
                # the exception still propagates to the enclosing scope.
                self._mark(nid, NodeState.SKIPPED)
                raise
            self._apply_outputs_safe(ctx, result, node.boundary.outputs)
            self._mark(nid, NodeState.SUCCESS)
            return

        loop = asyncio.get_running_loop()

        async def bg() -> None:
            self._mark(nid, NodeState.RUNNING)
            try:
                result = await self._run_with_retries(node, ctx, st)
            except (TerminateInterrupt, JumpTarget, ContinueInterrupt, BreakInterrupt):
                # Surface control-flow from background tasks at the next
                # barrier. We DO mark FAILED here so that observers can
                # distinguish "still in flight" from "control-flow aborted".
                self._mark(nid, NodeState.FAILED)
                raise
            except BaseException:
                # `_run_with_retries` already transitioned to FAILED before
                # re-raising; kept explicit in case the contract changes.
                self._mark(nid, NodeState.FAILED)
                raise
            self._apply_outputs_safe(ctx, result, node.boundary.outputs)
            self._mark(nid, NodeState.SUCCESS)

        tracker.create_task(loop, bg())

    def _handle_on_error(self, node: TaskNode, exc: BaseException) -> str:
        """Decide what to do with `exc` based on `node.on_error`.

        Returns one of:
          * ``"retry"``    - caller should retry (subject to retry_count).
          * ``"ignore"``   - swallow the error, treat node as completed with
                             an empty result (no outputs applied).
          * ``"propagate"``- caller should re-raise and mark the node FAILED.

        May raise control-flow exceptions (JumpTarget/Continue/Break) to
        redirect execution per `OnErrorAction`.
        """
        cfg = node.on_error
        if not cfg:
            return "propagate"
        act = cfg.action
        if isinstance(act, str):
            try:
                act = OnErrorAction(act)
            except ValueError:
                return "propagate"
        if act == OnErrorAction.RETRY:
            return "retry"
        if act == OnErrorAction.IGNORE:
            return "ignore"
        # Use `raise ... from None` so Python does not attach the caught
        # task exception as `__context__`; otherwise tracebacks end up with
        # the noisy "During handling of the above exception, another exception
        # occurred" banner even though the redirect is intentional.
        if act == OnErrorAction.JUMP and cfg.target:
            raise JumpTarget(cfg.target) from None
        if act == OnErrorAction.CONTINUE:
            raise ContinueInterrupt() from None
        if act == OnErrorAction.BREAK:
            raise BreakInterrupt() from None
        if act == OnErrorAction.CUSTOM and cfg.script:
            nid = self._nid(node)
            self._append_node_logs(
                nid,
                run_hook_script(
                    cfg.script, self.ctx, {"error": str(exc)}, source="on_error"
                ),
            )
            return "propagate"
        return "propagate"

    # ------------------------------------------------------------------
    # Composite nodes
    # ------------------------------------------------------------------

    @contextmanager
    def _pushed_frame(self, ctx: ContextStack, frame: ContextFrame) -> Iterator[None]:
        ctx.push(frame)
        try:
            yield
        finally:
            ctx.pop()

    async def _execute_loop(self, node: LoopNode, ctx: ContextStack, tracker: TaskTracker) -> None:
        nid = self._nid(node)
        await tracker.wait_all()
        self._mark(nid, NodeState.RUNNING)
        hooks = node.hooks if isinstance(node.hooks, LoopHooks) else None

        if hooks and hooks.pre_exec:
            self._append_node_logs(
                nid, run_hook_script(hooks.pre_exec, ctx, source="pre_exec")
            )

        items = eval_iterable_expr(node.iterable, ctx)
        info = self._node_runs.get(nid)
        if info is not None:
            info.iterations = len(items)
        copy_mode = getattr(node, "copy_item", "shared")
        isolation = getattr(node, "iteration_isolation", "shared")
        collect = getattr(node, "iteration_collect", None)

        strategy = self._strategy_for(node)
        mode = _strategy_mode(strategy)
        # Concurrency==1 falls back to the legacy sequential path so prior
        # flow semantics (frame reuse, ordered writes, break/continue at the
        # outermost iteration) are preserved bit-for-bit.
        concurrency = 1 if mode == StrategyMode.SYNC else max(1, strategy.concurrency)

        prepared: list[Any] = []
        for raw_it in items:
            if copy_mode == "deep":
                prepared.append(copy.deepcopy(raw_it))
            elif copy_mode == "shallow":
                prepared.append(copy.copy(raw_it))
            else:
                prepared.append(raw_it)

        try:
            if concurrency == 1:
                await self._run_loop_sequential(
                    node, prepared, ctx, tracker, hooks, isolation, collect
                )
            else:
                await self._run_loop_concurrent(
                    node, prepared, ctx, tracker, hooks, isolation, collect, concurrency
                )
        finally:
            if hooks and hooks.post_exec:
                try:
                    self._append_node_logs(
                        nid,
                        run_hook_script(hooks.post_exec, ctx, source="post_exec"),
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("loop post_exec hook failed")

        await tracker.wait_all()
        self._mark(nid, NodeState.SUCCESS)

    @staticmethod
    def _collect_iteration_result(
        iter_ctx: ContextStack, parent_ctx: ContextStack, collect: Any
    ) -> None:
        """Append a value read from ``iter_ctx`` onto a list at ``collect.append_to``
        in ``parent_ctx``. Missing source path -> no-op (caller decides whether
        to treat as an error via on_error); missing / non-list sink -> fresh
        list. The parent's lock is held during the read-modify-write so
        concurrent iterations don't lose updates.
        """
        try:
            val = iter_ctx.get_path(collect.from_path)
        except Exception as e:  # noqa: BLE001
            logger.debug(
                "iteration_collect: could not read %r from iteration ctx: %s",
                collect.from_path,
                e,
            )
            return
        with parent_ctx.lock:
            try:
                existing = parent_ctx.get_path(collect.append_to)
            except Exception:  # noqa: BLE001
                existing = None
            lst = list(existing) if isinstance(existing, list) else []
            lst.append(val)
            parent_ctx.set_path(collect.append_to, lst)

    async def _run_loop_sequential(
        self,
        node: LoopNode,
        items: list[Any],
        ctx: ContextStack,
        tracker: TaskTracker,
        hooks: LoopHooks | None,
        isolation: str,
        collect: Any,
    ) -> None:
        """Legacy path: run iterations one-by-one.

        When ``isolation == 'fork'`` we still honour it — each iteration gets
        its own forked stack and we still collect after the iteration.
        Otherwise we reuse the parent ctx directly, which preserves the
        original semantics exercised by every existing test/example.
        """
        nid = self._nid(node)
        for it in items:
            if isolation == "fork":
                iter_ctx = ctx.fork(clone_global=True)
                iter_tracker = TaskTracker(parent=None)
                frame = ContextFrame(node_id=nid, alias=node.alias, loop_item=it, loop_alias=node.alias)
                with self._pushed_frame(iter_ctx, frame):
                    try:
                        if hooks and hooks.on_iteration_start:
                            self._append_node_logs(
                                nid,
                                run_hook_script(
                                    hooks.on_iteration_start,
                                    iter_ctx,
                                    {"item": it},
                                    source="on_iteration_start",
                                ),
                            )
                        try:
                            await self._run_members(
                                node.children, iter_ctx, iter_tracker, parent_id=nid
                            )
                        except ContinueInterrupt:
                            continue
                        except BreakInterrupt:
                            # No partial collect on break.
                            break
                        # Collect while the iteration frame is still pushed so
                        # ``from_path`` can reference the loop alias (``$.it.*``);
                        # on continue/break/error we skip (no partial results).
                        if collect is not None:
                            self._collect_iteration_result(iter_ctx, ctx, collect)
                    finally:
                        try:
                            await iter_tracker.wait_all()
                        finally:
                            if hooks and hooks.on_iteration_end:
                                try:
                                    self._append_node_logs(
                                        nid,
                                        run_hook_script(
                                            hooks.on_iteration_end,
                                            iter_ctx,
                                            {"item": it},
                                            source="on_iteration_end",
                                        ),
                                    )
                                except Exception:  # noqa: BLE001
                                    logger.exception("on_iteration_end hook failed")
                continue

            iter_tracker = TaskTracker(parent=tracker)
            frame = ContextFrame(node_id=nid, alias=node.alias, loop_item=it, loop_alias=node.alias)
            with self._pushed_frame(ctx, frame):
                try:
                    if hooks and hooks.on_iteration_start:
                        self._append_node_logs(
                            nid,
                            run_hook_script(
                                hooks.on_iteration_start,
                                ctx,
                                {"item": it},
                                source="on_iteration_start",
                            ),
                        )
                    try:
                        await self._run_members(
                            node.children, ctx, iter_tracker, parent_id=nid
                        )
                    except ContinueInterrupt:
                        continue
                    except BreakInterrupt:
                        break
                    # Same rationale as the fork branch: the alias frame must
                    # still be live for ``$.alias.*`` lookups to succeed.
                    if collect is not None:
                        self._collect_iteration_result(ctx, ctx, collect)
                finally:
                    try:
                        await iter_tracker.wait_all()
                    finally:
                        if hooks and hooks.on_iteration_end:
                            try:
                                self._append_node_logs(
                                    nid,
                                    run_hook_script(
                                        hooks.on_iteration_end,
                                        ctx,
                                        {"item": it},
                                        source="on_iteration_end",
                                    ),
                                )
                            except Exception:  # noqa: BLE001
                                logger.exception("on_iteration_end hook failed")

    async def _run_loop_concurrent(
        self,
        node: LoopNode,
        items: list[Any],
        ctx: ContextStack,
        tracker: TaskTracker,
        hooks: LoopHooks | None,
        isolation: str,
        collect: Any,
        concurrency: int,
    ) -> None:
        """Dispatch each iteration as an asyncio task bounded by a semaphore.

        * ``isolation='fork'`` -> per-iteration deep-copied global_ns.
        * ``isolation='shared'`` -> share global_ns with the parent ctx while
          still getting a per-iteration frame stack (so ``$.item`` and loop
          frames don't collide). Concurrent writes to the same path on the
          shared ``global_ns`` are serialized by the shared RLock handed down
          from :meth:`ContextStack.fork`.

        ``BreakInterrupt`` raised inside an iteration cancels further
        iterations (subject to already-running ones finishing). ``Continue``
        inside an iteration is treated as "skip this one, keep going".
        """
        nid = self._nid(node)
        sem = asyncio.Semaphore(concurrency)
        stop_requested = {"flag": False}

        async def one(idx: int, raw_item: Any) -> None:
            if stop_requested["flag"]:
                return
            async with sem:
                if stop_requested["flag"]:
                    return
                iter_ctx = ctx.fork(clone_global=(isolation == "fork"))
                iter_tracker = TaskTracker(parent=None)
                frame = ContextFrame(
                    node_id=nid,
                    alias=node.alias,
                    loop_item=raw_item,
                    loop_alias=node.alias,
                )
                with self._pushed_frame(iter_ctx, frame):
                    try:
                        if hooks and hooks.on_iteration_start:
                            self._append_node_logs(
                                nid,
                                run_hook_script(
                                    hooks.on_iteration_start,
                                    iter_ctx,
                                    {"item": raw_item},
                                    source="on_iteration_start",
                                ),
                            )
                        try:
                            await self._run_members(
                                node.children, iter_ctx, iter_tracker, parent_id=nid
                            )
                        except ContinueInterrupt:
                            return
                        except BreakInterrupt:
                            stop_requested["flag"] = True
                            return
                        # Must collect while the alias frame is still pushed so
                        # ``from_path`` of form ``$.alias.*`` can resolve; skip
                        # on continue/break/error (no partial results).
                        if collect is not None:
                            self._collect_iteration_result(iter_ctx, ctx, collect)
                    finally:
                        try:
                            await iter_tracker.wait_all()
                        finally:
                            if hooks and hooks.on_iteration_end:
                                try:
                                    self._append_node_logs(
                                        nid,
                                        run_hook_script(
                                            hooks.on_iteration_end,
                                            iter_ctx,
                                            {"item": raw_item},
                                            source="on_iteration_end",
                                        ),
                                    )
                                except Exception:  # noqa: BLE001
                                    logger.exception("on_iteration_end hook failed")

        coros = [one(i, it) for i, it in enumerate(items)]
        results = await asyncio.gather(*coros, return_exceptions=True)
        first_exc: BaseException | None = None
        for r in results:
            if isinstance(r, BaseException) and not isinstance(
                r, (BreakInterrupt, ContinueInterrupt)
            ):
                if first_exc is None:
                    first_exc = r
                else:
                    logger.error("Additional concurrent-loop exception: %r", r)
        if first_exc is not None:
            raise first_exc
        # Drain any background tasks the concurrent iterations may have
        # attached to the parent tracker (none should have, since concurrent
        # iterations use their own trackers, but be defensive).
        await tracker.wait_all()

    async def _execute_subflow(self, node: SubflowNode, ctx: ContextStack, tracker: TaskTracker) -> None:
        nid = self._nid(node)
        await tracker.wait_all()
        self._mark(nid, NodeState.RUNNING)
        hooks = node.hooks if isinstance(node.hooks, NodeHooks) else None

        if hooks and hooks.pre_exec:
            self._append_node_logs(
                nid, run_hook_script(hooks.pre_exec, ctx, source="pre_exec")
            )

        sub_tracker = TaskTracker(parent=tracker)
        frame = ContextFrame(node_id=nid, alias=node.alias)
        with self._pushed_frame(ctx, frame):
            try:
                await self._run_members(node.children, ctx, sub_tracker, parent_id=nid)
            finally:
                # Drain isolated child tracker BEFORE popping the frame so that
                # background tasks' outputs still resolve against this subflow.
                await sub_tracker.wait_all()

        if hooks and hooks.post_exec:
            try:
                self._append_node_logs(
                    nid, run_hook_script(hooks.post_exec, ctx, source="post_exec")
                )
            except Exception:  # noqa: BLE001
                logger.exception("subflow post_exec hook failed")

        self._mark(nid, NodeState.SUCCESS)
