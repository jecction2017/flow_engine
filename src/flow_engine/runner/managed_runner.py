"""Managed flow runner: resolves version by channel, registers instance, sends heartbeats,
and listens for stop / restart signals from the Flow Engine API.

Usage example::

    import asyncio
    from flow_engine.runner.managed_runner import run_managed

    asyncio.run(run_managed("my_flow", channel="production"))

Channel values
--------------
* ``"production"`` – use the currently published production version
* ``"gray"``       – use the currently published gray/canary version
* ``"latest"``     – most recent committed version
* ``"draft"``      – current draft
* ``"v3"`` / ``3`` – specific version number

Stop behaviour
--------------
On receiving a stop signal the runner:
1. Cancels the flow gracefully (sets a cancel flag and waits for current node to finish).
2. If the flow does not finish within ``graceful_timeout_sec``, forces cancellation.
3. Deregisters the instance and exits.
4. If a new publish event arrives while in standby mode, the runner auto-restarts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_API = os.environ.get("FLOW_ENGINE_API_BASE", "http://127.0.0.1:8000")
_HEARTBEAT_INTERVAL = float(os.environ.get("FLOW_ENGINE_HEARTBEAT_INTERVAL", "10"))
_GRACEFUL_TIMEOUT = float(os.environ.get("FLOW_ENGINE_GRACEFUL_TIMEOUT", "30"))
_POLL_INTERVAL = float(os.environ.get("FLOW_ENGINE_POLL_INTERVAL", "5"))


# ---------------------------------------------------------------------------
# HTTP helpers (uses httpx if available, otherwise urllib)
# ---------------------------------------------------------------------------


async def _http_get(url: str) -> dict[str, Any]:
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
    except ImportError:
        import urllib.request

        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
            return json.loads(resp.read())


async def _http_post(url: str, data: dict[str, Any]) -> dict[str, Any]:
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=data)
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
    except ImportError:
        import urllib.request

        req = urllib.request.Request(  # noqa: S310
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return json.loads(resp.read())


async def _http_put(url: str, data: dict[str, Any]) -> dict[str, Any]:
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.put(url, json=data)
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
    except ImportError:
        import urllib.request

        req = urllib.request.Request(  # noqa: S310
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return json.loads(resp.read())


async def _http_delete(url: str) -> dict[str, Any]:
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.delete(url)
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
    except ImportError:
        import urllib.request

        req = urllib.request.Request(url, method="DELETE")  # noqa: S310
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return json.loads(resp.read())


# ---------------------------------------------------------------------------
# ManagedRunner
# ---------------------------------------------------------------------------


class ManagedRunner:
    """Lifecycle manager for a single flow execution with publish integration.

    Event semantics
    ----------------
    * ``_stop_event``      – signals "stop the currently running flow" (causes
      the current execution to cancel gracefully and then force-terminate)
    * ``_restart_event``   – signals "after stopping, restart with the newly
      published version" (the outer ``run()`` loop checks this flag and decides
      whether to loop or exit)
    * ``_shutdown_event``  – signals "exit immediately without restart" (used
      by external callers / signal handlers)
    """

    def __init__(
        self,
        flow_id: str,
        channel: str = "latest",
        instance_id: str | None = None,
        api_base: str = _DEFAULT_API,
        graceful_timeout_sec: float = _GRACEFUL_TIMEOUT,
        heartbeat_interval: float = _HEARTBEAT_INTERVAL,
        poll_interval: float = _POLL_INTERVAL,
        initial_context: dict[str, Any] | None = None,
    ) -> None:
        self.flow_id = flow_id
        self.channel = channel
        self.instance_id = instance_id or str(uuid.uuid4())
        self.api_base = api_base.rstrip("/")
        self.graceful_timeout_sec = graceful_timeout_sec
        self.heartbeat_interval = heartbeat_interval
        self.poll_interval = poll_interval
        self.initial_context = initial_context or {}

        self._stop_event = asyncio.Event()
        self._restart_event = asyncio.Event()
        self._shutdown_event = asyncio.Event()
        self._current_version: int | None = None
        self._runtime: Any = None  # FlowRuntime, imported lazily

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    async def _resolve(self) -> tuple[int | None, dict[str, Any]]:
        url = f"{self.api_base}/api/flows/{self.flow_id}/resolve?channel={self.channel}"
        resp = await _http_get(url)
        return resp.get("version"), resp["definition"]

    async def _register(self, version: int | None) -> None:
        url = f"{self.api_base}/api/flows/{self.flow_id}/instances"
        payload: dict[str, Any] = {
            "instance_id": self.instance_id,
            "version": version or 0,
            "channel": self.channel,
            "pid": os.getpid(),
            "host": socket.gethostname(),
        }
        await _http_post(url, payload)
        logger.info("Registered instance %s (flow=%s, channel=%s, v%s)", self.instance_id, self.flow_id, self.channel, version)

    async def _heartbeat(self, status: str = "running") -> None:
        url = f"{self.api_base}/api/flows/{self.flow_id}/instances/{self.instance_id}"
        try:
            await _http_put(url, {"status": status})
        except Exception as e:  # noqa: BLE001
            logger.warning("Heartbeat failed: %s", e)

    async def _deregister(self) -> None:
        url = f"{self.api_base}/api/flows/{self.flow_id}/instances/{self.instance_id}"
        try:
            await _http_delete(url)
        except Exception as e:  # noqa: BLE001
            logger.warning("Deregister failed: %s", e)

    async def _check_stop_signal(self) -> bool:
        """Poll publish state; return True if this channel has been stopped.

        Only meaningful for runners bound to the ``production`` / ``gray``
        channels; for ``latest`` / ``v<N>`` / ``draft`` runners there is no
        publish channel to observe and this always returns False.
        """
        if self.channel not in ("production", "gray"):
            return False
        try:
            url = f"{self.api_base}/api/flows/{self.flow_id}/publish"
            state = await _http_get(url)
            ch = state.get(self.channel)
            if not isinstance(ch, dict):
                return False
            return ch.get("status") in ("unpublished", "stopped", "failed")
        except Exception:  # noqa: BLE001
            return False

    async def _check_restart_signal(self) -> tuple[bool, int | None]:
        """Poll publish state; return ``(should_restart, new_version)`` if a
        new version was published to this channel.

        Only meaningful for runners bound to the ``production`` / ``gray``
        channels.
        """
        if self.channel not in ("production", "gray"):
            return False, None
        try:
            url = f"{self.api_base}/api/flows/{self.flow_id}/publish"
            state = await _http_get(url)
            ch = state.get(self.channel)
            if not isinstance(ch, dict):
                return False, None
            new_ver = ch.get("version")
            if (
                ch.get("status") in ("publishing", "running")
                and new_ver is not None
                and new_ver != self._current_version
            ):
                return True, new_ver
        except Exception:  # noqa: BLE001
            pass
        return False, None

    # ------------------------------------------------------------------
    # Core run loop
    # ------------------------------------------------------------------

    async def _run_once(self, flow_data: dict[str, Any], version: int | None) -> str:
        """Load and run the flow, returning final state string."""
        from flow_engine.engine.loader import load_flow_from_dict
        from flow_engine.engine.orchestrator import FlowRuntime

        flow = load_flow_from_dict(flow_data)
        if self.initial_context:
            merged = dict(flow.initial_context or {})
            merged.update(self.initial_context)
            flow.initial_context = merged

        self._runtime = FlowRuntime(flow)
        rt = self._runtime

        async def _run() -> str:
            res = await rt.run()
            return res.state.value

        run_task = asyncio.create_task(_run())

        # Heartbeat loop while running
        async def _heartbeats() -> None:
            while not run_task.done():
                await self._heartbeat("running")
                await asyncio.sleep(self.heartbeat_interval)

        hb_task = asyncio.create_task(_heartbeats())

        try:
            done, _ = await asyncio.wait(
                [run_task, asyncio.create_task(self._stop_event.wait())],
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass

        if self._stop_event.is_set() and not run_task.done():
            logger.info("Stop signal received – graceful shutdown (timeout=%ss)", self.graceful_timeout_sec)
            try:
                await asyncio.wait_for(run_task, timeout=self.graceful_timeout_sec)
            except asyncio.TimeoutError:
                logger.warning("Graceful timeout expired – forcing cancellation")
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
            return "TERMINATED"

        try:
            return await run_task
        except Exception as e:  # noqa: BLE001
            logger.error("Flow run failed: %s", e)
            return "FAILED"

    async def _poll_publish_state(self) -> None:
        """Background task that watches publish state and signals stop/restart.

        Runs only for runners bound to ``production`` / ``gray`` channels.
        Terminates itself once either event is set.
        """
        if self.channel not in ("production", "gray"):
            return
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                return
            if self._stop_event.is_set():
                return
            if await self._check_stop_signal():
                logger.info("Stop signal detected on channel '%s'", self.channel)
                self._stop_event.set()
                return
            should_restart, new_ver = await self._check_restart_signal()
            if should_restart:
                logger.info(
                    "New publish detected on channel '%s' (v%s) – will restart",
                    self.channel,
                    new_ver,
                )
                self._restart_event.set()
                self._stop_event.set()
                return

    async def _standby_wait(self) -> bool:
        """Wait in standby for a restart signal or explicit shutdown.

        Only invoked for ``production`` / ``gray`` channels.
        Returns True if a restart was requested, False if shutdown was
        requested (or the standby window elapsed).
        """
        if self.channel not in ("production", "gray"):
            return False
        deadline = time.time() + 3600  # max 1 hour standby
        while time.time() < deadline:
            if self._shutdown_event.is_set():
                return False
            if self._restart_event.is_set():
                return True
            should_restart, _ = await self._check_restart_signal()
            if should_restart:
                return True
            try:
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                return False
        return False

    async def run(self) -> None:
        """Main entry point: resolve → register → run → heartbeat → handle stop/restart.

        Loop invariants:
        * Each iteration resolves, registers, runs, then deregisters exactly once.
        * After the current execution ends the loop decides whether to restart:
          - ``_shutdown_event`` set      → exit immediately (user-requested).
          - ``_restart_event`` set       → resolve & run again right away.
          - ``production/gray`` channel  → enter ``_standby_wait`` waiting for
            a new publish event; exit if standby window elapses.
          - Any other case               → exit (flow completed naturally or
            was stopped by an external caller via ``request_stop``).
        """
        while True:
            self._stop_event.clear()
            self._restart_event.clear()

            try:
                version, flow_data = await self._resolve()
            except Exception as e:  # noqa: BLE001
                logger.error("Failed to resolve flow '%s' channel '%s': %s", self.flow_id, self.channel, e)
                raise

            self._current_version = version
            await self._register(version)

            poll_task = asyncio.create_task(self._poll_publish_state())
            try:
                final_state = await self._run_once(flow_data, version)
                logger.info("Flow '%s' finished with state=%s", self.flow_id, final_state)
            finally:
                poll_task.cancel()
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass
                await self._deregister()

            # Decide: exit, loop immediately, or enter standby
            if self._shutdown_event.is_set():
                logger.info("Shutdown requested – exiting")
                break
            if self._restart_event.is_set():
                logger.info("Restart requested – resolving next version")
                continue
            if self.channel in ("production", "gray") and self._stop_event.is_set():
                logger.info("Instance %s in standby – waiting for new publish event", self.instance_id)
                if await self._standby_wait():
                    logger.info("New publish received – restarting")
                    continue
            break

    def request_stop(self, *, shutdown: bool = True) -> None:
        """Signal the runner to stop the currently running flow.

        When ``shutdown=True`` (default) the runner exits after the current
        execution ends. When ``shutdown=False`` the runner enters standby and
        will restart automatically on a new publish signal (valid only for
        production/gray channels).
        """
        self._stop_event.set()
        if shutdown:
            self._shutdown_event.set()

    def request_restart(self) -> None:
        """Signal the runner to stop the current flow and restart."""
        self._restart_event.set()
        self._stop_event.set()


# ---------------------------------------------------------------------------
# Convenience top-level function
# ---------------------------------------------------------------------------


async def run_managed(
    flow_id: str,
    channel: str = "latest",
    instance_id: str | None = None,
    api_base: str = _DEFAULT_API,
    initial_context: dict[str, Any] | None = None,
    graceful_timeout_sec: float = _GRACEFUL_TIMEOUT,
) -> None:
    """Run a flow with full publish integration.

    Parameters
    ----------
    flow_id:
        The flow identifier.
    channel:
        Version resolution channel: ``"production"``, ``"gray"``, ``"latest"``,
        ``"draft"``, ``"v3"`` or a plain integer string like ``"3"``.
    instance_id:
        Optional explicit instance UUID; auto-generated if omitted.
    api_base:
        Flow Engine API base URL (default ``http://127.0.0.1:8000``).
    initial_context:
        Extra context merged on top of the flow's ``initial_context``.
    graceful_timeout_sec:
        Seconds to wait for graceful shutdown before forcing cancellation.
    """
    runner = ManagedRunner(
        flow_id=flow_id,
        channel=channel,
        instance_id=instance_id,
        api_base=api_base,
        initial_context=initial_context,
        graceful_timeout_sec=graceful_timeout_sec,
    )
    await runner.run()
