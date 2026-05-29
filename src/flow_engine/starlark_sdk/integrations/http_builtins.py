"""Starlark builtins for config-driven HTTP API calls."""

from __future__ import annotations

from typing import Any

from flow_engine.starlark_sdk.builtin_registry import BuiltinArgSpec, PythonBuiltinSpec, register_builtin
from flow_engine.starlark_sdk.integrations._http_helpers import run_http_operation

_HTTP_SUPPRESSED: dict[str, Any] = {
    "success": False,
    "data": None,
    "error_msg": "integration suppressed",
    "error_code": "SUPPRESSED",
    "status_code": None,
    "cost_ms": 0.0,
    "meta": {"_suppressed": True},
}


@register_builtin(
    PythonBuiltinSpec(
        id="python://http/call",
        starlark_name="http_call",
        category="integration",
        summary="配置驱动 HTTP 调用（service/endpoint）",
        signature=(
            BuiltinArgSpec(name="service_name", type="str"),
            BuiltinArgSpec(name="endpoint_name", type="str"),
            BuiltinArgSpec(name="instance", type="str", required=False),
            BuiltinArgSpec(name="path_params", type="dict", required=False),
            BuiltinArgSpec(name="query_params", type="dict", required=False),
            BuiltinArgSpec(name="header_params", type="dict", required=False),
            BuiltinArgSpec(name="method", type="str", required=False),
            BuiltinArgSpec(name="body", type="any", required=False),
            BuiltinArgSpec(name="json", type="any", required=False),
            BuiltinArgSpec(name="timeout_ms", type="int", required=False),
            BuiltinArgSpec(name="auth_override", type="str", required=False),
        ),
        returns="dict",
        side_effects="network",
        suppress_result=_HTTP_SUPPRESSED,
    )
)
def http_call(
    service_name: str,
    endpoint_name: str,
    instance: str = "main",
    path_params: dict[str, Any] | None = None,
    query_params: dict[str, Any] | None = None,
    header_params: dict[str, Any] | None = None,
    method: str | None = None,
    body: Any = None,
    json: Any = None,  # noqa: A002
    timeout_ms: int | None = None,
    auth_override: str | None = None,
) -> dict[str, Any]:
    return run_http_operation(
        instance,
        "call",
        service_name=service_name,
        endpoint_name=endpoint_name,
        path_params=path_params,
        query_params=query_params,
        header_params=header_params,
        method=method,
        body=body,
        json=json,
        timeout_ms=timeout_ms,
        auth_override=auth_override,
    )
