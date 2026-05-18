"""Example business write operations for users (fixed index, audited)."""

from __future__ import annotations

import logging
from typing import Any

from flow_engine.connectors.backends.elasticsearch.operations import USER_ID_FIELD, USER_INDEX
from flow_engine.connectors.correlation import get_integration_correlation_id
from flow_engine.connectors.errors import err_envelope
from flow_engine.connectors.registry import get_registry
from flow_engine.starlark_sdk.builtin_registry import BuiltinArgSpec, PythonBuiltinSpec, register_builtin
from flow_engine.starlark_sdk.integrations._es_helpers import run_es_operation

logger = logging.getLogger(__name__)

_DB_WRITE_SUPPRESSED: dict[str, Any] = {
    "ok": False,
    "error": {"code": "SUPPRESSED", "message": "db_write suppressed"},
    "_suppressed": True,
}


def _audit(operation: str, instance: str, **fields: Any) -> None:
    logger.info(
        "business_es_audit",
        extra={
            "operation": operation,
            "instance": instance,
            "correlation_id": get_integration_correlation_id(),
            **fields,
        },
    )


def _require_doc_id(user_doc: dict[str, Any]) -> str:
    uid = user_doc.get(USER_ID_FIELD) or user_doc.get("id")
    if uid is None:
        raise ValueError(f"user_doc must contain {USER_ID_FIELD!r} or 'id'")
    return str(uid)


@register_builtin(
    PythonBuiltinSpec(
        id="python://business/user_create",
        starlark_name="user_create",
        category="db_write",
        summary="创建用户文档（固定索引 flow_users）",
        signature=(
            BuiltinArgSpec(name="instance", type="str"),
            BuiltinArgSpec(name="user_doc", type="dict"),
        ),
        returns="dict",
        side_effects="network",
        suppress_result=_DB_WRITE_SUPPRESSED,
    )
)
def user_create(instance: str, user_doc: dict[str, Any]) -> dict[str, Any]:
    if not get_registry().elasticsearch_available:
        return err_envelope(
            "INTEGRATION_UNAVAILABLE",
            "elasticsearch not available",
            instance=instance,
        )
    try:
        doc_id = _require_doc_id(user_doc)
    except ValueError as exc:
        return err_envelope("INVALID_ARGUMENT", str(exc), instance=instance)
    _audit("user_create", instance, user_id=doc_id, index=USER_INDEX)
    return run_es_operation(
        instance,
        "index_document",
        index=USER_INDEX,
        doc_id=doc_id,
        document=dict(user_doc),
    )


@register_builtin(
    PythonBuiltinSpec(
        id="python://business/user_delete",
        starlark_name="user_delete",
        category="db_write",
        summary="删除用户文档（固定索引 flow_users）",
        signature=(
            BuiltinArgSpec(name="instance", type="str"),
            BuiltinArgSpec(name="user_id", type="str"),
        ),
        returns="dict",
        side_effects="network",
        suppress_result=_DB_WRITE_SUPPRESSED,
    )
)
def user_delete(instance: str, user_id: str) -> dict[str, Any]:
    if not get_registry().elasticsearch_available:
        return err_envelope("INTEGRATION_UNAVAILABLE", "elasticsearch not available", instance=instance)
    _audit("user_delete", instance, user_id=user_id, index=USER_INDEX)
    return run_es_operation(
        instance,
        "delete_document",
        index=USER_INDEX,
        doc_id=str(user_id),
    )


@register_builtin(
    PythonBuiltinSpec(
        id="python://business/user_bulk_update",
        starlark_name="user_bulk_update",
        category="db_write",
        summary="批量更新用户文档（固定索引 flow_users）",
        signature=(
            BuiltinArgSpec(name="instance", type="str"),
            BuiltinArgSpec(name="patches", type="list"),
        ),
        returns="dict",
        side_effects="network",
        suppress_result=_DB_WRITE_SUPPRESSED,
    )
)
def user_bulk_update(instance: str, patches: list[Any]) -> dict[str, Any]:
    if not get_registry().elasticsearch_available:
        return err_envelope("INTEGRATION_UNAVAILABLE", "elasticsearch not available", instance=instance)
    ops: list[dict[str, Any]] = []
    for p in patches:
        if isinstance(p, dict):
            ops.append(p)
    _audit("user_bulk_update", instance, count=len(ops), index=USER_INDEX)
    return run_es_operation(
        instance,
        "bulk_update",
        index=USER_INDEX,
        operations=ops,
    )
