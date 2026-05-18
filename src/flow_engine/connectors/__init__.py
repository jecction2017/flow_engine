"""Universal connector layer for external integrations (ES, Kafka, HTTP, ...)."""

from flow_engine.connectors.correlation import (
    get_integration_correlation_id,
    integration_correlation_scope,
)
from flow_engine.connectors.errors import ConnectorError
from flow_engine.connectors.registry import ConnectorRegistry, get_registry

__all__ = [
    "ConnectorError",
    "ConnectorRegistry",
    "get_integration_correlation_id",
    "get_registry",
    "integration_correlation_scope",
]
