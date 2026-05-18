"""Build sync Elasticsearch clients from instance config."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from flow_engine.connectors.backends.elasticsearch.auth import build_client_auth
from flow_engine.connectors.config import AuthSpec, ElasticsearchInstanceSpec, ProtectionSpec
from flow_engine.connectors.errors import ConnectorError


def _write_pem_temp(content: str, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    import os

    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def create_client(
    spec: ElasticsearchInstanceSpec,
    *,
    request_timeout_sec: float,
) -> Any:
    try:
        from elasticsearch import Elasticsearch
    except ImportError as exc:
        raise ConnectorError(
            "elasticsearch package not installed; install flow-engine[integrations]",
            code="INTEGRATION_UNAVAILABLE",
        ) from exc

    auth_spec = spec.auth if isinstance(spec.auth, AuthSpec) else AuthSpec.model_validate(spec.auth)
    auth_kwargs = build_client_auth(auth_spec)

    # Certificate PEMs may be inline; write temp files for client
    temp_paths: list[str] = []
    if "client_cert" in auth_kwargs and "\n" in str(auth_kwargs["client_cert"]):
        cert_path = _write_pem_temp(str(auth_kwargs["client_cert"]), ".crt")
        key_path = _write_pem_temp(str(auth_kwargs["client_key"]), ".key")
        temp_paths.extend([cert_path, key_path])
        auth_kwargs = {
            **{k: v for k, v in auth_kwargs.items() if k not in ("client_cert", "client_key")},
            "client_cert": cert_path,
            "client_key": key_path,
        }
    if auth_kwargs.get("ca_certs") and "\n" in str(auth_kwargs.get("ca_certs", "")):
        ca_path = _write_pem_temp(str(auth_kwargs["ca_certs"]), ".ca")
        temp_paths.append(ca_path)
        auth_kwargs["ca_certs"] = ca_path

    client = Elasticsearch(
        hosts=spec.hosts,
        verify_certs=spec.verify_certs,
        request_timeout=request_timeout_sec,
        **auth_kwargs,
    )
    client._flow_engine_temp_paths = temp_paths  # type: ignore[attr-defined]
    return client


def create_async_client(
    spec: ElasticsearchInstanceSpec,
    *,
    request_timeout_sec: float,
) -> Any:
    """Build AsyncElasticsearch (used with :mod:`connectors.async_bridge`)."""
    try:
        from elasticsearch import AsyncElasticsearch
    except ImportError as exc:
        raise ConnectorError(
            "elasticsearch package not installed; install flow-engine[integrations]",
            code="INTEGRATION_UNAVAILABLE",
        ) from exc

    auth_spec = spec.auth if isinstance(spec.auth, AuthSpec) else AuthSpec.model_validate(spec.auth)
    auth_kwargs = build_client_auth(auth_spec)
    return AsyncElasticsearch(
        hosts=spec.hosts,
        verify_certs=spec.verify_certs,
        request_timeout=request_timeout_sec,
        **auth_kwargs,
    )


def close_client(client: Any) -> None:
    try:
        client.close()
    except Exception:  # noqa: BLE001
        pass
    for path in getattr(client, "_flow_engine_temp_paths", []):
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


def merged_protection(
    defaults: dict[str, Any],
    instance: dict[str, Any],
) -> ProtectionSpec:
    base = ProtectionSpec.model_validate(defaults.get("protection") or {})
    inst_prot = instance.get("protection")
    if inst_prot:
        return base.model_copy(update=ProtectionSpec.model_validate(inst_prot).model_dump())
    return base
