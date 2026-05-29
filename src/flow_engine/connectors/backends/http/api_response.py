"""HTTP response normalization for the connector backend."""

from __future__ import annotations

import base64
import json
from typing import Any

from flow_engine.connectors.backends.http.models import ResponseResult


class ApiResponseProcessor:
    """Normalize status/body/content-type into one stable response model."""

    def process(
        self,
        *,
        status_code: int,
        content_type: str,
        body_bytes: bytes,
        cost_ms: float,
        meta: dict[str, Any] | None = None,
    ) -> ResponseResult:
        parsed = self._parse_body(content_type, body_bytes)
        out_meta = dict(meta or {})
        out_meta["content_type"] = content_type
        if status_code >= 400:
            return ResponseResult(
                success=False,
                data=parsed,
                error_msg=self._error_message(status_code, parsed),
                error_code="HTTP_STATUS_ERROR",
                status_code=status_code,
                cost_ms=cost_ms,
                meta=out_meta,
            )
        return ResponseResult(
            success=True,
            data=parsed,
            status_code=status_code,
            cost_ms=cost_ms,
            meta=out_meta,
        )

    @staticmethod
    def _error_message(status_code: int, parsed: Any) -> str:
        if isinstance(parsed, dict):
            for key in ("message", "error", "error_message", "detail"):
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return f"http status {status_code}"

    @staticmethod
    def _parse_body(content_type: str, body_bytes: bytes) -> Any:
        if not body_bytes:
            return None
        lowered = (content_type or "").lower()
        if "application/json" in lowered:
            try:
                return json.loads(body_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return body_bytes.decode("utf-8", errors="replace")
        if lowered.startswith("text/") or "xml" in lowered or "yaml" in lowered:
            return body_bytes.decode("utf-8", errors="replace")
        return {
            "encoding": "base64",
            "bytes": base64.b64encode(body_bytes).decode("ascii"),
        }
