"""Starlark builtins for read-only Elasticsearch operations."""

from __future__ import annotations

from typing import Any

from flow_engine.connectors.registry import get_registry
from flow_engine.starlark_sdk.builtin_registry import BuiltinArgSpec, PythonBuiltinSpec, register_builtin
from flow_engine.starlark_sdk.integrations._es_helpers import run_es_operation

_ES_SUPPRESSED: dict[str, Any] = {
    "ok": False,
    "error": {"code": "SUPPRESSED", "message": "integration suppressed"},
    "_suppressed": True,
}


@register_builtin(
    PythonBuiltinSpec(
        id="python://elasticsearch/search",
        starlark_name="es_search",
        category="integration",
        summary="Elasticsearch search（只读）",
        signature=(
            BuiltinArgSpec(name="instance", type="str"),
            BuiltinArgSpec(name="index", type="str"),
            BuiltinArgSpec(name="body", type="dict", required=False),
            BuiltinArgSpec(name="query", type="dict", required=False),
            BuiltinArgSpec(name="size", type="int", required=False),
        ),
        returns="dict",
        side_effects="network",
        suppress_result=_ES_SUPPRESSED,
    )
)
def es_search(
    instance: str,
    index: str,
    body: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    size: int | None = None,
) -> dict[str, Any]:
    reg = get_registry()
    reg.ensure_bound()
    cap_size = size or 1000
    try:
        handle = reg.get("elasticsearch", instance)
        cap_size = handle.cap_size(size)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    return run_es_operation(
        instance,
        "search",
        index=index,
        body=body,
        query=query,
        size=cap_size or 1000,
    )


@register_builtin(
    PythonBuiltinSpec(
        id="python://elasticsearch/mget",
        starlark_name="es_mget",
        category="integration",
        summary="Elasticsearch mget（只读）",
        signature=(
            BuiltinArgSpec(name="instance", type="str"),
            BuiltinArgSpec(name="index", type="str"),
            BuiltinArgSpec(name="ids", type="list"),
        ),
        returns="dict",
        side_effects="network",
        suppress_result=_ES_SUPPRESSED,
    )
)
def es_mget(instance: str, index: str, ids: list[Any]) -> dict[str, Any]:
    str_ids = [str(i) for i in ids]
    return run_es_operation(instance, "mget", index=index, ids=str_ids)


@register_builtin(
    PythonBuiltinSpec(
        id="python://elasticsearch/count",
        starlark_name="es_count",
        category="integration",
        summary="Elasticsearch count（只读）",
        signature=(
            BuiltinArgSpec(name="instance", type="str"),
            BuiltinArgSpec(name="index", type="str"),
            BuiltinArgSpec(name="body", type="dict", required=False),
            BuiltinArgSpec(name="query", type="dict", required=False),
        ),
        returns="dict",
        side_effects="network",
        suppress_result=_ES_SUPPRESSED,
    )
)
def es_count(
    instance: str,
    index: str,
    body: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return run_es_operation(instance, "count", index=index, body=body, query=query)


@register_builtin(
    PythonBuiltinSpec(
        id="python://elasticsearch/scroll",
        starlark_name="es_scroll",
        category="integration",
        summary="Elasticsearch scroll 查询（只读，受 max_scroll_pages 限制）",
        signature=(
            BuiltinArgSpec(name="instance", type="str"),
            BuiltinArgSpec(name="index", type="str"),
            BuiltinArgSpec(name="body", type="dict", required=False),
            BuiltinArgSpec(name="query", type="dict", required=False),
            BuiltinArgSpec(name="size", type="int", required=False),
            BuiltinArgSpec(name="scroll_ttl", type="str", required=False),
        ),
        returns="dict",
        side_effects="network",
        suppress_result=_ES_SUPPRESSED,
    )
)
def es_scroll(
    instance: str,
    index: str,
    body: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    size: int | None = None,
    scroll_ttl: str = "1m",
) -> dict[str, Any]:
    reg = get_registry()
    reg.ensure_bound()
    max_pages = 10
    cap_size = size or 1000
    try:
        handle = reg.get("elasticsearch", instance)
        max_pages = handle.cap_scroll_pages(None)  # type: ignore[attr-defined]
        cap_size = handle.cap_size(size)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    return run_es_operation(
        instance,
        "scroll",
        index=index,
        body=body,
        query=query,
        size=cap_size,
        max_pages=max_pages,
        scroll_ttl=scroll_ttl,
    )
