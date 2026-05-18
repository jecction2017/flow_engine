"""Connector backend protocols."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ConnectorHandle(Protocol):
    """A bound connection to one named instance."""

    kind: str
    instance_id: str

    def execute(self, operation: str, **params: Any) -> dict[str, Any]:
        """Run an operation; returns raw ES/API response dict."""
        ...


@runtime_checkable
class ConnectorBackend(Protocol):
    """Pluggable backend for a connector kind (elasticsearch, kafka, ...)."""

    kind: str

    def bind_instances(
        self,
        instances: dict[str, dict[str, Any]],
        *,
        defaults: dict[str, Any],
    ) -> dict[str, ConnectorHandle]:
        """Create handles for all configured instances."""
        ...

    def close_all(self) -> None:
        """Release connections for this backend."""
        ...
