"""Elasticsearch read/write operations (write used only from business layer)."""

from __future__ import annotations

import fnmatch
from typing import Any

from flow_engine.connectors.errors import ConnectorError


def _validate_index(index: str, allowed_patterns: list[str] | None) -> None:
    if not index or not index.strip():
        raise ConnectorError("index must be non-empty", code="INVALID_INDEX")
    if allowed_patterns:
        if not any(fnmatch.fnmatch(index, pat) for pat in allowed_patterns):
            raise ConnectorError(
                f"index {index!r} not allowed by instance policy",
                code="INDEX_NOT_ALLOWED",
            )


def _reject_script_fields(body: dict[str, Any] | None) -> None:
    if not body:
        return
    if "script" in body or "script_fields" in body:
        raise ConnectorError("script fields are not allowed in user queries", code="SCRIPT_FORBIDDEN")
    query = body.get("query")
    if isinstance(query, dict) and "script" in query:
        raise ConnectorError("script queries are not allowed", code="SCRIPT_FORBIDDEN")


def search(
    client: Any,
    *,
    index: str,
    body: dict[str, Any] | None,
    query: dict[str, Any] | None,
    size: int,
    allowed_patterns: list[str] | None,
) -> dict[str, Any]:
    _validate_index(index, allowed_patterns)
    req: dict[str, Any] = {"size": size}
    if body:
        _reject_script_fields(body)
        req.update(body)
    if query is not None:
        req["query"] = query
    if "size" in req:
        req["size"] = min(size, int(req["size"]))
    else:
        req["size"] = size
    resp = client.search(index=index, body=req)
    return dict(resp) if hasattr(resp, "items") else resp


def mget(
    client: Any,
    *,
    index: str,
    ids: list[str],
    allowed_patterns: list[str] | None,
) -> dict[str, Any]:
    _validate_index(index, allowed_patterns)
    if not ids:
        return {"docs": []}
    resp = client.mget(index=index, body={"ids": ids})
    return dict(resp) if hasattr(resp, "items") else resp


def count(
    client: Any,
    *,
    index: str,
    body: dict[str, Any] | None,
    query: dict[str, Any] | None,
    allowed_patterns: list[str] | None,
) -> dict[str, Any]:
    _validate_index(index, allowed_patterns)
    req: dict[str, Any] = {}
    if body:
        _reject_script_fields(body)
        req.update(body)
    if query is not None:
        req["query"] = query
    if req:
        resp = client.count(index=index, body=req)
    else:
        resp = client.count(index=index)
    return dict(resp) if hasattr(resp, "items") else resp


def scroll_search(
    client: Any,
    *,
    index: str,
    body: dict[str, Any] | None,
    query: dict[str, Any] | None,
    size: int,
    max_pages: int,
    scroll_ttl: str,
    allowed_patterns: list[str] | None,
) -> dict[str, Any]:
    _validate_index(index, allowed_patterns)
    req: dict[str, Any] = {"size": size}
    if body:
        _reject_script_fields(body)
        req.update(body)
    if query is not None:
        req["query"] = query
    req["size"] = min(size, int(req.get("size", size)))

    first = client.search(index=index, body=req, scroll=scroll_ttl)
    first_dict = dict(first) if hasattr(first, "items") else first
    scroll_id = first_dict.get("_scroll_id")
    all_hits: list[Any] = list((first_dict.get("hits") or {}).get("hits") or [])
    pages = 1

    while scroll_id and pages < max_pages:
        nxt = client.scroll(scroll_id=scroll_id, scroll=scroll_ttl)
        nxt_dict = dict(nxt) if hasattr(nxt, "items") else nxt
        scroll_id = nxt_dict.get("_scroll_id")
        batch = (nxt_dict.get("hits") or {}).get("hits") or []
        if not batch:
            break
        all_hits.extend(batch)
        pages += 1

    if scroll_id:
        try:
            client.clear_scroll(scroll_id=scroll_id)
        except Exception:  # noqa: BLE001
            pass

    return {
        "hits": {"hits": all_hits, "total": (first_dict.get("hits") or {}).get("total")},
        "pages_fetched": pages,
        "_scroll_truncated": pages >= max_pages,
    }


# --- write operations (business layer only) ---

USER_INDEX = "flow_users"
USER_ID_FIELD = "user_id"


def index_document(
    client: Any,
    *,
    index: str,
    doc_id: str,
    document: dict[str, Any],
) -> dict[str, Any]:
    resp = client.index(index=index, id=doc_id, document=document)
    return dict(resp) if hasattr(resp, "items") else resp


def delete_document(
    client: Any,
    *,
    index: str,
    doc_id: str,
) -> dict[str, Any]:
    resp = client.delete(index=index, id=doc_id)
    return dict(resp) if hasattr(resp, "items") else resp


def bulk_update_documents(
    client: Any,
    *,
    index: str,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    from elasticsearch.helpers import bulk

    actions = []
    for op in operations:
        doc_id = op.get("id") or op.get(USER_ID_FIELD)
        if not doc_id:
            continue
        actions.append(
            {
                "_op_type": "update",
                "_index": index,
                "_id": str(doc_id),
                "doc": op.get("doc") or {},
            }
        )
    if not actions:
        return {"items": [], "errors": False}
    success, errors = bulk(client, actions, raise_on_error=False)
    return {"success": success, "errors": errors}
