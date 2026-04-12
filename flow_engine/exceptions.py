"""Control-flow and engine exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class FlowEngineError(Exception):
    """Base class for engine errors."""


class CompilationError(FlowEngineError):
    """Static validation failed."""


class JumpInterrupt(FlowEngineError):
    """Jump to a named node within allowed scope (upward or same level)."""


@dataclass
class JumpTarget(JumpInterrupt):
    target: str  # node id / name


class ContinueInterrupt(FlowEngineError):
    """Skip remainder of current loop iteration."""


class BreakInterrupt(FlowEngineError):
    """Exit the innermost active loop."""


class TerminateInterrupt(FlowEngineError):
    """Request workflow termination (optional use from Starlark)."""


class TimeoutError(FlowEngineError):
    """Node execution exceeded timeout."""


class OutputValidationError(FlowEngineError):
    """Runtime output failed schema or shape checks."""


class GlobalWriteConflictError(FlowEngineError):
    """Two concurrent branches wrote the same global path without a barrier."""


def starlark_to_python(val: Any) -> Any:
    """Normalize Starlark return values to plain Python containers."""
    if val is None:
        return None
    if isinstance(val, (bool, int, float, str)):
        return val
    if isinstance(val, (list, tuple)):
        return [starlark_to_python(x) for x in val]
    if isinstance(val, dict):
        return {str(k): starlark_to_python(v) for k, v in val.items()}
    return val
