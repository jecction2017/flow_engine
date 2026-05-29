"""Core HTTP request caller with configuration layering."""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from flow_engine.connectors.backends.http.api_response import ApiResponseProcessor
from flow_engine.connectors.backends.http.auth_providers import BaseAuth
from flow_engine.connectors.backends.http.models import OutboundRequest, ResponseResult
from flow_engine.connectors.config_http import HttpInstanceSpec
from flow_engine.connectors.errors import ConnectorError


class ApiCaller:
    """Configuration-driven HTTP caller for a single connector instance."""

    def __init__(
        self,
        instance_id: str,
        spec: HttpInstanceSpec,
        auth_handlers: dict[str, BaseAuth],
    ) -> None:
        self._instance_id = instance_id
        self._spec = spec
        self._auth_handlers = auth_handlers
        self._response_processor = ApiResponseProcessor()

    def call(
        self,
        *,
        service_name: str,
        endpoint_name: str,
        path_params: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        header_params: dict[str, Any] | None = None,
        method: str | None = None,
        body: Any = None,
        json_body: Any = None,
        timeout_ms: int | None = None,
        auth_override: str | None = None,
    ) -> ResponseResult:
        service = self._spec.services.get(service_name)
        if service is None:
            raise ConnectorError(f"unknown service {service_name!r}", code="SERVICE_NOT_FOUND")
        endpoint = service.endpoints.get(endpoint_name)
        if endpoint is None:
            raise ConnectorError(
                f"unknown endpoint {endpoint_name!r} in service {service_name!r}",
                code="ENDPOINT_NOT_FOUND",
            )

        req_method = (method or endpoint.method).upper()
        timeout_sec = self._resolve_timeout_sec(service.request_timeout_sec, endpoint.request_timeout_sec, timeout_ms)
        retries = int(self._spec.base.retries)
        backoff_sec = float(self._spec.base.retry_backoff_sec)

        request = self._build_request(
            method=req_method,
            service_name=service_name,
            endpoint_name=endpoint_name,
            path_template=endpoint.path,
            service_base_url=service.base_url,
            endpoint_query_defaults=endpoint.query_defaults,
            path_params=path_params,
            query_params=query_params,
            header_params=header_params,
            service_headers=service.common_headers,
            endpoint_headers=endpoint.extra_headers,
            body=body,
            json_body=json_body,
            timeout_sec=timeout_sec,
        )

        provider_name = auth_override or endpoint.auth_provider or service.auth_provider
        if provider_name:
            auth = self._auth_handlers.get(provider_name)
            if auth is None:
                raise ConnectorError(
                    f"unknown auth provider {provider_name!r} in instance {self._instance_id!r}",
                    code="AUTH_PROVIDER_NOT_FOUND",
                )
            auth.apply(request.headers)

        return self._send_with_retry(request, retries=retries, backoff_sec=backoff_sec)

    def _resolve_timeout_sec(
        self,
        service_timeout: float | None,
        endpoint_timeout: float | None,
        timeout_ms: int | None,
    ) -> float:
        timeout_sec = float(self._spec.base.request_timeout_sec)
        if service_timeout is not None:
            timeout_sec = float(service_timeout)
        if endpoint_timeout is not None:
            timeout_sec = float(endpoint_timeout)
        if timeout_ms is not None:
            timeout_sec = max(0.1, float(timeout_ms) / 1000.0)
        return timeout_sec

    def _build_request(
        self,
        *,
        method: str,
        service_name: str,
        endpoint_name: str,
        path_template: str,
        service_base_url: str,
        endpoint_query_defaults: dict[str, str],
        path_params: dict[str, Any] | None,
        query_params: dict[str, Any] | None,
        header_params: dict[str, Any] | None,
        service_headers: dict[str, str],
        endpoint_headers: dict[str, str],
        body: Any,
        json_body: Any,
        timeout_sec: float,
    ) -> OutboundRequest:
        try:
            resolved_path = path_template.format_map({k: str(v) for k, v in (path_params or {}).items()})
        except KeyError as exc:
            raise ConnectorError(
                f"missing path param {exc.args[0]!r} for {service_name}.{endpoint_name}",
                code="INVALID_PATH_PARAMS",
            ) from exc

        base_url = service_base_url.rstrip("/")
        final_url = f"{base_url}/{resolved_path.lstrip('/')}"
        merged_query = dict(endpoint_query_defaults or {})
        if query_params:
            merged_query.update({str(k): str(v) for k, v in query_params.items()})
        if merged_query:
            final_url = f"{final_url}?{urllib.parse.urlencode(merged_query, doseq=True)}"

        headers: dict[str, str] = {}
        headers.update({str(k): str(v) for k, v in (self._spec.base.default_headers or {}).items()})
        headers.update({str(k): str(v) for k, v in (service_headers or {}).items()})
        headers.update({str(k): str(v) for k, v in (endpoint_headers or {}).items()})
        if header_params:
            headers.update({str(k): str(v) for k, v in header_params.items()})

        body_bytes: bytes | None = None
        if json_body is not None:
            body_bytes = json.dumps(json_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif body is not None:
            if isinstance(body, bytes):
                body_bytes = body
            else:
                body_bytes = str(body).encode("utf-8")

        return OutboundRequest(
            method=method,
            url=final_url,
            headers=headers,
            body_bytes=body_bytes,
            timeout_sec=timeout_sec,
            verify_ssl=bool(self._spec.base.verify_ssl),
        )

    def _send_with_retry(
        self,
        request: OutboundRequest,
        *,
        retries: int,
        backoff_sec: float,
    ) -> ResponseResult:
        started = time.monotonic()
        attempts = max(0, retries) + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                status, content_type, body_bytes = self._send_once(request)
                took = (time.monotonic() - started) * 1000.0
                return self._response_processor.process(
                    status_code=status,
                    content_type=content_type,
                    body_bytes=body_bytes,
                    cost_ms=took,
                    meta={"attempt": attempt + 1, "url": request.url, "method": request.method},
                )
            except urllib.error.HTTPError as exc:
                body_bytes = exc.read()
                took = (time.monotonic() - started) * 1000.0
                return self._response_processor.process(
                    status_code=int(exc.code),
                    content_type=str(exc.headers.get("Content-Type", "")),
                    body_bytes=body_bytes,
                    cost_ms=took,
                    meta={"attempt": attempt + 1, "url": request.url, "method": request.method},
                )
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                if backoff_sec > 0:
                    time.sleep(backoff_sec * (attempt + 1))
        took = (time.monotonic() - started) * 1000.0
        return ResponseResult(
            success=False,
            data=None,
            error_msg=str(last_error) if last_error else "http request failed",
            error_code="TRANSPORT_ERROR",
            status_code=None,
            cost_ms=took,
            meta={"url": request.url, "method": request.method},
        )

    @staticmethod
    def _send_once(request: OutboundRequest) -> tuple[int, str, bytes]:
        req = urllib.request.Request(
            request.url,
            method=request.method,
            data=request.body_bytes,
            headers=request.headers,
        )
        context = None
        if not request.verify_ssl:
            context = ssl._create_unverified_context()  # noqa: SLF001
        with urllib.request.urlopen(req, timeout=request.timeout_sec, context=context) as resp:  # noqa: S310
            body_bytes = resp.read()
            return int(resp.status), str(resp.headers.get("Content-Type", "")), body_bytes
