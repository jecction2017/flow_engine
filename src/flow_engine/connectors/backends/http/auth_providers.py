"""Authentication providers for HTTP connector."""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from flow_engine.connectors.config_http import HttpAuthProviderSpec
from flow_engine.connectors.errors import ConnectorError


class BaseAuth(ABC):
    @abstractmethod
    def apply(self, headers: dict[str, str]) -> None:
        """Mutate outgoing headers before request is sent."""


class NoneAuthHandler(BaseAuth):
    def apply(self, headers: dict[str, str]) -> None:  # noqa: ARG002
        return


class IAMAuthHandler(BaseAuth):
    """Fetch-and-cache IAM token using client credentials style flow."""

    def __init__(self, name: str, spec: HttpAuthProviderSpec) -> None:
        self._name = name
        self._spec = spec
        self._lock = threading.RLock()
        self._token: str | None = None
        self._expires_at: float = 0.0

    def apply(self, headers: dict[str, str]) -> None:
        token = self._get_token()
        prefix = (self._spec.token_prefix or "").strip()
        token_value = f"{prefix} {token}".strip()
        headers[str(self._spec.header_name)] = token_value

    def _get_token(self) -> str:
        now = time.monotonic()
        with self._lock:
            if self._token and now < self._expires_at:
                return self._token
            token, ttl = self._fetch_token()
            self._token = token
            self._expires_at = now + max(5.0, float(ttl) - 5.0)
            return token

    def _fetch_token(self) -> tuple[str, int]:
        if not self._spec.token_url:
            raise ConnectorError(
                f"iam auth provider {self._name!r} missing token_url",
                code="AUTH_CONFIG_INVALID",
            )
        payload: dict[str, Any] = {
            "grant_type": "client_credentials",
            "client_id": self._spec.client_id or "",
            "client_secret": self._spec.client_secret or "",
        }
        if self._spec.scope:
            payload["scope"] = self._spec.scope
        if self._spec.audience:
            payload["audience"] = self._spec.audience
        if self._spec.extra:
            payload.update(self._spec.extra)
        encoded = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            self._spec.token_url,
            method="POST",
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                body = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            raise ConnectorError(
                f"iam token fetch failed for provider {self._name!r}: {exc}",
                code="AUTH_FETCH_FAILED",
            ) from exc
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ConnectorError(
                f"iam token response is not JSON for provider {self._name!r}",
                code="AUTH_FETCH_FAILED",
            ) from exc
        token = parsed.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise ConnectorError(
                f"iam token response missing access_token for provider {self._name!r}",
                code="AUTH_FETCH_FAILED",
            )
        expires_in_raw = parsed.get("expires_in", self._spec.ttl_sec)
        try:
            expires_in = int(expires_in_raw)
        except (TypeError, ValueError):
            expires_in = self._spec.ttl_sec
        return token, min(expires_in, int(self._spec.ttl_sec))


class SOAAuthHandler(BaseAuth):
    def __init__(self, name: str, spec: HttpAuthProviderSpec) -> None:
        self._name = name
        self._spec = spec

    def apply(self, headers: dict[str, str]) -> None:  # noqa: ARG002
        raise ConnectorError(
            f"auth provider {self._name!r} type {self._spec.type!r} is not implemented yet",
            code="AUTH_NOT_IMPLEMENTED",
        )


class APIGAuthHandler(BaseAuth):
    def __init__(self, name: str, spec: HttpAuthProviderSpec) -> None:
        self._name = name
        self._spec = spec

    def apply(self, headers: dict[str, str]) -> None:  # noqa: ARG002
        raise ConnectorError(
            f"auth provider {self._name!r} type {self._spec.type!r} is not implemented yet",
            code="AUTH_NOT_IMPLEMENTED",
        )


def build_auth_handlers(providers: dict[str, HttpAuthProviderSpec]) -> dict[str, BaseAuth]:
    out: dict[str, BaseAuth] = {}
    for name, spec in providers.items():
        if spec.type == "none":
            out[name] = NoneAuthHandler()
        elif spec.type == "iam":
            out[name] = IAMAuthHandler(name, spec)
        elif spec.type == "soa":
            out[name] = SOAAuthHandler(name, spec)
        elif spec.type == "apig":
            out[name] = APIGAuthHandler(name, spec)
        else:
            raise ConnectorError(
                f"unsupported auth provider type {spec.type!r} for {name!r}",
                code="AUTH_CONFIG_INVALID",
            )
    return out
