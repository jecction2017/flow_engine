"""Connector registry: bind from data dictionary, resolve handles by kind/instance."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import sys
import threading
from typing import Any

from flow_engine.connectors.config import ElasticsearchConfig, parse_elasticsearch_config
from flow_engine.connectors.config_kafka import parse_kafka_config
from flow_engine.connectors.errors import ConnectorError
from flow_engine.connectors.protocol import ConnectorBackend, ConnectorHandle
from flow_engine.secrets.service import resolve_secret_references
from flow_engine.stores.data_dict import active_dictionary

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_registry: ConnectorRegistry | None = None


def get_registry() -> ConnectorRegistry:
    global _registry
    with _LOCK:
        if _registry is None:
            _registry = ConnectorRegistry()
        return _registry


def reset_registry_for_tests() -> None:
    global _registry
    with _LOCK:
        if _registry is not None:
            _registry.close_all()
        _registry = None


class ConnectorRegistry:
    def __init__(self) -> None:
        self._backends: dict[str, ConnectorBackend] = {}
        self._handles: dict[tuple[str, str], ConnectorHandle] = {}
        self._bind_hash: str | None = None
        self._profile: str | None = None
        self._register_backends()

    @staticmethod
    def _elasticsearch_package_installed() -> bool:
        return importlib.util.find_spec("elasticsearch") is not None

    def _ensure_elasticsearch_backend(self) -> bool:
        """Lazy-load ES backend when the package is present in this interpreter."""
        if "elasticsearch" in self._backends:
            return True
        if not self._elasticsearch_package_installed():
            return False
        try:
            from flow_engine.connectors.backends.elasticsearch.backend import (
                ElasticsearchBackend,
            )

            self._backends["elasticsearch"] = ElasticsearchBackend()
            return True
        except ImportError:
            logger.warning("elasticsearch package present but backend import failed", exc_info=True)
            return False

    def _register_backends(self) -> None:
        self._ensure_elasticsearch_backend()
        self._ensure_kafka_backend()

    @staticmethod
    def _aiokafka_installed() -> bool:
        return importlib.util.find_spec("aiokafka") is not None

    def _ensure_kafka_backend(self) -> bool:
        if "kafka" in self._backends:
            return True
        try:
            from flow_engine.connectors.backends.kafka.backend import KafkaBackend

            self._backends["kafka"] = KafkaBackend()
            return True
        except ImportError:
            logger.debug("kafka backend not available", exc_info=True)
            return False

    @property
    def elasticsearch_available(self) -> bool:
        return self._ensure_elasticsearch_backend()

    @property
    def kafka_available(self) -> bool:
        return self._ensure_kafka_backend()

    @staticmethod
    def integration_unavailable_message(kind: str = "elasticsearch") -> str:
        exe = sys.executable
        if kind == "kafka":
            if ConnectorRegistry._aiokafka_installed():
                return (
                    f"Kafka backend failed to load in this process ({exe}). "
                    "Restart flow-worker using the project virtualenv."
                )
            return (
                f"aiokafka is not installed ({exe}). "
                "Run: pip install aiokafka, or pip install -e \".[kafka]\"."
            )
        if ConnectorRegistry._elasticsearch_package_installed():
            return (
                f"Elasticsearch backend failed to load in this process ({exe}). "
                "Restart flow-api using the project virtualenv."
            )
        return (
            f"elasticsearch is not installed for the API Python interpreter ({exe}). "
            "Activate .venv, run: pip install \"elasticsearch>=7.17,<8\", then restart flow-api."
        )

    def bind(
        self,
        dictionary: dict[str, Any],
        *,
        profile: str | None = None,
    ) -> None:
        """Bind all connector kinds from resolved dictionary tree."""
        middleware = dictionary.get("middleware") or {}
        if not isinstance(middleware, dict):
            middleware = {}

        es_raw = middleware.get("elasticsearch")
        kafka_raw = middleware.get("kafka")
        config_hash = _hash_config({"elasticsearch": es_raw, "kafka": kafka_raw})

        with _LOCK:
            stale_empty = (
                config_hash == self._bind_hash
                and profile == self._profile
                and (
                    (es_raw is not None and not any(k == "elasticsearch" for k, _ in self._handles))
                    or (kafka_raw is not None and not any(k == "kafka" for k, _ in self._handles))
                )
            )
            if config_hash == self._bind_hash and profile == self._profile and not stale_empty:
                return
            # Same dictionary payload, different profile label only — do not tear down
            # long-lived Kafka subscription sessions (FlowRuntime.run re-binds often).
            if config_hash == self._bind_hash and not stale_empty:
                self._profile = profile
                return
            logger.debug(
                "connector registry rebind closing sessions profile=%s hash_changed=%s",
                profile,
                config_hash != self._bind_hash,
            )
            self.close_all()
            self._bind_hash = config_hash
            self._profile = profile

            if es_raw is not None and self._ensure_elasticsearch_backend():
                resolved = resolve_secret_references(es_raw, profile=profile)
                cfg = parse_elasticsearch_config(resolved)
                if cfg is not None:
                    if not cfg.instances:
                        logger.warning(
                            "middleware.elasticsearch has no instances; "
                            "ensure YAML uses top-level key 'instances:' "
                            "(module_code must be middleware.elasticsearch)"
                        )
                    backend = self._backends["elasticsearch"]
                    defaults = cfg.defaults.model_dump()
                    instances = {
                        iid: inst.model_dump() for iid, inst in cfg.instances.items()
                    }
                    for iid, handle in backend.bind_instances(instances, defaults=defaults).items():
                        self._handles[("elasticsearch", iid)] = handle
            elif es_raw is None:
                logger.debug(
                    "no middleware.elasticsearch in dictionary for profile=%s",
                    profile,
                )

            if kafka_raw is not None and self._ensure_kafka_backend():
                resolved_k = resolve_secret_references(kafka_raw, profile=profile)
                kcfg = parse_kafka_config(resolved_k)
                if kcfg is not None:
                    if not kcfg.instances:
                        logger.warning(
                            "middleware.kafka has no instances; "
                            "module_code must be middleware.kafka"
                        )
                    backend = self._backends["kafka"]
                    for iid, handle in backend.bind_instances(kcfg).items():
                        self._handles[("kafka", iid)] = handle
            elif kafka_raw is None:
                logger.debug(
                    "no middleware.kafka in dictionary for profile=%s",
                    profile,
                )

    def bind_from_active_dictionary(self, *, profile: str | None = None) -> None:
        tree = active_dictionary()
        if tree is None:
            return
        self.bind(tree, profile=profile)

    def ensure_bound(self, *, profile: str | None = None) -> None:
        if profile is None:
            from flow_engine.stores.profile_store import active_profile

            try:
                profile = active_profile()
            except Exception:  # noqa: BLE001
                profile = None
        self.bind_from_active_dictionary(profile=profile)

    def get(self, kind: str, instance_id: str) -> ConnectorHandle:
        self.ensure_bound(profile=None)
        key = (kind, instance_id)
        handle = self._handles.get(key)
        if handle is None:
            known = sorted(i for k, i in self._handles if k == kind)
            hint = _instance_not_found_hint(kind, instance_id)
            raise ConnectorError(
                f"Unknown {kind} instance {instance_id!r}; configured: {known or '(none)'}. {hint}",
                code="INSTANCE_NOT_FOUND",
            )
        return handle

    def list_instances(self, kind: str) -> list[str]:
        self.ensure_bound(profile=None)
        return sorted(i for k, i in self._handles if k == kind)

    def close_all(self) -> None:
        for backend in self._backends.values():
            try:
                backend.close_all()
            except Exception:  # noqa: BLE001
                logger.debug("backend close failed", exc_info=True)
        self._handles.clear()

    def reset_for_tests(self) -> None:
        with _LOCK:
            self.close_all()
            self._bind_hash = None
            self._profile = None


def _hash_config(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _instance_not_found_hint(kind: str, instance_id: str) -> str:
    if kind != "elasticsearch":
        return ""
    tree = active_dictionary()
    if not isinstance(tree, dict):
        return "Active dictionary not set; use debug Profile matching your dict module."
    middleware = tree.get("middleware")
    if not isinstance(middleware, dict):
        return (
            "Missing $.middleware.elasticsearch — add dict module_code "
            "middleware.elasticsearch (not elasticsearch at root)."
        )
    es_raw = middleware.get("elasticsearch")
    if es_raw is None:
        return (
            "Missing $.middleware.elasticsearch — add dict module_code "
            "middleware.elasticsearch."
        )
    if isinstance(es_raw, dict):
        inst = es_raw.get("instances")
        if not isinstance(inst, dict) or not inst:
            return (
                "middleware.elasticsearch.instances is empty — YAML must nest hosts under "
                "instances.<name> (e.g. instances.main.hosts), not at module root."
            )
        if instance_id not in inst:
            return f"Instance {instance_id!r} not in instances; available: {sorted(inst)}."
    return ""
