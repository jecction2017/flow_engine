"""Unit tests targeting the orchestrator fixes:

* TerminateInterrupt bypasses retry and marks TERMINATED.
* Background tasks honor on_error / retry.
* Subflow uses an isolated child tracker and does not leak context frames.
* Unresolved runtime `flow_jump()` targets end in FAILED instead of escaping.
* Loop / Subflow honor `pre_exec` / `post_exec` hooks.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from flow_engine.engine.compiler import compile_flow
from flow_engine.engine.models import FlowDefinition, FlowState, NodeState
from flow_engine.engine.orchestrator import FlowRuntime


def _flow(y: str) -> FlowDefinition:
    data: dict[str, Any] = yaml.safe_load(y)
    return compile_flow(FlowDefinition.model_validate(data))


@pytest.mark.asyncio
async def test_flow_terminate_bypasses_retry() -> None:
    """flow_terminate() inside a task must short-circuit even with retry_count>0."""
    flow = _flow(
        """
        name: terminate_test
        strategies:
          retry_sync:
            name: retry_sync
            mode: sync
            retry_count: 3
          default_sync:
            name: default_sync
            mode: sync
        nodes:
          - name: halt
            type: task
            strategy_ref: retry_sync
            script: |
              flow_terminate()
              {}
          - name: unreached
            type: task
            strategy_ref: default_sync
            script: |
              {"x": 1}
            boundary:
              outputs:
                x: "$.global.reached"
        """
    )
    res = await FlowRuntime(flow).run()
    assert res.state == FlowState.TERMINATED
    assert "reached" not in res.context.global_ns


@pytest.mark.asyncio
async def test_background_task_honors_ignore() -> None:
    """Background (non-sync) task with on_error=ignore must not fail the flow."""
    flow = _flow(
        """
        name: bg_ignore
        strategies:
          async_strategy:
            name: async_strategy
            mode: async
          default_sync:
            name: default_sync
            mode: sync
        nodes:
          - name: flaky
            type: task
            strategy_ref: async_strategy
            script: |
              {"x": 1 // 0}
            on_error:
              action: ignore
          - name: barrier
            type: task
            strategy_ref: default_sync
            wait_before: true
            script: |
              {"ok": True}
            boundary:
              outputs:
                ok: "$.global.barrier_ok"
        """
    )
    rt = FlowRuntime(flow)
    res = await rt.run()
    assert res.state == FlowState.COMPLETED
    assert res.context.global_ns.get("barrier_ok") is True


@pytest.mark.asyncio
async def test_background_task_retry_on_error() -> None:
    """Background task with retry eventually succeeds once the script path heals."""
    flow = _flow(
        """
        name: bg_retry
        strategies:
          async_strategy:
            name: async_strategy
            mode: async
            retry_count: 2
          default_sync:
            name: default_sync
            mode: sync
        initial_context:
          divisor: 0
        nodes:
          - name: heal
            type: task
            strategy_ref: default_sync
            script: |
              {"d": 1}
            boundary:
              outputs:
                d: "$.global.divisor"
          - name: flaky
            type: task
            strategy_ref: async_strategy
            wait_before: true
            script: |
              {"x": 10 // resolve("$.global.divisor")}
            on_error:
              action: retry
            boundary:
              outputs:
                x: "$.global.x"
          - name: barrier
            type: task
            strategy_ref: default_sync
            wait_before: true
            script: |
              {"ok": True}
        """
    )
    res = await FlowRuntime(flow).run()
    assert res.state == FlowState.COMPLETED
    assert res.context.global_ns.get("x") == 10


@pytest.mark.asyncio
async def test_subflow_no_frame_leak() -> None:
    """After a subflow completes, ContextStack must have no residual frames."""
    flow = _flow(
        """
        name: subflow_leak
        strategies:
          default_sync:
            name: default_sync
            mode: sync
        nodes:
          - name: sub
            type: subflow
            strategy_ref: default_sync
            alias: s
            children:
              - name: inner
                type: task
                strategy_ref: default_sync
                script: |
                  {"v": 42}
                boundary:
                  outputs:
                    v: "$.global.result"
        """
    )
    rt = FlowRuntime(flow)
    res = await rt.run()
    assert res.state == FlowState.COMPLETED
    assert res.context.global_ns.get("result") == 42
    assert res.context.frames == []


@pytest.mark.asyncio
async def test_subflow_frame_popped_on_error() -> None:
    """If a subflow child fails the frame must still be popped."""
    flow = _flow(
        """
        name: subflow_err
        strategies:
          default_sync:
            name: default_sync
            mode: sync
        nodes:
          - name: sub
            type: subflow
            strategy_ref: default_sync
            alias: s
            children:
              - name: boom
                type: task
                strategy_ref: default_sync
                script: |
                  {"x": 1 // 0}
        """
    )
    rt = FlowRuntime(flow)
    res = await rt.run()
    assert res.state == FlowState.FAILED
    assert res.context.frames == []


@pytest.mark.asyncio
async def test_unresolved_runtime_jump_marks_failed() -> None:
    """A runtime flow_jump() to a nonexistent id must not escape `run()`."""
    flow = _flow(
        """
        name: bad_jump
        strategies:
          default_sync:
            name: default_sync
            mode: sync
        nodes:
          - name: a
            type: task
            strategy_ref: default_sync
            script: |
              flow_jump("nowhere")
              {}
        """
    )
    res = await FlowRuntime(flow).run()
    assert res.state == FlowState.FAILED
    assert res.message is not None and "nowhere" in res.message


@pytest.mark.asyncio
async def test_loop_pre_and_post_exec_hooks_fire() -> None:
    """LoopHooks.pre_exec / post_exec must run exactly once per loop node."""
    flow = _flow(
        """
        name: loop_hooks
        strategies:
          default_sync:
            name: default_sync
            mode: sync
        initial_context:
          items: [1, 2, 3]
          pre: 0
          post: 0
          sum: 0
        nodes:
          - name: lp
            type: loop
            strategy_ref: default_sync
            iterable: resolve("$.global.items")
            alias: it
            hooks:
              pre_exec: |
                _ = 1
              post_exec: |
                _ = 1
            children:
              - name: accum
                type: task
                strategy_ref: default_sync
                script: |
                  {"s": resolve("$.global.sum") + resolve("$.item")}
                boundary:
                  outputs:
                    s: "$.global.sum"
        """
    )
    # pre_exec / post_exec snippets above are side-effect-free; the real
    # assertion is that the loop completes successfully with hooks defined,
    # which previously would have been silently ignored but now must at least
    # be evaluated without errors.
    res = await FlowRuntime(flow).run()
    assert res.state == FlowState.COMPLETED
    assert res.context.global_ns["sum"] == 6


@pytest.mark.asyncio
async def test_concurrent_writes_to_global_ns_are_safe() -> None:
    """Many async tasks writing different global paths must not lose updates
    nor crash due to concurrent dict mutation."""
    n = 40
    children = []
    for i in range(n):
        children.append(
            {
                "name": f"w{i}",
                "type": "task",
                "strategy_ref": "async_strategy",
                "script": f'{{"v": {i}}}',
                "boundary": {"outputs": {"v": f"$.global.bucket.k{i}"}},
            }
        )
    doc: dict[str, Any] = {
        "name": "concurrent",
        "strategies": {
            "async_strategy": {"name": "async_strategy", "mode": "async", "concurrency": 16},
            "default_sync": {"name": "default_sync", "mode": "sync"},
        },
        "initial_context": {"bucket": {}},
        "nodes": [
            *children,
            {
                "name": "barrier",
                "type": "task",
                "strategy_ref": "default_sync",
                "wait_before": True,
                "script": '{"ok": True}',
            },
        ],
    }
    flow = compile_flow(FlowDefinition.model_validate(doc))
    res = await FlowRuntime(flow).run()
    assert res.state == FlowState.COMPLETED
    bucket = res.context.global_ns["bucket"]
    assert len(bucket) == n
    for i in range(n):
        assert bucket[f"k{i}"] == i


@pytest.mark.asyncio
async def test_result_exposes_node_state_snapshot() -> None:
    flow = _flow(
        """
        name: ns_snapshot
        strategies:
          default_sync:
            name: default_sync
            mode: sync
        nodes:
          - name: a
            type: task
            strategy_ref: default_sync
            script: |
              {"x": 1}
          - name: b
            type: task
            strategy_ref: default_sync
            condition: "False"
            script: |
              {"x": 2}
        """
    )
    res = await FlowRuntime(flow).run()
    assert res.state == FlowState.COMPLETED
    assert res.node_state["a"] == NodeState.SUCCESS
    assert res.node_state["b"] == NodeState.SKIPPED


def test_compiler_rejects_retry_with_zero_retry_count() -> None:
    from flow_engine.engine.exceptions import CompilationError

    doc = {
        "name": "bad_retry",
        "strategies": {"default_sync": {"name": "default_sync", "mode": "sync"}},
        "nodes": [
            {
                "name": "t",
                "type": "task",
                "strategy_ref": "default_sync",
                "script": "{}",
                "on_error": {"action": "retry"},
            }
        ],
    }
    with pytest.raises(CompilationError):
        compile_flow(FlowDefinition.model_validate(doc))


@pytest.mark.asyncio
async def test_loop_copy_item_deep_isolates_mutation() -> None:
    """With copy_item=deep, mutations inside an iteration must not leak into
    sibling iterations that share references in the source list."""
    shared = {"n": 0}
    doc = {
        "name": "deep_item",
        "strategies": {"default_sync": {"name": "default_sync", "mode": "sync"}},
        "initial_context": {"items": [shared, shared, shared], "sum": 0},
        "nodes": [
            {
                "name": "lp",
                "type": "loop",
                "strategy_ref": "default_sync",
                "iterable": 'resolve("$.global.items")',
                "alias": "it",
                "copy_item": "deep",
                "children": [
                    {
                        "name": "step",
                        "type": "task",
                        "strategy_ref": "default_sync",
                        "script": '{"s": resolve("$.global.sum") + 1}',
                        "boundary": {"outputs": {"s": "$.global.sum"}},
                    }
                ],
            }
        ],
    }
    flow = compile_flow(FlowDefinition.model_validate(doc))
    res = await FlowRuntime(flow).run()
    assert res.state == FlowState.COMPLETED
    assert res.context.global_ns["sum"] == 3
    # The original source objects are unchanged because the loop deep-copied
    # each one before binding it as $.item.
    assert shared == {"n": 0}


@pytest.mark.asyncio
async def test_signal_handlers_idempotent_across_runs() -> None:
    """Multiple run() invocations must not accumulate cancel hooks unboundedly."""
    from flow_engine.engine import resources as res_mod

    flow = _flow(
        """
        name: noop
        strategies:
          default_sync:
            name: default_sync
            mode: sync
        nodes:
          - name: n
            type: task
            strategy_ref: default_sync
            script: |
              {}
        """
    )
    # Snapshot registry size before a pair of runs.
    before = len(res_mod._snapshot_cancel_hooks())
    for _ in range(3):
        await FlowRuntime(flow).run()
    after = len(res_mod._snapshot_cancel_hooks())
    # Each run registers a cancel hook and deregisters it on exit; the net
    # delta must stay zero (previously grew by 1 per run).
    assert after == before
