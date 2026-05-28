"""Pluggable Elasticsearch authentication strategies."""

from __future__ import annotations

from typing import Any, Callable

from flow_engine.connectors.config import AuthSpec
from flow_engine.connectors.errors import ConnectorError

AuthBuilder = Callable[[AuthSpec], dict[str, Any]]
_AUTH_BUILDERS: dict[str, AuthBuilder] = {}


def register_auth_strategy(auth_type: str, builder: AuthBuilder) -> None:
    key = auth_type.strip().lower()
    if not key:
        raise ConnectorError("auth type must be non-empty")
    _AUTH_BUILDERS[key] = builder


def build_client_auth(auth: AuthSpec) -> dict[str, Any]:
    builder = _AUTH_BUILDERS.get(auth.type)
    if builder is None:
        known = ", ".join(sorted(_AUTH_BUILDERS)) or "(none)"
        raise ConnectorError(f"Unknown auth type {auth.type!r}; registered: {known}", code="AUTH_UNKNOWN")
    return builder(auth)


def _build_none(_auth: AuthSpec) -> dict[str, Any]:
    return {}


def _build_basic(auth: AuthSpec) -> dict[str, Any]:
    if not auth.username:
        raise ConnectorError("basic auth requires username", code="AUTH_INVALID")
    return {
        "http_auth": (auth.username, auth.password or ""),
    }


def _build_api_key(auth: AuthSpec) -> dict[str, Any]:
    if not auth.api_key:
        raise ConnectorError("api_key auth requires api_key", code="AUTH_INVALID")
    return {"api_key": auth.api_key}


def _build_bearer(auth: AuthSpec) -> dict[str, Any]:
    if not auth.bearer_token:
        raise ConnectorError("bearer auth requires bearer_token", code="AUTH_INVALID")
    return {
        "headers": {"Authorization": f"Bearer {auth.bearer_token}"},
    }


def _build_certificate(auth: AuthSpec) -> dict[str, Any]:
    if not auth.client_cert or not auth.client_key:
        raise ConnectorError(
            "certificate auth requires client_cert and client_key",
            code="AUTH_INVALID",
        )
    out: dict[str, Any] = {
        "client_cert": auth.client_cert,
        "client_key": auth.client_key,
    }
    if auth.ca_certs:
        out["ca_certs"] = auth.ca_certs
    return out


def _bootstrap_auth() -> None:
    if _AUTH_BUILDERS:
        return
    register_auth_strategy("none", _build_none)
    register_auth_strategy("basic", _build_basic)
    register_auth_strategy("api_key", _build_api_key)
    register_auth_strategy("bearer", _build_bearer)
    register_auth_strategy("certificate", _build_certificate)


_bootstrap_auth()
