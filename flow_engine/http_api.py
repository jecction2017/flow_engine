"""FastAPI HTTP service: YAML-backed flow CRUD + node debug."""

from __future__ import annotations

import json
import traceback
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from flow_engine import data_dict
from flow_engine.compiler import compile_flow
from flow_engine.context import ContextStack
from flow_engine.dict_store import DataDictError
from flow_engine.loader import load_flow_from_yaml
from flow_engine.models import ExecutionStrategy, FlowDefinition, StrategyMode
from flow_engine.starlark_glue import run_task_script
from flow_engine.starlark_sdk.paths import user_scripts_root
from flow_engine.starlark_sdk.python_builtin_impl import user_script_list
from flow_engine.starlark_sdk.registry_data import load_registry
from flow_engine.starlark_sdk.runtime import runtime_stats, warmup_runtime
from flow_engine.starlark_sdk.uri_resolve import resolve_internal_script_file, resolve_user_script_file
from flow_engine.lookup_import import rows_from_bytes
from flow_engine.lookup_service import merge_imported_rows, put_table
from flow_engine.lookup_store import LookupStoreError, get_lookup_store, validate_lookup_namespace
from flow_engine.yaml_store import FlowYamlStore, validate_flow_id

store = FlowYamlStore()


class CreateFlowBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    name: str | None = None


class DebugNodeBody(BaseModel):
    script: str
    boundary_inputs: dict[str, str] = Field(default_factory=dict)
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
    module_ids: list[str] = Field(default_factory=list, description='e.g. ["internal://lib/helpers.star"]')
    script_samples: list[str] = Field(default_factory=list, description="optional script samples for AST warmup")


def create_app() -> FastAPI:
    app = FastAPI(title="Flow Engine API", version="0.2.0")

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

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/flows")
    def list_flows() -> dict[str, Any]:
        flows = store.list_flows()
        return {
            "flows": [
                {
                    "id": f.id,
                    "name": f.name,
                    "path": f.path,
                    "updated_at": f.updated_at,
                }
                for f in flows
            ],
            "flows_dir": str(store.directory),
        }

    @app.get("/api/flows/{flow_id}")
    def get_flow(flow_id: str) -> dict[str, Any]:
        try:
            validate_flow_id(flow_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        try:
            return store.read_raw(flow_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Flow not found") from None

    @app.put("/api/flows/{flow_id}")
    def put_flow(flow_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            validate_flow_id(flow_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        try:
            compiled = compile_flow(FlowDefinition.model_validate(body))
            store.write_raw(flow_id, compiled.model_dump(mode="json", exclude_none=True))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Validation failed: {e}") from e
        return {"ok": True, "id": flow_id}

    @app.post("/api/flows")
    def create_flow(body: CreateFlowBody) -> dict[str, Any]:
        try:
            fid = validate_flow_id(body.id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if store.exists(fid):
            raise HTTPException(status_code=409, detail="Flow id already exists")
        name = body.name or fid
        minimal = FlowDefinition(
            name=name,
            version="1.0.0",
            strategies={
                "default_sync": ExecutionStrategy(name="default_sync", mode=StrategyMode.SYNC),
            },
            nodes=[],
        )
        compiled = compile_flow(minimal)
        store.write_raw(fid, compiled.model_dump(mode="json", exclude_none=True))
        return {"ok": True, "id": fid}

    @app.delete("/api/flows/{flow_id}")
    def delete_flow(flow_id: str) -> dict[str, Any]:
        try:
            validate_flow_id(flow_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not store.exists(flow_id):
            raise HTTPException(status_code=404, detail="Flow not found")
        store.delete(flow_id)
        return {"ok": True}

    @app.get("/api/dict")
    def get_data_dictionary() -> dict[str, Any]:
        st = data_dict.store()
        return {
            "dict_dir": str(st.directory),
            "tree": st.read_tree(),
            "yaml": st.read_raw(),
        }

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
        from flow_engine.lookup_service import lookup_query as run_lookup_query

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

    @app.post("/api/debug/node")
    def debug_node(body: DebugNodeBody) -> JSONResponse:
        ctx = ContextStack()
        ctx.global_ns.update(body.initial_context or {})
        try:
            result = run_task_script(body.script, ctx, body.boundary_inputs)
            return JSONResponse(content={"ok": True, "result": result})
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                status_code=200,
                content={
                    "ok": False,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                },
            )

    @app.post("/api/flows/{flow_id}/validate")
    def validate_flow_file(flow_id: str) -> dict[str, Any]:
        try:
            validate_flow_id(flow_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not store.exists(flow_id):
            raise HTTPException(status_code=404, detail="Flow not found")
        try:
            flow = load_flow_from_yaml(store.path_for(flow_id))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "name": flow.name, "version": flow.version}

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "flow_engine.http_api:app",
        host="127.0.0.1",
        port=int(__import__("os").environ.get("FLOW_ENGINE_PORT", "8000")),
        reload=__import__("os").environ.get("FLOW_ENGINE_RELOAD", "").lower() in ("1", "true", "yes"),
    )


if __name__ == "__main__":
    main()
