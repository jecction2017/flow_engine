"""FastAPI HTTP service: versioned flow CRUD and execution."""

from __future__ import annotations

import asyncio
import json
import time
import traceback
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from flow_engine.engine.compiler import compile_flow
from flow_engine.engine.loader import load_flow_from_dict
from flow_engine.engine.models import ExecutionStrategy, FlowDefinition, NodeState, StrategyMode
from flow_engine.engine.orchestrator import FlowRuntime
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
from flow_engine.stores.profile_store import (
    ProfileConfigError,
    profile_scope,
    store as profile_store,
)
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
    fields: list[str] | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)


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
            "dict_dir": str(st.directory),
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
        return {"lookup_dir": str(st.directory), "profile": pid, "namespaces": st.list_namespaces(profile=pid)}

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
        filter_json: str = Query(default="{}", alias="filter"),
        profile: str | None = Query(default=None),
    ) -> dict[str, Any]:
        from flow_engine.lookup.lookup_service import lookup_query as run_lookup_query

        try:
            validate_lookup_namespace(namespace)
            pid = profile_store().resolve_profile(profile)
            filt = json.loads(filter_json or "{}")
            if not isinstance(filt, dict):
                raise ValueError("filter must be a JSON object")
        except LookupStoreError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(e)) from e
        with profile_scope(pid):
            rows = run_lookup_query(namespace, filt)
        return {"namespace": namespace, "profile": pid, "filter": filt, "rows": rows}

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
