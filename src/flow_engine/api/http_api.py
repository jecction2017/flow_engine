"""FastAPI HTTP service: versioned flow CRUD and execution."""

from __future__ import annotations

import asyncio
import json
import time
import traceback
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from flow_engine.db.models import (
    FeFlowDeployment,
    FeFlowTestBatch,
    FeFlowTestBatchPlan,
    FeFlowTestPlan,
    FeWorker,
    FeWorkerAssignment,
)
from flow_engine.db.session import db_session
from flow_engine.engine.compiler import compile_flow
from flow_engine.engine.loader import load_flow_from_dict
from flow_engine.engine.models import ExecutionStrategy, FlowDefinition, NodeState, StrategyMode
from flow_engine.engine.orchestrator import FlowRuntime
from flow_engine.engine.starlark_glue import debug_task_script
from flow_engine.runner import deploy_persistence, test_persistence
from flow_engine.runner import test_runner
from flow_engine.runner.models import CapabilityRule, MockConfig, RunMode
from flow_engine.lookup.lookup_import import rows_from_bytes
from flow_engine.lookup.lookup_service import (
    delete_rows,
    delete_rows_by_filter,
    merge_imported_rows,
    put_table,
    update_table_schema,
)
from flow_engine.lookup.lookup_store import LookupStoreError, get_lookup_store, validate_lookup_namespace
from flow_engine.starlark_sdk.python_builtin_impl import user_script_list
from flow_engine.starlark_sdk.registry_data import load_registry
from flow_engine.starlark_sdk.runtime import runtime_stats, warmup_runtime
from flow_engine.starlark_sdk.uri_resolve import resolve_internal_script_file
from flow_engine.starlark_sdk.user_script_store import get_user_script_store
from flow_engine.stores import data_dict
from flow_engine.stores.dict_store import DataDictError
from flow_engine.stores.profile_store import (
    ProfileConfigError,
    profile_scope,
    store as profile_store,
)
from flow_engine.stores.version_store import FlowVersionRegistry, validate_flow_id
from flow_engine.time_utils import utc_isoformat


def _load_dotenv() -> None:
    """Best-effort .env loading for local development."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


_load_dotenv()

# ---------------------------------------------------------------------------
# Global registry (replaces old FlowYamlStore singleton)
# ---------------------------------------------------------------------------

registry = FlowVersionRegistry()

# ---------------------------------------------------------------------------
# Request / response body models
# ---------------------------------------------------------------------------


class CreateFlowBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    # 可选的展示名；留空时 UI 回落 flow_id，初始 yaml 里的 display_name 也留空。
    display_name: str | None = None


class DebugNodeBody(BaseModel):
    script: str
    initial_context: dict[str, Any] = Field(default_factory=dict)
    profile: str | None = None


class PutUserScriptBody(BaseModel):
    content: str = Field(..., description="Starlark source")


class PutDictRawBody(BaseModel):
    content: str = Field(..., description="Full dictionary.yaml text")


class PutDictSubtreeBody(BaseModel):
    yaml: str = Field(..., description="YAML fragment for this subtree or root")


class PutDictModuleBody(BaseModel):
    yaml: str = Field(..., description="YAML mapping for this dictionary module")


class CreateDictProfileBody(BaseModel):
    profile: str


class SetDefaultProfileBody(BaseModel):
    default_profile: str


class PutLookupBody(BaseModel):
    schema: dict[str, Any] | None = None
    fields: list[str] | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)


class DeleteLookupRowsBody(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)


class DeleteLookupRowsByFilterBody(BaseModel):
    filter: dict[str, Any] | str = Field(default_factory=dict)


class PutLookupSchemaBody(BaseModel):
    schema: dict[str, Any]


class StarlarkWarmupBody(BaseModel):
    module_ids: list[str] = Field(default_factory=list)
    script_samples: list[str] = Field(default_factory=list)


class RunFlowBody(BaseModel):
    initial_context: dict[str, Any] | None = None
    merge: bool = True
    timeout_sec: float = Field(default=30.0, ge=0.1, le=600.0)
    profile: str | None = None
    runtime_patch: dict[str, Any] | None = None


class CommitVersionBody(BaseModel):
    description: str | None = None
    data: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Runner request schemas
# ---------------------------------------------------------------------------


class CreateDeploymentBody(BaseModel):
    flow_code: str = Field(..., min_length=1, max_length=128)
    ver_no: int = Field(..., ge=1)
    mode: str = Field(default="production", pattern=r"^(shadow|production)$")
    schedule_type: str = Field(..., pattern=r"^(once|cron|resident)$")
    schedule_config: dict[str, Any] = Field(default_factory=dict)
    worker_policy: dict[str, Any] = Field(
        default_factory=lambda: {
            "type": "single_active",
            "min_workers": 1,
            "max_restarts": 5,
            "restart_backoff_s": 30,
        }
    )
    capability_policy: list[CapabilityRule] = Field(default_factory=list)
    env_profile_code: str = ""
    worker_targeting: dict[str, Any] = Field(
        default_factory=dict,
        description="Worker 定向策略（pool/labels 等）；空对象表示不限制",
    )


def _normalize_worker_targeting(raw: Any) -> dict[str, Any]:
    """Normalize & validate worker_targeting into a strict any/pin/pool shape."""
    targeting: dict[str, Any] = raw if isinstance(raw, dict) else {}
    mode = str(targeting.get("mode") or "any").strip().lower()
    if mode not in ("any", "pin", "pool"):
        raise HTTPException(status_code=400, detail="worker_targeting.mode must be any|pin|pool")

    if mode == "any":
        return {"mode": "any"}

    if mode == "pin":
        worker_id = str(targeting.get("worker_id") or "").strip()
        if not worker_id:
            raise HTTPException(status_code=400, detail="worker_targeting.worker_id is required for mode=pin")
        return {"mode": "pin", "worker_id": worker_id}

    # pool
    raw_ids = targeting.get("worker_ids")
    if not isinstance(raw_ids, list):
        raise HTTPException(status_code=400, detail="worker_targeting.worker_ids must be a non-empty list for mode=pool")
    ids = [str(x).strip() for x in raw_ids if str(x).strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="worker_targeting.worker_ids must be a non-empty list for mode=pool")
    # stable order + de-dup
    dedup = list(dict.fromkeys(ids))
    return {"mode": "pool", "worker_ids": dedup}


class PatchDeploymentBody(BaseModel):
    status: str = Field(..., pattern=r"^(stopping|pending)$")


class CreateTestBatchBody(BaseModel):
    flow_code: str = Field(..., min_length=1, max_length=128)
    # 兼容旧 API：传 ver_no（>=1）；新语义优先使用 version_channel
    ver_no: int | None = Field(default=None, ge=1)
    version_channel: str = Field(default="latest", description="latest | draft | vN | N")
    test_ns_code: str = Field(..., min_length=1, max_length=64)
    profile_code: str = Field(..., min_length=1, max_length=64)
    mock_config: dict[str, MockConfig] = Field(default_factory=dict)
    context_mapping: dict[str, Any] | None = None
    concurrency: int = Field(default=4, ge=1, le=64)
    assertions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="断言规则（与方案 assertions 同结构）；临时批次可内联传入",
    )


class CreateTestPlanBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    flow_code: str = Field(..., min_length=1, max_length=128)
    version_channel: str = Field(default="latest", min_length=1, max_length=32)
    test_ns_code: str = Field(..., min_length=1, max_length=64)
    profile_code: str = Field(..., min_length=1, max_length=64)
    concurrency: int = Field(default=4, ge=1, le=64)
    mock_config: dict[str, MockConfig] = Field(default_factory=dict)
    context_mapping: dict[str, Any] | None = None
    assertions: list[dict[str, Any]] = Field(default_factory=list)


class PatchTestPlanBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    version_channel: str | None = Field(default=None, min_length=1, max_length=32)
    test_ns_code: str | None = Field(default=None, min_length=1, max_length=64)
    profile_code: str | None = Field(default=None, min_length=1, max_length=64)
    concurrency: int | None = Field(default=None, ge=1, le=64)
    mock_config: dict[str, MockConfig] | None = None
    context_mapping: dict[str, Any] | None = None
    assertions: list[dict[str, Any]] | None = None


class CopyTestPlanBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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
            "flows_dir": registry.directory,
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
        minimal = FlowDefinition(
            display_name=body.display_name,
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

    @app.get("/api/flows/{flow_id}/resolve")
    def resolve_channel(flow_id: str, channel: str = Query(default="latest")) -> dict[str, Any]:
        """Resolve ``latest``, ``draft``, or ``vN`` / ``N`` to a concrete flow definition."""
        _resolve_flow_id(flow_id)
        _require_flow(flow_id)
        try:
            version_num, data = registry.resolve_version_data(flow_id, channel)
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return {"flow_id": flow_id, "channel": channel, "version": version_num, "definition": data}

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
        return {"ok": True, "display_name": flow.display_name or "", "version": flow.version}

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

        try:
            profile_id = profile_store().resolve_profile(body.profile)
        except ProfileConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        try:
            resolved = data_dict.resolve(profile_id, body.runtime_patch)
        except DataDictError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        rt = FlowRuntime(flow, dictionary=resolved["resolved_dictionary"])
        started = time.monotonic()
        timed_out = False
        try:
            with profile_scope(profile_id):
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
                "resolved_profile": resolved["resolved_profile"],
                "resolved_modules": resolved["resolved_modules"],
                "resolved_hash": resolved["resolved_hash"],
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
            "resolved_profile": resolved["resolved_profile"],
            "resolved_modules": resolved["resolved_modules"],
            "resolved_hash": resolved["resolved_hash"],
        }

    # -----------------------------------------------------------------------
    # Data dictionary
    # -----------------------------------------------------------------------

    def _dict_layer(layer: str) -> str:
        if layer not in {"base", "profile"}:
            raise HTTPException(status_code=400, detail="layer must be 'base' or 'profile'")
        return layer

    @app.get("/api/dict")
    def get_data_dictionary_summary() -> dict[str, Any]:
        st = data_dict.store()
        return {
            "dict_dir": st.directory,
            "profiles": profile_store().list_profiles(),
            "base_modules": [m.__dict__ for m in st.list_modules("base")],
        }

    @app.get("/api/dict/resolve")
    def resolve_data_dictionary(profile: str | None = Query(default=None)) -> dict[str, Any]:
        try:
            pid = profile_store().resolve_profile(profile)
            return data_dict.resolve(pid)
        except (DataDictError, ProfileConfigError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.get("/api/dict/profiles")
    def list_dict_profiles() -> dict[str, Any]:
        return {"profiles": profile_store().list_profiles()}

    @app.post("/api/dict/profiles")
    def create_dict_profile(body: CreateDictProfileBody) -> dict[str, Any]:
        try:
            pid = profile_store().create_profile(body.profile)
        except (ProfileConfigError, DataDictError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "profile": pid}

    @app.get("/api/profiles")
    def list_profiles() -> dict[str, Any]:
        return {"profiles": profile_store().list_profiles()}

    @app.post("/api/profiles")
    def create_profile(body: CreateDictProfileBody) -> dict[str, Any]:
        try:
            pid = profile_store().create_profile(body.profile)
        except (ProfileConfigError, DataDictError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "profile": pid}

    @app.get("/api/profiles/config")
    def get_profile_config() -> dict[str, Any]:
        st = profile_store()
        return {"default_profile": st.get_default_profile(), "profiles": st.list_profiles()}

    @app.put("/api/profiles/config")
    def set_profile_config(body: SetDefaultProfileBody) -> dict[str, Any]:
        try:
            pid = profile_store().set_default_profile(body.default_profile)
        except ProfileConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "default_profile": pid}

    @app.get("/api/dict/modules")
    def list_dict_modules(layer: str = "base", profile: str | None = None) -> dict[str, Any]:
        try:
            lay = _dict_layer(layer)
            modules = data_dict.store().list_modules(lay, profile=profile)
        except DataDictError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"layer": layer, "profile": profile, "modules": [m.__dict__ for m in modules]}

    @app.get("/api/dict/module")
    def get_dict_module(module_id: str, layer: str = "base", profile: str | None = None) -> dict[str, Any]:
        try:
            lay = _dict_layer(layer)
            yaml_text = data_dict.store().read_module_raw(lay, module_id, profile=profile)
        except DataDictError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"layer": layer, "profile": profile, "module_id": module_id, "yaml": yaml_text}

    @app.put("/api/dict/module")
    def put_dict_module(
        module_id: str,
        layer: str = "base",
        profile: str | None = None,
        body: PutDictModuleBody = Body(...),
    ) -> dict[str, Any]:
        try:
            lay = _dict_layer(layer)
            data_dict.store().write_module(lay, module_id, body.yaml, profile=profile)
        except DataDictError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "layer": layer, "profile": profile, "module_id": module_id}

    @app.delete("/api/dict/module")
    def delete_dict_module(module_id: str, layer: str = "base", profile: str | None = None) -> dict[str, Any]:
        try:
            lay = _dict_layer(layer)
            data_dict.store().delete_module(lay, module_id, profile=profile)
        except DataDictError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True}

    @app.get("/api/dict/lookup")
    def dict_lookup(path: str, profile: str | None = Query(default=None)) -> dict[str, Any]:
        try:
            pid = profile_store().resolve_profile(profile)
            with profile_scope(pid), data_dict.dictionary_scope(data_dict.tree_copy(pid)):
                v = data_dict.lookup(path, None)
        except (DataDictError, ProfileConfigError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"path": path, "profile": pid, "value": v}

    # -----------------------------------------------------------------------
    # Lookup tables
    # -----------------------------------------------------------------------

    @app.get("/api/lookups")
    def list_lookups(profile: str | None = Query(default=None)) -> dict[str, Any]:
        st = get_lookup_store()
        try:
            pid = profile_store().resolve_profile(profile)
        except ProfileConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"lookup_dir": st.directory, "profile": pid, "namespaces": st.list_namespaces(profile=pid)}

    @app.get("/api/lookups/{namespace}")
    def get_lookup_table(namespace: str, profile: str | None = Query(default=None)) -> dict[str, Any]:
        try:
            validate_lookup_namespace(namespace)
            pid = profile_store().resolve_profile(profile)
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except ProfileConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        st = get_lookup_store()
        if not st.exists(namespace, profile=pid):
            return {"fields": [], "rows": []}
        return st.read_table(namespace, profile=pid)

    @app.put("/api/lookups/{namespace}")
    def put_lookup_table(namespace: str, body: PutLookupBody, profile: str | None = Query(default=None)) -> dict[str, Any]:
        try:
            validate_lookup_namespace(namespace)
            pid = profile_store().resolve_profile(profile)
            return put_table(namespace, body.model_dump(exclude_none=True), profile=pid)
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except ProfileConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.put("/api/lookups/{namespace}/schema")
    def put_lookup_schema(
        namespace: str,
        body: PutLookupSchemaBody,
        profile: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            validate_lookup_namespace(namespace)
            pid = profile_store().resolve_profile(profile)
            return update_table_schema(namespace, body.schema, profile=pid)
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except ProfileConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.delete("/api/lookups/{namespace}")
    def delete_lookup_table(namespace: str, profile: str | None = Query(default=None)) -> dict[str, Any]:
        try:
            validate_lookup_namespace(namespace)
            pid = profile_store().resolve_profile(profile)
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except ProfileConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        get_lookup_store().delete_namespace(namespace, profile=pid)
        return {"ok": True}

    @app.post("/api/lookups/{namespace}/rows/delete")
    def delete_lookup_rows(
        namespace: str,
        body: DeleteLookupRowsBody,
        profile: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            validate_lookup_namespace(namespace)
            pid = profile_store().resolve_profile(profile)
            result = delete_rows(namespace, body.rows, profile=pid)
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except ProfileConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, **result}

    @app.post("/api/lookups/{namespace}/rows/delete_by_filter")
    def delete_lookup_rows_by_filter(
        namespace: str,
        body: DeleteLookupRowsByFilterBody,
        profile: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            validate_lookup_namespace(namespace)
            pid = profile_store().resolve_profile(profile)
            result = delete_rows_by_filter(namespace, body.filter, profile=pid)
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except ProfileConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, **result}

    @app.post("/api/lookups/{namespace}/import")
    async def import_lookup_table(
        namespace: str,
        file: UploadFile = File(...),
        mode: str = Form("replace"),
        format: str = Form("auto"),  # noqa: A002
        profile: str | None = Form(default=None),
    ) -> dict[str, Any]:
        rows: list[Any] = []
        try:
            validate_lookup_namespace(namespace)
            pid = profile_store().resolve_profile(profile)
            raw = await file.read()
            rows = rows_from_bytes(raw, filename=file.filename or "", format=format)
            merge_imported_rows(namespace, rows, mode=mode, profile=pid)
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except ProfileConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "imported": len(rows), "mode": mode}

    @app.get("/api/lookups/{namespace}/query")
    def query_lookup_http(
        namespace: str,
        filter_raw: str = Query(default="", alias="filter"),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=10_000),
        profile: str | None = Query(default=None),
    ) -> dict[str, Any]:
        from flow_engine.lookup.lookup_service import lookup_query_page as run_lookup_query_page

        try:
            validate_lookup_namespace(namespace)
            pid = profile_store().resolve_profile(profile)
            filt: dict[str, Any] | str = {}
            raw = (filter_raw or "").strip()
            if raw:
                if raw.startswith("{"):
                    parsed = json.loads(raw)
                    if not isinstance(parsed, dict):
                        raise ValueError("filter JSON must be an object")
                    filt = parsed
                else:
                    filt = raw
            with profile_scope(pid):
                page = run_lookup_query_page(namespace, filt, offset=offset, limit=limit)
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"namespace": namespace, "profile": pid, "filter": filt, **page}

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
        return {"scripts": user_script_list(), "root": "mysql://user-scripts"}

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
            content = get_user_script_store().get_script(tenant, path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Script not found") from None
        return {"path": f"{tenant}/{path}", "content": content}

    @app.put("/api/starlark/user/{tenant}/{path:path}")
    def put_user_script(tenant: str, path: str, body: PutUserScriptBody) -> dict[str, Any]:
        try:
            get_user_script_store().put_script(tenant, path, body.content)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "path": f"{tenant}/{path}"}

    # -----------------------------------------------------------------------
    # Debug
    # -----------------------------------------------------------------------

    @app.post("/api/debug/node")
    def debug_node(body: DebugNodeBody) -> JSONResponse:
        try:
            profile = profile_store().resolve_profile(body.profile)
            resolved = data_dict.resolve(profile)
            with profile_scope(profile), data_dict.dictionary_scope(resolved["resolved_dictionary"]):
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

    # -----------------------------------------------------------------------
    # Deployments
    # -----------------------------------------------------------------------

    def _serialize_deployment(row: FeFlowDeployment) -> dict[str, Any]:
        return {
            "id": row.id,
            "flow_code": row.flow_code,
            "ver_no": row.ver_no,
            "mode": row.mode,
            "schedule_type": row.schedule_type,
            "schedule_config": row.schedule_config,
            "worker_policy": row.worker_policy,
            "capability_policy": row.capability_policy,
            "worker_targeting": _normalize_worker_targeting(getattr(row, "worker_targeting", None) or {}),
            "status": row.status,
            "status_detail": getattr(row, "status_detail", None),
            "env_profile_code": row.env_profile_code,
            "parent_deployment_id": row.parent_deployment_id,
            "created_at": utc_isoformat(row.created_at),
            "updated_at": utc_isoformat(row.updated_at),
        }

    @app.post("/api/deployments")
    def create_deployment(body: CreateDeploymentBody) -> dict[str, Any]:
        if body.schedule_type == "cron":
            if not (body.schedule_config or {}).get("cron_expr"):
                raise HTTPException(
                    status_code=400, detail="cron schedule requires schedule_config.cron_expr"
                )
        with db_session() as s:
            # cron deployments are templates; they should be active immediately so the
            # Scheduler can fire child once deployments. Do not enqueue them as pending.
            initial_status = "running" if body.schedule_type == "cron" else "pending"
            targeting = _normalize_worker_targeting(body.worker_targeting or {})
            row = FeFlowDeployment(
                flow_code=body.flow_code,
                ver_no=body.ver_no,
                mode=body.mode,
                schedule_type=body.schedule_type,
                schedule_config=body.schedule_config or {},
                worker_policy=body.worker_policy or {},
                capability_policy=[r.model_dump() for r in body.capability_policy],
                status=initial_status,
                env_profile_code=body.env_profile_code or "",
                worker_targeting=targeting,
            )
            s.add(row)
            s.flush()
            return _serialize_deployment(row)

    @app.get("/api/deployments")
    def list_deployments(
        flow_code: str | None = Query(default=None),
        status: str | None = Query(default=None),
        mode: str | None = Query(default=None),
        root_only: bool = Query(
            default=False,
            description="If true, exclude rows with parent_deployment_id set (legacy cron clones).",
        ),
    ) -> dict[str, Any]:
        with db_session() as s:
            stmt = select(FeFlowDeployment).where(FeFlowDeployment.deleted_at.is_(None))
            if root_only:
                stmt = stmt.where(FeFlowDeployment.parent_deployment_id.is_(None))
            if flow_code:
                stmt = stmt.where(FeFlowDeployment.flow_code == flow_code)
            if status:
                stmt = stmt.where(FeFlowDeployment.status == status)
            if mode:
                stmt = stmt.where(FeFlowDeployment.mode == mode)
            stmt = stmt.order_by(FeFlowDeployment.id.desc())
            rows = list(s.execute(stmt).scalars().all())
            return {"deployments": [_serialize_deployment(r) for r in rows]}

    @app.get("/api/deployments/{deployment_id}")
    def get_deployment(deployment_id: int) -> dict[str, Any]:
        with db_session() as s:
            row = s.get(FeFlowDeployment, deployment_id)
            if row is None or row.deleted_at is not None:
                raise HTTPException(status_code=404, detail="deployment not found")
            assn_stmt = (
                select(FeWorkerAssignment)
                .where(FeWorkerAssignment.deployment_id == deployment_id)
                .where(FeWorkerAssignment.deleted_at.is_(None))
            )
            assignments = [
                {
                    "id": a.id,
                    "worker_id": a.worker_id,
                    "role": a.role,
                    "lease_expires_at": utc_isoformat(a.lease_expires_at),
                }
                for a in s.execute(assn_stmt).scalars().all()
            ]
            return {**_serialize_deployment(row), "assignments": assignments}

    @app.patch("/api/deployments/{deployment_id}")
    def patch_deployment(deployment_id: int, body: PatchDeploymentBody) -> dict[str, Any]:
        with db_session() as s:
            row = s.get(FeFlowDeployment, deployment_id)
            if row is None or row.deleted_at is not None:
                raise HTTPException(status_code=404, detail="deployment not found")
            row.status = body.status
            return {"id": row.id, "status": row.status}

    @app.delete("/api/deployments/{deployment_id}")
    def delete_deployment(deployment_id: int) -> dict[str, Any]:
        with db_session() as s:
            row = s.get(FeFlowDeployment, deployment_id)
            if row is None or row.deleted_at is not None:
                raise HTTPException(status_code=404, detail="deployment not found")
            row.deleted_at = datetime.now(timezone.utc)
        return {"ok": True}

    # -----------------------------------------------------------------------
    # Workers
    # -----------------------------------------------------------------------

    @app.get("/api/workers")
    def list_workers() -> dict[str, Any]:
        with db_session() as s:
            stmt = (
                select(FeWorker)
                .where(FeWorker.deleted_at.is_(None))
                .order_by(FeWorker.last_heartbeat.desc())
            )
            workers = list(s.execute(stmt).scalars().all())
            assn_stmt = select(FeWorkerAssignment).where(
                FeWorkerAssignment.deleted_at.is_(None)
            )
            assignments = list(s.execute(assn_stmt).scalars().all())
            by_worker: dict[str, list[int]] = {}
            for a in assignments:
                by_worker.setdefault(a.worker_id, []).append(int(a.deployment_id))
            return {
                "workers": [
                    {
                        "worker_id": w.worker_id,
                        "host": w.host,
                        "pid": w.pid,
                        "status": w.status,
                        "last_heartbeat": utc_isoformat(w.last_heartbeat),
                        "capabilities": w.capabilities,
                        "assigned_deployments": by_worker.get(w.worker_id, []),
                    }
                    for w in workers
                ]
            }

    # -----------------------------------------------------------------------
    # Test batches (lookup-namespace driven)
    # -----------------------------------------------------------------------

    def _serialize_test_plan(row: FeFlowTestPlan) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "name": row.name,
            "flow_code": row.flow_code,
            "version_channel": row.version_channel,
            "test_ns_code": row.test_ns_code,
            "profile_code": row.profile_code,
            "concurrency": int(row.concurrency),
            "updated_at": utc_isoformat(row.updated_at),
            "created_at": utc_isoformat(row.created_at),
        }

    @app.get("/api/test-plans")
    def list_test_plans(
        flow_code: str | None = Query(default=None),
    ) -> dict[str, Any]:
        with db_session() as s:
            stmt = select(FeFlowTestPlan).where(FeFlowTestPlan.deleted_at.is_(None))
            if flow_code:
                stmt = stmt.where(FeFlowTestPlan.flow_code == flow_code)
            stmt = stmt.order_by(FeFlowTestPlan.updated_at.desc())
            rows = list(s.execute(stmt).scalars().all())
            return {"plans": [_serialize_test_plan(r) for r in rows]}

    @app.post("/api/test-plans")
    def create_test_plan(body: CreateTestPlanBody) -> dict[str, Any]:
        mock_ser = json.dumps(
            {nid: cfg.model_dump() for nid, cfg in (body.mock_config or {}).items()},
            ensure_ascii=False,
            default=str,
        )
        mapping_ser = json.dumps(body.context_mapping or {"mode": "spread"}, ensure_ascii=False, default=str)
        assertions_ser = json.dumps(body.assertions or [], ensure_ascii=False, default=str)
        with db_session() as s:
            row = FeFlowTestPlan(
                name=body.name,
                flow_code=body.flow_code,
                version_channel=(body.version_channel or "latest").strip() or "latest",
                test_ns_code=body.test_ns_code,
                profile_code=body.profile_code,
                concurrency=int(body.concurrency),
                mock_config=mock_ser,
                context_mapping=mapping_ser,
                assertions=assertions_ser,
            )
            s.add(row)
            s.flush()
            return _serialize_test_plan(row)

    @app.get("/api/test-plans/{plan_id}")
    def get_test_plan(plan_id: int) -> dict[str, Any]:
        with db_session() as s:
            row = s.get(FeFlowTestPlan, plan_id)
            if row is None or row.deleted_at is not None:
                raise HTTPException(status_code=404, detail="test plan not found")
            return {
                **_serialize_test_plan(row),
                "mock_config": json.loads(row.mock_config or "{}"),
                "context_mapping": json.loads(row.context_mapping or "{}"),
                "assertions": json.loads(getattr(row, "assertions", None) or "[]"),
            }

    @app.patch("/api/test-plans/{plan_id}")
    def patch_test_plan(plan_id: int, body: PatchTestPlanBody) -> dict[str, Any]:
        with db_session() as s:
            row = s.get(FeFlowTestPlan, plan_id)
            if row is None or row.deleted_at is not None:
                raise HTTPException(status_code=404, detail="test plan not found")
            if body.name is not None:
                row.name = body.name
            if body.version_channel is not None:
                row.version_channel = body.version_channel.strip() or "latest"
            if body.test_ns_code is not None:
                row.test_ns_code = body.test_ns_code
            if body.profile_code is not None:
                row.profile_code = body.profile_code
            if body.concurrency is not None:
                row.concurrency = int(body.concurrency)
            if body.mock_config is not None:
                row.mock_config = json.dumps(
                    {nid: cfg.model_dump() for nid, cfg in body.mock_config.items()},
                    ensure_ascii=False,
                    default=str,
                )
            if body.context_mapping is not None:
                row.context_mapping = json.dumps(body.context_mapping, ensure_ascii=False, default=str)
            if body.assertions is not None:
                row.assertions = json.dumps(body.assertions, ensure_ascii=False, default=str)
            s.flush()
            return _serialize_test_plan(row)

    @app.delete("/api/test-plans/{plan_id}")
    def delete_test_plan(plan_id: int) -> dict[str, Any]:
        with db_session() as s:
            row = s.get(FeFlowTestPlan, plan_id)
            if row is None or row.deleted_at is not None:
                raise HTTPException(status_code=404, detail="test plan not found")
            row.deleted_at = datetime.now(timezone.utc)
        return {"ok": True}

    @app.post("/api/test-plans/{plan_id}/run")
    async def run_test_plan(plan_id: int) -> dict[str, Any]:
        """Run a test plan once, creating a new test batch (Run)."""
        with db_session() as s:
            plan = s.get(FeFlowTestPlan, plan_id)
            if plan is None or plan.deleted_at is not None:
                raise HTTPException(status_code=404, detail="test plan not found")
            plan_data = {
                "id": int(plan.id),
                "name": plan.name,
                "flow_code": plan.flow_code,
                "version_channel": plan.version_channel,
                "test_ns_code": plan.test_ns_code,
                "profile_code": plan.profile_code,
                "concurrency": int(plan.concurrency),
                "mock_config": json.loads(plan.mock_config or "{}"),
                "context_mapping": json.loads(plan.context_mapping or "{}"),
                "assertions": json.loads(getattr(plan, "assertions", None) or "[]"),
            }

        res = await create_test_batch(
            CreateTestBatchBody(
                flow_code=plan_data["flow_code"],
                ver_no=None,
                version_channel=plan_data["version_channel"],
                test_ns_code=plan_data["test_ns_code"],
                profile_code=plan_data["profile_code"],
                mock_config={k: MockConfig.model_validate(v) for k, v in (plan_data["mock_config"] or {}).items()},
                context_mapping=plan_data["context_mapping"],
                concurrency=int(plan_data["concurrency"]),
                assertions=list(plan_data.get("assertions") or []),
            )
        )

        # Attach plan snapshot to the created batch for auditability.
        batch_id = int(res["batch_id"])
        await asyncio.to_thread(
            test_runner.attach_plan_to_batch,
            batch_id=batch_id,
            plan_id=int(plan_id),
            plan_snapshot={
                "plan": plan_data,
                "resolved": res.get("resolved") or {},
                "created_at": utc_isoformat(datetime.now(timezone.utc)),
            },
        )
        return res

    @app.get("/api/test-plans/{plan_id}/batches")
    def list_test_plan_batches(
        plan_id: int,
        status: str | None = Query(default=None),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        """List batches (runs) created from a given test plan."""
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        with db_session() as s:
            plan = s.get(FeFlowTestPlan, plan_id)
            if plan is None or plan.deleted_at is not None:
                raise HTTPException(status_code=404, detail="test plan not found")

            # Load all batch ids for stable per-plan sequence numbers.
            seq_stmt = (
                select(FeFlowTestBatchPlan, FeFlowTestBatch)
                .join(FeFlowTestBatch, FeFlowTestBatch.id == FeFlowTestBatchPlan.batch_id)
                .where(FeFlowTestBatchPlan.deleted_at.is_(None))
                .where(FeFlowTestBatch.deleted_at.is_(None))
                .where(FeFlowTestBatchPlan.plan_id == plan_id)
                .order_by(FeFlowTestBatch.id.asc())
            )
            seq_rows = list(s.execute(seq_stmt).all())
            seq_map: dict[int, int] = {}
            for i, (_link, _batch) in enumerate(seq_rows):
                seq_map[int(_batch.id)] = i + 1

            # Apply user-facing sort: newest first
            rows = list(reversed(seq_rows))
            if status:
                rows = [rb for rb in rows if rb[1].status == status]
            total = len(rows)
            page = rows[offset : offset + limit]

            def _elapsed_ms(b: FeFlowTestBatch) -> int | None:
                if not b.started_at:
                    return None
                if not b.finished_at:
                    return None
                try:
                    return int((b.finished_at - b.started_at).total_seconds() * 1000)
                except Exception:  # noqa: BLE001
                    return None

            out = []
            for link, batch in page:
                # plan_snapshot is MEDIUMTEXT JSON
                snapshot = {}
                try:
                    snapshot = json.loads(link.plan_snapshot or "{}")
                except Exception:  # noqa: BLE001
                    snapshot = {}
                summ = test_persistence.summarize_batch_runs(int(batch.id))
                vc = summ.get("verdict_counts") or {}
                tr = max(1, int(batch.total_runs))
                out.append(
                    {
                        "plan_batch_no": seq_map.get(int(batch.id), 0),
                        "batch_id": int(batch.id),
                        "status": batch.status,
                        "flow_code": batch.flow_code,
                        "resolved_ver_no": int(batch.ver_no),
                        "test_ns_code": batch.test_ns_code,
                        "profile_code": batch.profile_code,
                        "total_runs": int(batch.total_runs),
                        "completed_runs": int(batch.completed_runs),
                        "error_runs": int(batch.error_runs),
                        "started_at": utc_isoformat(batch.started_at),
                        "finished_at": utc_isoformat(batch.finished_at),
                        "elapsed_ms": _elapsed_ms(batch),
                        "snapshot": {
                            "created_at": snapshot.get("created_at"),
                            "version_channel": (snapshot.get("plan") or {}).get("version_channel"),
                        },
                        "result_summary": summ,
                        "assertion_pass_rate":
                            round((int(vc.get("pass") or 0) / tr) * 100, 1)
                            if batch.status != "running"
                            else None,
                    }
                )

            return {"plan_id": int(plan_id), "total": total, "offset": offset, "limit": limit, "batches": out}

    @app.get("/api/test-plans/{plan_id}/batches/compare")
    def compare_test_plan_batches(
        plan_id: int,
        left: int = Query(description="Left batch id"),
        right: int = Query(description="Right batch id"),
    ) -> dict[str, Any]:
        """Compare two batches from the same plan (runs aligned by case_key)."""

        def _batch_belongs(pid: int, batch_id: int) -> bool:
            with db_session() as s:
                link = s.execute(
                    select(FeFlowTestBatchPlan)
                    .where(FeFlowTestBatchPlan.plan_id == pid)
                    .where(FeFlowTestBatchPlan.batch_id == batch_id)
                    .where(FeFlowTestBatchPlan.deleted_at.is_(None))
                ).scalar_one_or_none()
                return link is not None

        if not _batch_belongs(plan_id, left) or not _batch_belongs(plan_id, right):
            raise HTTPException(status_code=404, detail="batch not found for this plan")
        return test_persistence.compare_test_batches(left, right)

    @app.post("/api/test-plans/{plan_id}/copy")
    def copy_test_plan(plan_id: int, body: CopyTestPlanBody = Body(default_factory=CopyTestPlanBody)) -> dict[str, Any]:
        """Copy a plan (new id) with the same config."""
        with db_session() as s:
            src = s.get(FeFlowTestPlan, plan_id)
            if src is None or src.deleted_at is not None:
                raise HTTPException(status_code=404, detail="test plan not found")
            new_name = (body.name or "").strip()
            if not new_name:
                new_name = f"{src.name} (copy)"
            row = FeFlowTestPlan(
                name=new_name,
                flow_code=src.flow_code,
                version_channel=src.version_channel,
                test_ns_code=src.test_ns_code,
                profile_code=src.profile_code,
                concurrency=int(src.concurrency),
                mock_config=src.mock_config,
                context_mapping=src.context_mapping,
                assertions=getattr(src, "assertions", None) or "[]",
            )
            s.add(row)
            s.flush()
            return _serialize_test_plan(row)

    @app.post("/api/test-batches")
    async def create_test_batch(body: CreateTestBatchBody) -> dict[str, Any]:
        """Create a test batch and dispatch case execution in the background.

        The batch row is created synchronously so the caller gets a real
        ``batch_id`` immediately for polling; the per-row run loop continues
        asynchronously after the response returns.
        """
        rows = await asyncio.to_thread(
            test_runner._read_test_rows,  # noqa: SLF001
            body.test_ns_code,
            body.profile_code,
        )
        # Resolve flow body (latest/draft/vN) and ver_no for persistence.
        try:
            if body.ver_no is not None:
                resolved_ver_no = int(body.ver_no)
                flow_data = await asyncio.to_thread(
                    test_runner._read_flow_version_body,  # noqa: SLF001
                    body.flow_code,
                    resolved_ver_no,
                )
            else:
                channel = (body.version_channel or "latest").strip() or "latest"
                resolved_ver_no, flow_data = registry.resolve_version_data(body.flow_code, channel)
                # draft channel returns version_num=None; use 0 as a persistent sentinel.
                resolved_ver_no = int(resolved_ver_no or 0)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Resolve flow version failed: {e}") from e

        batch_id = await asyncio.to_thread(
            test_runner._create_test_batch,  # noqa: SLF001
            flow_code=body.flow_code,
            ver_no=resolved_ver_no,
            test_ns_code=body.test_ns_code,
            profile_code=body.profile_code,
            mock_config=body.mock_config,
            total_runs=len(rows),
        )

        if not rows:
            await asyncio.to_thread(
                test_runner._finalize_test_batch,  # noqa: SLF001
                batch_id,
                status="completed",
            )
            return {"batch_id": batch_id, "status": "completed", "total_runs": 0}

        async def _drive() -> None:
            try:
                sem = asyncio.Semaphore(max(1, body.concurrency))
                resolved = await asyncio.to_thread(data_dict.resolve, body.profile_code)

                async def one(row: dict[str, Any]) -> None:
                    async with sem:
                        await test_runner._run_single_test_case(  # noqa: SLF001
                            batch_id=batch_id,
                            flow_code=body.flow_code,
                            ver_no=resolved_ver_no,
                            profile_code=body.profile_code,
                            flow_data=flow_data,
                            dictionary=resolved["resolved_dictionary"],
                            mock_config=body.mock_config,
                            test_input=row,
                            context_mapping=body.context_mapping,
                            assertions=body.assertions or [],
                        )

                await asyncio.gather(*(one(r) for r in rows), return_exceptions=True)
                await asyncio.to_thread(
                    test_runner._finalize_test_batch,  # noqa: SLF001
                    batch_id,
                    status="completed",
                )
            except Exception:  # noqa: BLE001
                await asyncio.to_thread(
                    test_runner._finalize_test_batch,  # noqa: SLF001
                    batch_id,
                    status="failed",
                )

        asyncio.create_task(_drive())
        return {
            "batch_id": batch_id,
            "status": "running",
            "total_runs": len(rows),
            "resolved": {
                "flow_code": body.flow_code,
                "version_channel": (body.version_channel or ("v" + str(body.ver_no or ""))).strip(),
                "ver_no": resolved_ver_no,
                "test_ns_code": body.test_ns_code,
                "profile_code": body.profile_code,
            },
        }

    @app.get("/api/test-batches/{batch_id}")
    def get_test_batch(batch_id: int) -> dict[str, Any]:
        info = test_runner.get_test_batch(batch_id)
        if info is None:
            raise HTTPException(status_code=404, detail="test batch not found")
        return info

    @app.get("/api/test-batches/{batch_id}/runs")
    def list_test_batch_runs(
        batch_id: int,
        status: str | None = Query(default=None),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        page = test_persistence.list_test_runs(
            test_batch_id=batch_id,
            status=status,
            offset=offset,
            limit=limit,
        )
        return page

    @app.get("/api/test-batches/{batch_id}/runs/{run_id}")
    def get_test_batch_run(batch_id: int, run_id: int) -> dict[str, Any]:
        info = test_persistence.get_test_run_detail(run_id)
        if info is None or info.get("test_batch_id") != int(batch_id):
            raise HTTPException(status_code=404, detail="run not found in batch")
        return info

    # -----------------------------------------------------------------------
    # Deploy runs (Run Center domain)
    # -----------------------------------------------------------------------

    @app.get("/api/deploy-runs")
    def list_deploy_runs(
        deployment_id: int | None = Query(default=None),
        flow_code: str | None = Query(default=None),
        mode: str | None = Query(default=None),
        status: str | None = Query(default=None),
        worker_id: str | None = Query(default=None),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        return deploy_persistence.list_deploy_runs(
            deployment_id=deployment_id,
            flow_code=flow_code,
            mode=mode,
            status=status,
            worker_id=worker_id,
            offset=offset,
            limit=limit,
        )

    @app.get("/api/deploy-runs/{run_id}")
    def get_deploy_run(run_id: int) -> dict[str, Any]:
        info = deploy_persistence.get_deploy_run_detail(run_id)
        if info is None:
            raise HTTPException(status_code=404, detail="run not found")
        return info

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
