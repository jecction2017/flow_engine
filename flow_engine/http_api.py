"""FastAPI HTTP service: YAML-backed flow CRUD + node debug."""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from flow_engine.compiler import compile_flow
from flow_engine.context import ContextStack
from flow_engine.loader import load_flow_from_yaml
from flow_engine.models import ExecutionStrategy, FlowDefinition, StrategyMode
from flow_engine.starlark_glue import run_task_script
from flow_engine.yaml_store import FlowYamlStore, validate_flow_id

store = FlowYamlStore()


class CreateFlowBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    name: str | None = None


class DebugNodeBody(BaseModel):
    script: str
    boundary_inputs: dict[str, str] = Field(default_factory=dict)
    initial_context: dict[str, Any] = Field(default_factory=dict)


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
