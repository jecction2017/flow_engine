"""Models used by HTTP connector backend internals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OutboundRequest:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body_bytes: bytes | None = None
    timeout_sec: float = 30.0
    verify_ssl: bool = True


@dataclass
class ResponseResult:
    success: bool
    data: Any = None
    error_msg: str | None = None
    error_code: str | None = None
    status_code: int | None = None
    cost_ms: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error_msg": self.error_msg,
            "error_code": self.error_code,
            "status_code": self.status_code,
            "cost_ms": self.cost_ms,
            "meta": dict(self.meta),
        }
