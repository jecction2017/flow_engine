"""HTTP ConnectorBackend implementation."""

from __future__ import annotations

from typing import Any

from flow_engine.connectors.backends.http.api_caller import ApiCaller
from flow_engine.connectors.backends.http.auth_providers import build_auth_handlers
from flow_engine.connectors.config import ProtectionSpec
from flow_engine.connectors.config_http import HttpInstanceSpec
from flow_engine.connectors.correlation import get_integration_correlation_id
from flow_engine.connectors.errors import ConnectorError
from flow_engine.connectors.protection.pipeline import ProtectionPipeline, RequestContext
from flow_engine.connectors.protocol import ConnectorHandle


class HttpHandle:
    kind = "http"

    def __init__(
        self,
        instance_id: str,
        spec: HttpInstanceSpec,
        pipeline: ProtectionPipeline,
    ) -> None:
        self.instance_id = instance_id
        self._spec = spec
        self._pipeline = pipeline
        self._caller = ApiCaller(
            instance_id=instance_id,
            spec=spec,
            auth_handlers=build_auth_handlers(spec.auth_providers),
        )

    def execute(self, operation: str, **params: Any) -> dict[str, Any]:
        ctx = RequestContext(instance_id=self.instance_id, operation=operation)
        try:
            return self._pipeline.run(ctx, lambda: self._execute_inner(operation, **params))
        except RuntimeError as exc:
            code = str(exc)
            if code in {"CIRCUIT_OPEN", "CONNECTOR_RATE_LIMIT", "CONNECTOR_CONCURRENCY_LIMIT"}:
                return self._fail(
                    error_msg=code.replace("_", " ").lower(),
                    error_code=code,
                )
            raise
        except TimeoutError as exc:
            return self._fail(error_msg=str(exc), error_code="CONNECTOR_TIMEOUT")
        except ConnectorError as exc:
            return self._fail(error_msg=str(exc), error_code=exc.code)
        except Exception as exc:  # noqa: BLE001
            return self._fail(error_msg=str(exc), error_code="HTTP_CONNECTOR_ERROR")

    def _execute_inner(self, operation: str, **params: Any) -> dict[str, Any]:
        if operation != "call":
            raise ConnectorError(f"unknown operation {operation!r}", code="UNKNOWN_OPERATION")
        result = self._caller.call(
            service_name=str(params["service_name"]),
            endpoint_name=str(params["endpoint_name"]),
            path_params=params.get("path_params"),
            query_params=params.get("query_params"),
            header_params=params.get("header_params"),
            method=params.get("method"),
            body=params.get("body"),
            json_body=params.get("json"),
            timeout_ms=params.get("timeout_ms"),
            auth_override=params.get("auth_override"),
        )
        payload = result.to_dict()
        meta = dict(payload.get("meta") or {})
        meta.setdefault("instance", self.instance_id)
        meta.setdefault("correlation_id", get_integration_correlation_id())
        payload["meta"] = meta
        return payload

    def _fail(self, *, error_msg: str, error_code: str) -> dict[str, Any]:
        return {
            "success": False,
            "data": None,
            "error_msg": error_msg,
            "error_code": error_code,
            "status_code": None,
            "cost_ms": 0.0,
            "meta": {
                "instance": self.instance_id,
                "correlation_id": get_integration_correlation_id(),
            },
        }

    def close(self) -> None:
        return


class HttpBackend:
    kind = "http"

    def __init__(self) -> None:
        self._handles: dict[str, HttpHandle] = {}

    def bind_instances(
        self,
        instances: dict[str, dict[str, Any]],
        *,
        defaults: dict[str, Any],
    ) -> dict[str, ConnectorHandle]:
        out: dict[str, ConnectorHandle] = {}
        base_protection = ProtectionSpec.model_validate(defaults.get("protection") or {})
        for iid, raw in instances.items():
            spec = HttpInstanceSpec.model_validate(raw)
            inst_protection = spec.protection
            protection = (
                base_protection.model_copy(update=inst_protection.model_dump())
                if inst_protection is not None
                else base_protection
            )
            pipeline = ProtectionPipeline(
                protection,
                request_timeout_sec=float(spec.base.request_timeout_sec),
            )
            handle = HttpHandle(iid, spec, pipeline)
            self._handles[iid] = handle
            out[iid] = handle
        return out

    def close_all(self) -> None:
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()
