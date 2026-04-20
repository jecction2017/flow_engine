"""Tests for ManagedRunner – the client-side runtime component.

We mock the HTTP layer (`_http_get/_http_post/_http_put/_http_delete`) and
the FlowRuntime so these tests are pure unit tests without spinning up the
HTTP API.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from flow_engine.runner import managed_runner as mr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeHttpBackend:
    """Records all HTTP calls made by the runner and returns scripted replies."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.resolve_reply: dict[str, Any] = {
            "version": 1,
            "definition": {
                "name": "fake",
                "version": "1.0.0",
                "strategies": {"default_sync": {"name": "default_sync", "mode": "sync"}},
                "nodes": [],
            },
        }
        # Default publish_state makes _check_stop_signal/_check_restart_signal no-ops
        self.publish_state: dict[str, Any] = {
            "flow_id": "demo",
            "production": {"version": 1, "status": "running"},
            "gray": {"version": None, "status": "unpublished"},
        }
        self.register_calls: list[dict[str, Any]] = []
        self.heartbeat_calls: list[dict[str, Any]] = []
        self.deregister_calls: int = 0

    async def get(self, url: str) -> dict[str, Any]:
        self.calls.append(("GET", url, None))
        if "/resolve" in url:
            return self.resolve_reply
        if url.endswith("/publish"):
            return self.publish_state
        raise RuntimeError(f"Unexpected GET {url}")

    async def post(self, url: str, data: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("POST", url, data))
        if url.endswith("/instances"):
            self.register_calls.append(data)
            return {"ok": True}
        raise RuntimeError(f"Unexpected POST {url}")

    async def put(self, url: str, data: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("PUT", url, data))
        self.heartbeat_calls.append(data)
        return {"ok": True}

    async def delete(self, url: str) -> dict[str, Any]:
        self.calls.append(("DELETE", url, None))
        self.deregister_calls += 1
        return {"ok": True}


class FakeFlowRuntime:
    """Stand-in for FlowRuntime that waits a configurable amount then returns a state."""

    def __init__(self, flow: Any, duration: float = 0.05, final_state: str = "COMPLETED") -> None:
        self.flow = flow
        self.duration = duration
        self.final_state = final_state
        self.cancelled = False

    async def run(self) -> Any:
        try:
            await asyncio.sleep(self.duration)
        except asyncio.CancelledError:
            self.cancelled = True
            raise

        class _Res:
            pass

        res = _Res()
        res.state = type("S", (), {"value": self.final_state})()
        return res


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> FakeHttpBackend:
    backend = FakeHttpBackend()
    monkeypatch.setattr(mr, "_http_get", backend.get)
    monkeypatch.setattr(mr, "_http_post", backend.post)
    monkeypatch.setattr(mr, "_http_put", backend.put)
    monkeypatch.setattr(mr, "_http_delete", backend.delete)
    return backend


@pytest.fixture
def fake_runtime(monkeypatch: pytest.MonkeyPatch) -> type[FakeFlowRuntime]:
    """Replace orchestrator.FlowRuntime and loader.load_flow_from_dict."""
    import flow_engine.engine.orchestrator as orch
    import flow_engine.engine.loader as loader

    # Return the dict unchanged so FakeFlowRuntime(flow) just gets the dict
    monkeypatch.setattr(loader, "load_flow_from_dict", lambda data: data)
    monkeypatch.setattr(orch, "FlowRuntime", FakeFlowRuntime)
    return FakeFlowRuntime


# ---------------------------------------------------------------------------
# Resolve / register / deregister
# ---------------------------------------------------------------------------


async def test_run_resolves_registers_runs_deregisters(
    fake_http: FakeHttpBackend, fake_runtime: type[FakeFlowRuntime]
) -> None:
    runner = mr.ManagedRunner(
        flow_id="demo",
        channel="latest",
        instance_id="inst-1",
        heartbeat_interval=0.01,
        poll_interval=0.01,
    )
    await asyncio.wait_for(runner.run(), timeout=3.0)

    # Resolve happened once
    assert any("/resolve" in c[1] for c in fake_http.calls if c[0] == "GET")
    # Registered once
    assert len(fake_http.register_calls) == 1
    reg = fake_http.register_calls[0]
    assert reg["instance_id"] == "inst-1"
    assert reg["version"] == 1
    assert reg["channel"] == "latest"
    # Deregistered once (after run)
    assert fake_http.deregister_calls == 1


async def test_run_sends_heartbeats(
    fake_http: FakeHttpBackend, fake_runtime: type[FakeFlowRuntime]
) -> None:
    # Use a slow fake runtime so multiple heartbeats fit within the flow run
    class SlowRuntime(FakeFlowRuntime):
        def __init__(self, flow: Any) -> None:
            super().__init__(flow, duration=0.2)

    import flow_engine.engine.orchestrator as orch

    orch.FlowRuntime = SlowRuntime  # type: ignore[misc]

    runner = mr.ManagedRunner(
        flow_id="demo",
        channel="latest",
        instance_id="inst-hb",
        heartbeat_interval=0.05,
    )
    await asyncio.wait_for(runner.run(), timeout=3.0)
    assert len(fake_http.heartbeat_calls) >= 2
    for hb in fake_http.heartbeat_calls:
        assert hb["status"] == "running"


async def test_resolve_failure_raises(
    fake_http: FakeHttpBackend, fake_runtime: type[FakeFlowRuntime]
) -> None:
    async def bad_get(url: str) -> dict[str, Any]:
        raise RuntimeError("server down")

    import pytest

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mr, "_http_get", bad_get)
        runner = mr.ManagedRunner(flow_id="demo", channel="latest", instance_id="i")
        with pytest.raises(RuntimeError, match="server down"):
            await runner.run()


async def test_deregister_called_even_if_flow_fails(
    fake_http: FakeHttpBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingRuntime:
        def __init__(self, flow: Any) -> None:
            pass

        async def run(self) -> Any:
            raise RuntimeError("boom")

    import flow_engine.engine.loader as loader
    import flow_engine.engine.orchestrator as orch

    monkeypatch.setattr(loader, "load_flow_from_dict", lambda data: data)
    monkeypatch.setattr(orch, "FlowRuntime", FailingRuntime)

    runner = mr.ManagedRunner(
        flow_id="demo", channel="latest", instance_id="i-fail", heartbeat_interval=0.01
    )
    await asyncio.wait_for(runner.run(), timeout=3.0)
    # Even though the flow raised, deregister happened
    assert fake_http.deregister_calls == 1


# ---------------------------------------------------------------------------
# Stop handling
# ---------------------------------------------------------------------------


async def test_request_stop_triggers_termination(
    fake_http: FakeHttpBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Long-running flow
    class LongRuntime(FakeFlowRuntime):
        def __init__(self, flow: Any) -> None:
            super().__init__(flow, duration=5.0)

    import flow_engine.engine.loader as loader
    import flow_engine.engine.orchestrator as orch

    monkeypatch.setattr(loader, "load_flow_from_dict", lambda data: data)
    monkeypatch.setattr(orch, "FlowRuntime", LongRuntime)

    runner = mr.ManagedRunner(
        flow_id="demo",
        channel="latest",
        instance_id="i-stop",
        heartbeat_interval=0.05,
        graceful_timeout_sec=0.1,
    )

    async def stop_soon() -> None:
        await asyncio.sleep(0.1)
        runner.request_stop()

    asyncio.create_task(stop_soon())
    # With force-cancel path, the long flow is cancelled and the runner exits
    await asyncio.wait_for(runner.run(), timeout=3.0)
    assert fake_http.deregister_calls >= 1


async def test_graceful_shutdown_waits_for_flow(
    fake_http: FakeHttpBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    import flow_engine.engine.loader as loader
    import flow_engine.engine.orchestrator as orch

    # Flow that naturally finishes shortly after stop signal
    class QuickRuntime(FakeFlowRuntime):
        def __init__(self, flow: Any) -> None:
            super().__init__(flow, duration=0.15)

    monkeypatch.setattr(loader, "load_flow_from_dict", lambda data: data)
    monkeypatch.setattr(orch, "FlowRuntime", QuickRuntime)

    runner = mr.ManagedRunner(
        flow_id="demo",
        channel="latest",
        instance_id="i-graceful",
        heartbeat_interval=0.02,
        graceful_timeout_sec=5.0,
    )

    async def stop_soon() -> None:
        await asyncio.sleep(0.05)
        runner.request_stop()

    asyncio.create_task(stop_soon())
    await asyncio.wait_for(runner.run(), timeout=3.0)
    # Graceful timeout was high enough for flow to finish naturally
    assert fake_http.deregister_calls == 1


# ---------------------------------------------------------------------------
# _check_stop_signal / _check_restart_signal logic
# ---------------------------------------------------------------------------


async def test_check_stop_signal_true_when_channel_unpublished(
    fake_http: FakeHttpBackend,
) -> None:
    fake_http.publish_state = {
        "production": {"version": None, "status": "unpublished"},
        "gray": {"version": None, "status": "unpublished"},
    }
    runner = mr.ManagedRunner(flow_id="demo", channel="production", instance_id="i")
    assert await runner._check_stop_signal() is True


async def test_check_stop_signal_false_when_running(
    fake_http: FakeHttpBackend,
) -> None:
    fake_http.publish_state = {
        "production": {"version": 1, "status": "running"},
        "gray": {"version": None, "status": "unpublished"},
    }
    runner = mr.ManagedRunner(flow_id="demo", channel="production", instance_id="i")
    assert await runner._check_stop_signal() is False


async def test_check_stop_signal_false_for_non_channel_mode(
    fake_http: FakeHttpBackend,
) -> None:
    """For channels like 'latest', 'v3', or 'draft' the stop-signal check is
    inapplicable and should return False (these are not tied to publish state)."""
    runner = mr.ManagedRunner(flow_id="demo", channel="latest", instance_id="i")
    assert await runner._check_stop_signal() is False


async def test_check_restart_signal_detects_new_publish(
    fake_http: FakeHttpBackend,
) -> None:
    fake_http.publish_state = {
        "production": {"version": 2, "status": "publishing"},
        "gray": {"version": None, "status": "unpublished"},
    }
    runner = mr.ManagedRunner(flow_id="demo", channel="production", instance_id="i")
    runner._current_version = 1
    should_restart, new_ver = await runner._check_restart_signal()
    assert should_restart is True
    assert new_ver == 2


async def test_check_restart_signal_ignores_same_version(
    fake_http: FakeHttpBackend,
) -> None:
    fake_http.publish_state = {
        "production": {"version": 1, "status": "publishing"},
        "gray": {"version": None, "status": "unpublished"},
    }
    runner = mr.ManagedRunner(flow_id="demo", channel="production", instance_id="i")
    runner._current_version = 1
    should_restart, _ = await runner._check_restart_signal()
    assert should_restart is False


async def test_heartbeat_swallows_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def bad_put(url: str, data: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("heartbeat api down")

    monkeypatch.setattr(mr, "_http_put", bad_put)
    runner = mr.ManagedRunner(flow_id="demo", channel="latest", instance_id="i")
    # Must not raise
    await runner._heartbeat("running")


async def test_deregister_swallows_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def bad_delete(url: str) -> dict[str, Any]:
        raise RuntimeError("delete failed")

    monkeypatch.setattr(mr, "_http_delete", bad_delete)
    runner = mr.ManagedRunner(flow_id="demo", channel="latest", instance_id="i")
    await runner._deregister()  # must not raise


# ---------------------------------------------------------------------------
# run_managed convenience wrapper
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Restart flow (server-driven and explicit)
# ---------------------------------------------------------------------------


async def test_request_restart_triggers_second_iteration(
    fake_http: FakeHttpBackend, fake_runtime: type[FakeFlowRuntime], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calling ``request_restart`` during the first run should cause a second
    register/deregister cycle before exit."""

    class SlowRuntime(FakeFlowRuntime):
        def __init__(self, flow: Any) -> None:
            super().__init__(flow, duration=0.3)

    import flow_engine.engine.orchestrator as orch

    monkeypatch.setattr(orch, "FlowRuntime", SlowRuntime)

    runner = mr.ManagedRunner(
        flow_id="demo",
        channel="latest",
        instance_id="i-restart",
        heartbeat_interval=0.05,
        graceful_timeout_sec=2.0,
    )

    async def restart_then_shutdown() -> None:
        await asyncio.sleep(0.05)
        runner.request_restart()
        # After the second iteration resolves & registers, shut down
        await asyncio.sleep(0.5)
        runner.request_stop(shutdown=True)

    asyncio.create_task(restart_then_shutdown())
    await asyncio.wait_for(runner.run(), timeout=5.0)

    # Two register/deregister cycles
    assert len(fake_http.register_calls) >= 2
    assert fake_http.deregister_calls >= 2


async def test_channel_runner_restarts_on_new_publish(
    fake_http: FakeHttpBackend, fake_runtime: type[FakeFlowRuntime], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A runner bound to 'production' should detect a new publish via polling
    and restart automatically."""

    class SlowRuntime(FakeFlowRuntime):
        def __init__(self, flow: Any) -> None:
            super().__init__(flow, duration=5.0)

    import flow_engine.engine.orchestrator as orch

    monkeypatch.setattr(orch, "FlowRuntime", SlowRuntime)

    # Initial state: v1 running
    fake_http.publish_state = {
        "production": {"version": 1, "status": "running"},
        "gray": {"version": None, "status": "unpublished"},
    }

    call_count = {"n": 0}
    original_get = fake_http.get

    async def scripted_get(url: str) -> dict[str, Any]:
        # After a few polls, flip publish_state to v2 publishing
        call_count["n"] += 1
        if "/publish" in url and call_count["n"] > 2:
            fake_http.publish_state = {
                "production": {"version": 2, "status": "publishing"},
                "gray": {"version": None, "status": "unpublished"},
            }
        return await original_get(url)

    monkeypatch.setattr(mr, "_http_get", scripted_get)

    # Also update resolve_reply so the restart iteration sees v2
    def set_v2() -> None:
        fake_http.resolve_reply = {
            "version": 2,
            "definition": fake_http.resolve_reply["definition"],
        }

    runner = mr.ManagedRunner(
        flow_id="demo",
        channel="production",
        instance_id="i-prod",
        heartbeat_interval=0.05,
        poll_interval=0.05,
        graceful_timeout_sec=0.5,
    )

    async def shutdown_later() -> None:
        await asyncio.sleep(0.4)
        set_v2()
        await asyncio.sleep(0.4)
        # After the second iteration starts, force shutdown so the test ends
        runner.request_stop(shutdown=True)

    asyncio.create_task(shutdown_later())
    await asyncio.wait_for(runner.run(), timeout=5.0)

    assert len(fake_http.register_calls) >= 2


async def test_channel_runner_enters_standby_on_stop_signal(
    fake_http: FakeHttpBackend, fake_runtime: type[FakeFlowRuntime], monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the server marks the channel unpublished, the runner stops the
    current flow and enters standby. An external shutdown breaks standby."""

    class SlowRuntime(FakeFlowRuntime):
        def __init__(self, flow: Any) -> None:
            super().__init__(flow, duration=5.0)

    import flow_engine.engine.orchestrator as orch

    monkeypatch.setattr(orch, "FlowRuntime", SlowRuntime)

    fake_http.publish_state = {
        "production": {"version": 1, "status": "running"},
        "gray": {"version": None, "status": "unpublished"},
    }

    runner = mr.ManagedRunner(
        flow_id="demo",
        channel="production",
        instance_id="i-standby",
        heartbeat_interval=0.05,
        poll_interval=0.05,
        graceful_timeout_sec=0.5,
    )

    async def orchestrate() -> None:
        # After some time, mark the channel unpublished – runner should stop
        await asyncio.sleep(0.3)
        fake_http.publish_state = {
            "production": {"version": None, "status": "unpublished"},
            "gray": {"version": None, "status": "unpublished"},
        }
        # Runner is now in standby – shutdown to exit the test
        await asyncio.sleep(0.5)
        runner.request_stop(shutdown=True)

    asyncio.create_task(orchestrate())
    await asyncio.wait_for(runner.run(), timeout=5.0)
    assert fake_http.deregister_calls == 1


async def test_run_managed_convenience(
    fake_http: FakeHttpBackend, fake_runtime: type[FakeFlowRuntime]
) -> None:
    # heartbeat_interval defaults to 10s – we rely on the flow completing almost
    # instantly so at most one heartbeat fires
    await asyncio.wait_for(
        mr.run_managed(flow_id="demo", channel="latest", instance_id="i-conv"),
        timeout=3.0,
    )
    assert fake_http.deregister_calls == 1
    assert len(fake_http.register_calls) == 1
