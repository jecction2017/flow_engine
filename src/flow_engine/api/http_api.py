"""FastAPI HTTP service: versioned flow CRUD, publish management, instance tracking, SSE."""

from __future__ import annotations

import asyncio
import json
import time
import traceback
from typing import Any, AsyncGenerator

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from flow_engine.engine.compiler import compile_flow
from flow_engine.engine.event_bus import get_event_bus, make_event
from flow_engine.engine.loader import load_flow_from_dict
from flow_engine.engine.models import ExecutionStrategy, FlowDefinition, NodeState, StrategyMode
from flow_engine.engine.orchestrator import FlowRuntime
from flow_engine.engine.publish_models import (
    ChannelState,
    FlowInstance,
    FlowPublishState,
    PublishStatus,
)
from flow_engine.engine.starlark_glue import debug_task_script
from flow_engine.lookup.lookup_import import rows_from_bytes
from flow_engine.lookup.lookup_service import merge_imported_rows, put_table
from flow_engine.lookup.lookup_store import LookupStoreError, get_lookup_store, validate_lookup_namespace
from flow_engine.starlark_sdk.paths import user_scripts_root
from flow_engine.starlark_sdk.python_builtin_impl import user_script_list
from flow_engine.starlark_sdk.registry_data import load_registry
from flow_engine.starlark_sdk.runtime import runtime_stats, warmup_runtime
from flow_engine.starlark_sdk.uri_resolve import resolve_internal_script_file, resolve_user_script_file
from flow_engine.stores import data_dict
from flow_engine.stores.dict_store import DataDictError
from flow_engine.stores.version_store import FlowVersionRegistry, validate_flow_id

# ---------------------------------------------------------------------------
# Global registry (replaces old FlowYamlStore singleton)
# ---------------------------------------------------------------------------

registry = FlowVersionRegistry()

# ---------------------------------------------------------------------------
# Request / response body models
# ---------------------------------------------------------------------------


class CreateFlowBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    name: str | None = None


class DebugNodeBody(BaseModel):
    script: str
    initial_context: dict[str, Any] = Field(default_factory=dict)


class PutUserScriptBody(BaseModel):
    content: str = Field(..., description="Starlark source")


class PutDictRawBody(BaseModel):
    content: str = Field(..., description="Full dictionary.yaml text")


class PutDictSubtreeBody(BaseModel):
    yaml: str = Field(..., description="YAML fragment for this subtree or root")


class PutLookupBody(BaseModel):
    fields: list[str] | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)


class StarlarkWarmupBody(BaseModel):
    module_ids: list[str] = Field(default_factory=list)
    script_samples: list[str] = Field(default_factory=list)


class RunFlowBody(BaseModel):
    initial_context: dict[str, Any] | None = None
    merge: bool = True
    timeout_sec: float = Field(default=30.0, ge=0.1, le=600.0)


class CommitVersionBody(BaseModel):
    description: str | None = None
    data: dict[str, Any] | None = None


class PublishBody(BaseModel):
    version: int = Field(..., ge=1)
    channel: str = Field(..., pattern="^(production|gray)$")


class RegisterInstanceBody(BaseModel):
    instance_id: str
    version: int
    channel: str = "latest"
    pid: int | None = None
    host: str | None = None


class HeartbeatBody(BaseModel):
    status: str = "running"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PUBLISH_TIMEOUT = float(__import__("os").environ.get("FLOW_ENGINE_PUBLISH_TIMEOUT", "60"))


def _resolve_flow_id(flow_id: str) -> str:
    try:
        return validate_flow_id(flow_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _require_flow(flow_id: str) -> None:
    if not registry.exists(flow_id):
        raise HTTPException(status_code=404, detail="Flow not found")


def _load_flow_data(flow_id: str) -> dict[str, Any]:
    """Return draft if exists, otherwise latest committed version."""
    vs = registry.version_store(flow_id)
    if vs.has_draft():
        return vs.read_draft()
    meta = vs.read_meta()
    if meta.latest_version > 0:
        return vs.read_version(meta.latest_version)
    raise HTTPException(status_code=404, detail="Flow has no draft or committed versions")


def _channel_state(state: FlowPublishState, channel: str) -> ChannelState:
    return state.production if channel == "production" else state.gray


def _set_channel(state: FlowPublishState, channel: str, ch: ChannelState) -> None:
    if channel == "production":
        state.production = ch
    else:
        state.gray = ch


def _apply_publish_timeouts(state: FlowPublishState) -> tuple[FlowPublishState, bool]:
    """Lazily demote any ``PUBLISHING`` channel that has exceeded the timeout
    to ``FAILED``. Returns ``(state, mutated)``.

    This is called on every publish-state read so the state machine converges
    even if a background task didn't run (e.g. TestClient with a short-lived
    event loop, or server restart before the timeout fired).
    """
    mutated = False
    now = time.time()
    for ch_name in ("production", "gray"):
        ch = _channel_state(state, ch_name)
        if ch.status == PublishStatus.PUBLISHING and ch.published_at is not None:
            if now - ch.published_at > _PUBLISH_TIMEOUT:
                ch.status = PublishStatus.FAILED
                _set_channel(state, ch_name, ch)
                mutated = True
    return state, mutated


def _read_publish_state(flow_id: str) -> FlowPublishState:
    """Read publish state + apply lazy timeout check (persists if demoted)."""
    ps = registry.publish_store(flow_id)
    state = ps.read()
    state, mutated = _apply_publish_timeouts(state)
    if mutated:
        ps.write(state)
    return state


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(title="Flow Engine API", version="0.3.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:4173",
            "http://localhost:4173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -----------------------------------------------------------------------
    # Health
    # -----------------------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # -----------------------------------------------------------------------
    # Flow list / CRUD  (backward-compatible surface)
    # -----------------------------------------------------------------------

    @app.get("/api/flows")
    def list_flows() -> dict[str, Any]:
        flows = registry.list_flows()
        return {
            "flows": flows,
            "flows_dir": str(registry.directory),
        }

    @app.get("/api/flows/{flow_id}")
    def get_flow(flow_id: str) -> dict[str, Any]:
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)
        return _load_flow_data(flow_id)

    @app.put("/api/flows/{flow_id}")
    def put_flow(flow_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """Save flow as draft (backward-compatible with old save-to-server)."""
        _resolve_flow_id(flow_id)
        try:
            compiled = compile_flow(FlowDefinition.model_validate(body))
            data = compiled.model_dump(mode="json", exclude_none=True)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Validation failed: {e}") from e
        if not registry.exists(flow_id):
            registry.create(flow_id, data)
        else:
            registry.version_store(flow_id).save_draft(data)
        return {"ok": True, "id": flow_id}

    @app.post("/api/flows")
    def create_flow(body: CreateFlowBody) -> dict[str, Any]:
        fid = _resolve_flow_id(body.id)
        if registry.exists(fid):
            raise HTTPException(status_code=409, detail="Flow id already exists")
        name = body.name or fid
        minimal = FlowDefinition(
            name=name,
            version="1.0.0",
            strategies={"default_sync": ExecutionStrategy(name="default_sync", mode=StrategyMode.SYNC)},
            nodes=[],
        )
        compiled = compile_flow(minimal)
        registry.create(fid, compiled.model_dump(mode="json", exclude_none=True))
        return {"ok": True, "id": fid}

    @app.delete("/api/flows/{flow_id}")
    def delete_flow(flow_id: str) -> dict[str, Any]:
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)
        registry.delete(flow_id)
        return {"ok": True}

    # -----------------------------------------------------------------------
    # Version management
    # -----------------------------------------------------------------------

    @app.get("/api/flows/{flow_id}/versions")
    def list_versions(flow_id: str) -> dict[str, Any]:
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)
        vs = registry.version_store(flow_id)
        meta = vs.read_meta()
        return {
            "flow_id": flow_id,
            "latest_version": meta.latest_version,
            "has_draft": meta.has_draft,
            "versions": [v.model_dump() for v in meta.versions],
        }

    @app.get("/api/flows/{flow_id}/versions/{version_num}")
    def get_version(flow_id: str, version_num: int) -> dict[str, Any]:
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)
        try:
            data = registry.version_store(flow_id).read_version(version_num)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Version v{version_num} not found") from None
        return data

    @app.get("/api/flows/{flow_id}/draft")
    def get_draft(flow_id: str) -> dict[str, Any]:
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)
        vs = registry.version_store(flow_id)
        if not vs.has_draft():
            raise HTTPException(status_code=404, detail="No draft exists")
        return vs.read_draft()

    @app.put("/api/flows/{flow_id}/draft")
    def put_draft(flow_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        _resolve_flow_id(flow_id)
        try:
            compiled = compile_flow(FlowDefinition.model_validate(body))
            data = compiled.model_dump(mode="json", exclude_none=True)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Validation failed: {e}") from e
        if not registry.exists(flow_id):
            registry.create(flow_id, data)
        else:
            registry.version_store(flow_id).save_draft(data)
        return {"ok": True, "id": flow_id}

    @app.post("/api/flows/{flow_id}/versions")
    def commit_version(flow_id: str, body: CommitVersionBody = Body(default_factory=CommitVersionBody)) -> dict[str, Any]:
        """Commit draft (or supplied data) as a new immutable version."""
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)
        vs = registry.version_store(flow_id)
        data = body.data
        if data is not None:
            try:
                compiled = compile_flow(FlowDefinition.model_validate(data))
                data = compiled.model_dump(mode="json", exclude_none=True)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(status_code=400, detail=f"Validation failed: {e}") from e
        else:
            if not vs.has_draft():
                raise HTTPException(status_code=400, detail="No draft to commit; provide data in request body")
            raw = vs.read_draft()
            try:
                compiled = compile_flow(FlowDefinition.model_validate(raw))
                data = compiled.model_dump(mode="json", exclude_none=True)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(status_code=400, detail=f"Draft validation failed: {e}") from e
        new_ver = vs.commit_version(data, description=body.description)
        return {"ok": True, "flow_id": flow_id, "version": new_ver}

    # -----------------------------------------------------------------------
    # Publish management
    # -----------------------------------------------------------------------

    @app.get("/api/flows/{flow_id}/publish")
    def get_publish_state(flow_id: str) -> dict[str, Any]:
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)
        return _read_publish_state(flow_id).model_dump()

    @app.post("/api/flows/{flow_id}/publish")
    async def publish_version(flow_id: str, body: PublishBody) -> dict[str, Any]:
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)
        vs = registry.version_store(flow_id)
        ps = registry.publish_store(flow_id)

        # Verify version exists
        try:
            vs.read_version(body.version)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Version v{body.version} not found") from None

        # Apply lazy timeout check before evaluating conflict: if the channel
        # is stuck in PUBLISHING past the timeout it auto-demotes to FAILED,
        # which frees the channel for a new publish.
        state = _read_publish_state(flow_id)
        ch = _channel_state(state, body.channel)

        # Enforce: must stop existing active channel before publishing new version
        if ch.status in (PublishStatus.PUBLISHING, PublishStatus.RUNNING):
            raise HTTPException(
                status_code=409,
                detail=f"Channel '{body.channel}' is already {ch.status.value}. Stop it first.",
            )

        new_ch = ChannelState(
            version=body.version,
            status=PublishStatus.PUBLISHING,
            published_at=time.time(),
        )
        _set_channel(state, body.channel, new_ch)
        ps.write(state)

        bus = get_event_bus()
        await bus.publish(make_event(
            "flow.published",
            flow_id,
            {"channel": body.channel, "version": body.version},
        ))
        await bus.publish(make_event("publish.state_changed", flow_id, state.model_dump()))

        # Background task: auto-fail after timeout if no instance registers
        async def _timeout_watcher() -> None:
            await asyncio.sleep(_PUBLISH_TIMEOUT)
            current = ps.read()
            cur_ch = _channel_state(current, body.channel)
            if cur_ch.status == PublishStatus.PUBLISHING and cur_ch.version == body.version:
                cur_ch.status = PublishStatus.FAILED
                _set_channel(current, body.channel, cur_ch)
                ps.write(current)
                await bus.publish(make_event("publish.state_changed", flow_id, current.model_dump()))

        asyncio.create_task(_timeout_watcher())

        return {"ok": True, "flow_id": flow_id, "channel": body.channel, "version": body.version, "status": "publishing"}

    @app.delete("/api/flows/{flow_id}/publish/{channel}")
    async def stop_publish(flow_id: str, channel: str) -> dict[str, Any]:
        if channel not in ("production", "gray"):
            raise HTTPException(status_code=400, detail="channel must be 'production' or 'gray'")
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)

        ps = registry.publish_store(flow_id)
        state = ps.read()
        ch = _channel_state(state, channel)
        stopped_version = ch.version

        new_ch = ChannelState(status=PublishStatus.UNPUBLISHED, stopped_at=time.time())
        _set_channel(state, channel, new_ch)
        ps.write(state)

        bus = get_event_bus()
        await bus.publish(make_event(
            "flow.stopped",
            flow_id,
            {"channel": channel, "version": stopped_version},
        ))
        await bus.publish(make_event("publish.state_changed", flow_id, state.model_dump()))

        return {"ok": True, "flow_id": flow_id, "channel": channel}

    @app.get("/api/flows/{flow_id}/resolve")
    def resolve_channel(flow_id: str, channel: str = Query(default="latest")) -> dict[str, Any]:
        """Resolve channel/version string to a concrete flow definition (used by runners)."""
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)
        try:
            version_num, data = registry.resolve_version_data(flow_id, channel)
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return {"flow_id": flow_id, "channel": channel, "version": version_num, "definition": data}

    # -----------------------------------------------------------------------
    # Instance management
    # -----------------------------------------------------------------------

    @app.get("/api/flows/{flow_id}/instances")
    def list_instances(flow_id: str) -> dict[str, Any]:
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)
        inst_store = registry.instance_store(flow_id)
        return {"flow_id": flow_id, "instances": [i.model_dump() for i in inst_store.list_instances()]}

    @app.post("/api/flows/{flow_id}/instances")
    async def register_instance(flow_id: str, body: RegisterInstanceBody) -> dict[str, Any]:
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)
        inst = FlowInstance(
            instance_id=body.instance_id,
            flow_id=flow_id,
            version=body.version,
            channel=body.channel,
            started_at=time.time(),
            last_heartbeat=time.time(),
            status="running",
            pid=body.pid,
            host=body.host,
        )
        registry.instance_store(flow_id).register(inst)

        # Transition publish state → RUNNING if a channel is waiting for this
        # version. Also resurrect FAILED back to RUNNING when a late instance
        # arrives (e.g. after the lazy timeout check demoted it).
        ps = registry.publish_store(flow_id)
        state = ps.read()
        changed = False
        for ch_name in ("production", "gray"):
            ch = _channel_state(state, ch_name)
            if ch.version == body.version and ch.status in (
                PublishStatus.PUBLISHING,
                PublishStatus.FAILED,
            ):
                ch.status = PublishStatus.RUNNING
                _set_channel(state, ch_name, ch)
                changed = True
        if changed:
            ps.write(state)

        bus = get_event_bus()
        await bus.publish(make_event("instance.registered", flow_id, inst.model_dump()))
        if changed:
            await bus.publish(make_event("publish.state_changed", flow_id, state.model_dump()))

        return {"ok": True, "instance_id": body.instance_id}

    @app.put("/api/flows/{flow_id}/instances/{instance_id}")
    async def heartbeat_instance(flow_id: str, instance_id: str, body: HeartbeatBody = Body(default_factory=HeartbeatBody)) -> dict[str, Any]:
        _resolve_flow_id(flow_id)
        inst_store = registry.instance_store(flow_id)
        inst = inst_store.heartbeat(instance_id)
        if inst is None:
            raise HTTPException(status_code=404, detail="Instance not found")
        if body.status != inst.status:
            inst_store.update_status(instance_id, body.status)
        bus = get_event_bus()
        await bus.publish(make_event("instance.heartbeat", flow_id, {"instance_id": instance_id, "status": body.status}))
        return {"ok": True}

    @app.delete("/api/flows/{flow_id}/instances/{instance_id}")
    async def deregister_instance(flow_id: str, instance_id: str) -> dict[str, Any]:
        _resolve_flow_id(flow_id)
        inst_store = registry.instance_store(flow_id)
        inst_store.update_status(instance_id, "stopped")
        found = inst_store.deregister(instance_id)

        # Transition publish state back if no running instances remain
        ps = registry.publish_store(flow_id)
        state = ps.read()
        running_count = inst_store.count_running()
        changed = False
        if running_count == 0:
            for ch_name in ("production", "gray"):
                ch = _channel_state(state, ch_name)
                if ch.status == PublishStatus.RUNNING:
                    ch.status = PublishStatus.UNPUBLISHED
                    ch.stopped_at = time.time()
                    _set_channel(state, ch_name, ch)
                    changed = True
            if changed:
                ps.write(state)

        bus = get_event_bus()
        await bus.publish(make_event("instance.stopped", flow_id, {"instance_id": instance_id}))
        if changed:
            await bus.publish(make_event("publish.state_changed", flow_id, state.model_dump()))

        return {"ok": True, "found": found}

    # -----------------------------------------------------------------------
    # SSE – real-time event stream
    # -----------------------------------------------------------------------

    @app.get("/api/flows/{flow_id}/events")
    async def flow_events(flow_id: str) -> StreamingResponse:
        _resolve_flow_id(flow_id)

        async def generator() -> AsyncGenerator[str, None]:
            # Send initial state snapshot
            if registry.exists(flow_id):
                inst_store = registry.instance_store(flow_id)
                snapshot = {
                    "type": "snapshot",
                    "flow_id": flow_id,
                    "publish": _read_publish_state(flow_id).model_dump(),
                    "instances": [i.model_dump() for i in inst_store.list_instances()],
                    "ts": time.time(),
                }
                yield f"data: {json.dumps(snapshot)}\n\n"

            bus = get_event_bus()
            sub = bus.subscribe()
            async with sub as events:
                async for event in events:
                    if event.get("flow_id") == flow_id:
                        yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(
            generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # -----------------------------------------------------------------------
    # Flow validate + run  (updated to work with versioned store)
    # -----------------------------------------------------------------------

    @app.post("/api/flows/{flow_id}/validate")
    def validate_flow_file(flow_id: str) -> dict[str, Any]:
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)
        try:
            data = _load_flow_data(flow_id)
            flow = FlowDefinition.model_validate(data)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "name": flow.name, "version": flow.version}

    @app.post("/api/flows/{flow_id}/run")
    async def run_flow(
        flow_id: str,
        body: RunFlowBody | None = Body(default=None),
    ) -> dict[str, Any]:
        body = body or RunFlowBody()
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)

        try:
            data = _load_flow_data(flow_id)
            flow = load_flow_from_dict(data)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Load failed: {e}") from e

        if body.initial_context is not None:
            merged: dict[str, Any] = {}
            if body.merge and flow.initial_context:
                merged.update(flow.initial_context)
            merged.update(body.initial_context)
            flow.initial_context = merged

        rt = FlowRuntime(flow)
        started = time.monotonic()
        timed_out = False
        try:
            res = await asyncio.wait_for(rt.run(), timeout=body.timeout_sec)
        except asyncio.TimeoutError:
            timed_out = True
            res = None
        elapsed_ms = int((time.monotonic() - started) * 1000)

        if timed_out or res is None:
            partial_runs = [r.to_dict() for r in sorted(rt._node_runs.values(), key=lambda r: r.order)]
            partial_state = {
                k: v.value if isinstance(v, NodeState) else str(v) for k, v in rt.node_state.items()
            }
            return {
                "ok": False,
                "state": "TERMINATED",
                "message": f"Run exceeded {body.timeout_sec}s",
                "elapsed_ms": elapsed_ms,
                "node_state": partial_state,
                "node_runs": partial_runs,
                "flow_logs": list(rt._flow_logs),
                "global_ns": {},
            }

        ns = dict(res.context.global_ns)
        ns.pop("dictionary", None)
        node_state = {k: v.value if isinstance(v, NodeState) else str(v) for k, v in res.node_state.items()}
        return {
            "ok": res.state.value == "COMPLETED",
            "state": res.state.value,
            "message": res.message,
            "elapsed_ms": elapsed_ms,
            "node_state": node_state,
            "node_runs": [r.to_dict() for r in res.node_runs],
            "flow_logs": list(res.flow_logs),
            "global_ns": ns,
        }

    # -----------------------------------------------------------------------
    # Data dictionary
    # -----------------------------------------------------------------------

    @app.get("/api/dict")
    def get_data_dictionary() -> dict[str, Any]:
        st = data_dict.store()
        return {"dict_dir": str(st.directory), "tree": st.read_tree(), "yaml": st.read_raw()}

    @app.put("/api/dict")
    def put_data_dictionary_raw(body: PutDictRawBody) -> dict[str, Any]:
        try:
            data_dict.store().write_raw(body.content)
        except DataDictError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True}

    @app.get("/api/dict/subtree")
    def get_dict_subtree(path: str = "") -> dict[str, Any]:
        try:
            y = data_dict.subtree_as_yaml(path)
        except DataDictError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"path": path, "yaml": y}

    @app.put("/api/dict/subtree")
    def put_dict_subtree(path: str = "", body: PutDictSubtreeBody = Body(...)) -> dict[str, Any]:
        try:
            data_dict.apply_subtree_yaml(path, body.yaml)
        except DataDictError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"YAML error: {e}") from e
        return {"ok": True}

    @app.delete("/api/dict/subtree")
    def delete_dict_subtree(path: str = "") -> dict[str, Any]:
        try:
            data_dict.delete_path(path)
        except DataDictError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True}

    @app.get("/api/dict/lookup")
    def dict_lookup(path: str) -> dict[str, Any]:
        v = data_dict.lookup(path, None)
        return {"path": path, "value": v}

    # -----------------------------------------------------------------------
    # Lookup tables
    # -----------------------------------------------------------------------

    @app.get("/api/lookups")
    def list_lookups() -> dict[str, Any]:
        st = get_lookup_store()
        return {"lookup_dir": str(st.directory), "namespaces": st.list_namespaces()}

    @app.get("/api/lookups/{namespace}")
    def get_lookup_table(namespace: str) -> dict[str, Any]:
        try:
            validate_lookup_namespace(namespace)
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        st = get_lookup_store()
        if not st.exists(namespace):
            return {"fields": [], "rows": []}
        return st.read_table(namespace)

    @app.put("/api/lookups/{namespace}")
    def put_lookup_table(namespace: str, body: PutLookupBody) -> dict[str, Any]:
        try:
            validate_lookup_namespace(namespace)
            return put_table(namespace, body.model_dump(exclude_none=True))
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.delete("/api/lookups/{namespace}")
    def delete_lookup_table(namespace: str) -> dict[str, Any]:
        try:
            validate_lookup_namespace(namespace)
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        get_lookup_store().delete_namespace(namespace)
        return {"ok": True}

    @app.post("/api/lookups/{namespace}/import")
    async def import_lookup_table(
        namespace: str,
        file: UploadFile = File(...),
        mode: str = Form("replace"),
        format: str = Form("auto"),  # noqa: A002
    ) -> dict[str, Any]:
        rows: list[Any] = []
        try:
            validate_lookup_namespace(namespace)
            raw = await file.read()
            rows = rows_from_bytes(raw, filename=file.filename or "", format=format)
            merge_imported_rows(namespace, rows, mode=mode)
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "imported": len(rows), "mode": mode}

    @app.get("/api/lookups/{namespace}/query")
    def query_lookup_http(
        namespace: str,
        filter_json: str = Query(default="{}", alias="filter"),
    ) -> dict[str, Any]:
        from flow_engine.lookup.lookup_service import lookup_query as run_lookup_query

        try:
            validate_lookup_namespace(namespace)
            filt = json.loads(filter_json or "{}")
            if not isinstance(filt, dict):
                raise ValueError("filter must be a JSON object")
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(e)) from e
        rows = run_lookup_query(namespace, filt)
        return {"namespace": namespace, "filter": filt, "rows": rows}

    # -----------------------------------------------------------------------
    # Starlark
    # -----------------------------------------------------------------------

    @app.get("/api/starlark/registry")
    def starlark_registry() -> dict[str, Any]:
        return load_registry()

    @app.get("/api/starlark/runtime/stats")
    def starlark_runtime_stats() -> dict[str, Any]:
        return runtime_stats()

    @app.post("/api/starlark/runtime/warmup")
    def starlark_runtime_warmup(body: StarlarkWarmupBody) -> dict[str, Any]:
        return warmup_runtime(body.module_ids, body.script_samples)

    @app.get("/api/starlark/user/scripts")
    def starlark_user_scripts() -> dict[str, Any]:
        return {"scripts": user_script_list(), "root": str(user_scripts_root())}

    @app.get("/api/starlark/internal/{path:path}")
    def get_internal_script(path: str) -> dict[str, Any]:
        try:
            p = resolve_internal_script_file(path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not p.is_file():
            raise HTTPException(status_code=404, detail="Internal module not found")
        return {"path": path, "content": p.read_text(encoding="utf-8")}

    @app.get("/api/starlark/user/{tenant}/{path:path}")
    def get_user_script(tenant: str, path: str) -> dict[str, Any]:
        try:
            p = resolve_user_script_file(tenant, path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not p.is_file():
            raise HTTPException(status_code=404, detail="Script not found")
        return {"path": f"{tenant}/{path}", "content": p.read_text(encoding="utf-8")}

    @app.put("/api/starlark/user/{tenant}/{path:path}")
    def put_user_script(tenant: str, path: str, body: PutUserScriptBody) -> dict[str, Any]:
        try:
            p = resolve_user_script_file(tenant, path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body.content, encoding="utf-8", newline="\n")
        return {"ok": True, "path": f"{tenant}/{path}"}

    # -----------------------------------------------------------------------
    # Debug
    # -----------------------------------------------------------------------

    @app.post("/api/debug/node")
    def debug_node(body: DebugNodeBody) -> JSONResponse:
        try:
            result, logs = debug_task_script(body.script, body.initial_context or {})
            return JSONResponse(content={"ok": True, "result": result, "logs": logs})
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                status_code=200,
                content={
                    "ok": False,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                    "logs": [],
                },
            )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "flow_engine.api.http_api:app",
        host="127.0.0.1",
        port=int(__import__("os").environ.get("FLOW_ENGINE_PORT", "8000")),
        reload=__import__("os").environ.get("FLOW_ENGINE_RELOAD", "").lower() in ("1", "true", "yes"),
    )
