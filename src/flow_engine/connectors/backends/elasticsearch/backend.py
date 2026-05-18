"""Elasticsearch ConnectorBackend implementation."""

from __future__ import annotations

import time
from typing import Any

from flow_engine.connectors.backends.elasticsearch import operations as es_ops
from flow_engine.connectors.backends.elasticsearch.client_factory import (
    close_client,
    create_client,
    merged_protection,
)
from flow_engine.connectors.config import ElasticsearchInstanceSpec, ProtectionSpec
from flow_engine.connectors.errors import ConnectorError, err_envelope, ok_envelope
from flow_engine.connectors.protection.pipeline import ProtectionPipeline, RequestContext
from flow_engine.connectors.protocol import ConnectorHandle


class ElasticsearchHandle:
    kind = "elasticsearch"

    def __init__(
        self,
        instance_id: str,
        client: Any,
        pipeline: ProtectionPipeline,
        allowed_index_patterns: list[str] | None,
    ) -> None:
        self.instance_id = instance_id
        self._client = client
        self._pipeline = pipeline
        self._allowed = allowed_index_patterns

    def execute(self, operation: str, **params: Any) -> dict[str, Any]:
        ctx = RequestContext(instance_id=self.instance_id, operation=operation)
        try:
            return self._pipeline.run(ctx, lambda: self._execute_inner(operation, **params))
        except RuntimeError as exc:
            code = str(exc)
            if code in {"CIRCUIT_OPEN", "CONNECTOR_RATE_LIMIT", "CONNECTOR_CONCURRENCY_LIMIT"}:
                return err_envelope(code, code.replace("_", " ").lower(), instance=self.instance_id)
            raise
        except TimeoutError as exc:
            return err_envelope("CONNECTOR_TIMEOUT", str(exc), instance=self.instance_id)
        except ConnectorError as exc:
            return err_envelope(exc.code, str(exc), instance=self.instance_id)
        except Exception as exc:  # noqa: BLE001
            return err_envelope("ES_ERROR", str(exc), instance=self.instance_id)

    def _execute_inner(self, operation: str, **params: Any) -> dict[str, Any]:
        t0 = time.monotonic()
        if operation == "search":
            data = es_ops.search(
                self._client,
                index=params["index"],
                body=params.get("body"),
                query=params.get("query"),
                size=params["size"],
                allowed_patterns=self._allowed,
            )
        elif operation == "mget":
            data = es_ops.mget(
                self._client,
                index=params["index"],
                ids=params["ids"],
                allowed_patterns=self._allowed,
            )
        elif operation == "count":
            data = es_ops.count(
                self._client,
                index=params["index"],
                body=params.get("body"),
                query=params.get("query"),
                allowed_patterns=self._allowed,
            )
        elif operation == "scroll":
            data = es_ops.scroll_search(
                self._client,
                index=params["index"],
                body=params.get("body"),
                query=params.get("query"),
                size=params["size"],
                max_pages=params["max_pages"],
                scroll_ttl=params.get("scroll_ttl", "1m"),
                allowed_patterns=self._allowed,
            )
        elif operation == "index_document":
            data = es_ops.index_document(
                self._client,
                index=params["index"],
                doc_id=params["doc_id"],
                document=params["document"],
            )
        elif operation == "delete_document":
            data = es_ops.delete_document(
                self._client,
                index=params["index"],
                doc_id=params["doc_id"],
            )
        elif operation == "bulk_update":
            data = es_ops.bulk_update_documents(
                self._client,
                index=params["index"],
                operations=params["operations"],
            )
        else:
            raise ConnectorError(f"unknown operation {operation!r}", code="UNKNOWN_OPERATION")

        took_ms = (time.monotonic() - t0) * 1000.0
        return ok_envelope(data, instance=self.instance_id, took_ms=took_ms)

    def cap_size(self, size: int | None) -> int:
        return self._pipeline.cap_size(size)

    def cap_scroll_pages(self, pages: int | None) -> int:
        return self._pipeline.cap_scroll_pages(pages)

    def close(self) -> None:
        close_client(self._client)


class ElasticsearchBackend:
    kind = "elasticsearch"

    def __init__(self) -> None:
        self._clients: dict[str, ElasticsearchHandle] = {}

    def bind_instances(
        self,
        instances: dict[str, dict[str, Any]],
        *,
        defaults: dict[str, Any],
    ) -> dict[str, ConnectorHandle]:
        out: dict[str, ConnectorHandle] = {}
        default_timeout = float(defaults.get("request_timeout_sec", 30))

        for iid, raw in instances.items():
            spec = ElasticsearchInstanceSpec.model_validate(raw)
            timeout = spec.request_timeout_sec or default_timeout
            prot = merged_protection(defaults, raw)
            pipeline = ProtectionPipeline(prot, request_timeout_sec=timeout)
            client = create_client(spec, request_timeout_sec=timeout)
            handle = ElasticsearchHandle(
                iid,
                client,
                pipeline,
                spec.allowed_index_patterns,
            )
            self._clients[iid] = handle
            out[iid] = handle
        return out

    def close_all(self) -> None:
        for handle in self._clients.values():
            handle.close()
        self._clients.clear()
