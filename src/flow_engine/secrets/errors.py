"""Secret management errors."""

from __future__ import annotations

from flow_engine.engine.exceptions import FlowEngineError


class SecretError(FlowEngineError):
    """Invalid secret reference, missing secret, or crypto failure."""
