"""Observability abstractions for the flow engine.

The engine emits three kinds of observation signals during a run:

  * **Span** — a structured execution unit (flow root / loop iteration /
    subflow call / task). Spans nest naturally via ``parent_span_id``.
  * **Metric** — a single time-series point (one per node execution).
    Always emitted; the backend aggregates into per-node buckets.
  * **Log** — a structured log entry attached to the currently-open span.

The engine depends ONLY on :class:`ObservabilityBackend` (a ``Protocol``).
Concrete persistence lives in :mod:`flow_engine.runner.obs_backend`. The
default :class:`NullBackend` is a no-op so the engine path is identical
whether or not a real backend is attached.

Design notes
------------

* ``open_span`` returns an opaque ``int`` handle (a monotonically
  increasing local sequence number). The engine MUST pass the same handle
  back to ``close_span``; it has NO meaning outside the backend that
  issued it.
* ``emit_metric`` is unconditional — metrics are the "always-on" cheap
  layer, sampled spans are the deep-dive layer.
* The engine does NOT decide sampling. It always calls
  ``should_span(node_id)`` first; the backend (which holds the
  deployment-level config) returns the decision. Failures get a second
  chance via the same handle: when ``close_span`` is invoked with
  ``status='failed'`` the backend MAY upgrade an unsampled span into a
  sampled one (``always_on_failure`` policy).
* Sentinel for an unsampled span is ``SPAN_UNSAMPLED`` (``-1``). When
  ``should_span`` returns False the engine passes the sentinel everywhere
  and the backend skips persistence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

# Sentinel value returned by NullBackend / used when sampling skips a span.
# Engine treats it as "no span open"; the backend MUST accept it as a no-op.
SPAN_UNSAMPLED: int = -1


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass
class RunRef:
    """Identifies which run owns a Span.

    Exactly one of ``deploy_run_id`` / ``test_run_id`` is non-None. The
    backend uses this to populate the right column of ``fe_run_span``.
    Keeping the discriminator at the record boundary (instead of two
    parallel methods) means new run domains can be added without changing
    the protocol.
    """

    deploy_run_id: int | None = None
    test_run_id: int | None = None

    def __post_init__(self) -> None:
        if (self.deploy_run_id is None) == (self.test_run_id is None):
            raise ValueError("RunRef requires exactly one of deploy_run_id / test_run_id")


@dataclass
class SpanRecord:
    """One execution span.

    The engine fills the "open" half (everything except ``finished_at``,
    ``duration_ms``, ``status``, ``error``, ``child_spans``, ``logs``);
    the backend completes the rest on ``close_span``.
    """

    run_ref: RunRef
    flow_code: str
    node_id: str
    node_type: str                       # flow_root | task | loop_iter | subflow
    started_at: datetime
    span_seq: int = 0                    # filled by backend
    parent_span_id: int | None = None    # the seq handle of the enclosing span
    scope_key: str = ""
    finished_at: datetime | None = None
    duration_ms: int | None = None
    status: str = "running"              # running | success | failed | skipped
    error: str | None = None
    child_spans: list[dict[str, Any]] = field(default_factory=list)
    logs: list[dict[str, Any]] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    sampled: bool = True


@dataclass
class MetricPoint:
    """One node-execution data point fed to the metric pipeline."""

    deploy_run_id: int | None
    flow_code: str
    node_id: str
    at: datetime
    duration_ms: int
    status: str                           # success | failed | skipped


@dataclass
class LogEntry:
    """One log line attached to whichever Span is currently open on this branch."""

    level: str                            # DEBUG | INFO | WARN | ERROR
    msg: str
    source: str                           # node_id or hook name
    t_ms: int                             # ms since run start


# ---------------------------------------------------------------------------
# Log level helpers
# ---------------------------------------------------------------------------


LOG_LEVELS: dict[str, int] = {
    "NONE": 100,                          # NONE filters everything
    "ERROR": 40,
    "WARN": 30,
    "WARNING": 30,
    "INFO": 20,
    "DEBUG": 10,
}


def log_level_value(name: str | None) -> int:
    if not name:
        return LOG_LEVELS["ERROR"]
    return LOG_LEVELS.get(str(name).upper(), LOG_LEVELS["ERROR"])


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class ObservabilityBackend(Protocol):
    """Pluggable observation sink.

    All methods are synchronous and MUST be cheap: the engine calls them
    on the hot path of every node execution. Heavy work (DB writes,
    serialization) must happen on a background task owned by the backend.
    """

    def should_span(self, node_id: str, node_type: str) -> bool:
        """Sampling decision: open a span for this node right now?"""

    def open_span(self, record: SpanRecord) -> int:
        """Begin tracking a span. Returns a handle the engine must pass
        back to ``close_span``. May return :data:`SPAN_UNSAMPLED` to
        indicate that the span was rejected by sampling (the engine may
        still call this for ``always_on_failure`` upgrade — backend's
        choice)."""

    def close_span(
        self,
        handle: int,
        *,
        status: str,
        error: str | None,
        finished_at: datetime,
        child_spans: list[dict[str, Any]] | None = None,
        logs: list[dict[str, Any]] | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Finalize the span. Handles ``SPAN_UNSAMPLED`` gracefully (no-op
        unless the backend's failure-upgrade policy kicks in)."""

    def emit_metric(self, point: MetricPoint) -> None:
        """Record one data point. Always called (no sampling)."""

    def emit_log(self, handle: int, entry: LogEntry) -> None:
        """Attach a log entry to the open span identified by ``handle``.
        ``SPAN_UNSAMPLED`` is a no-op."""

    def extract_scope_key(
        self,
        node_id: str,
        item: Any,
        get_path: Any,
    ) -> str:
        """Resolve the configured ``scope_key`` for ``node_id`` against
        the current iteration item / context-path getter. Backends that
        don't support extraction return ``""``."""


# ---------------------------------------------------------------------------
# Null implementation (default)
# ---------------------------------------------------------------------------


class NullBackend:
    """No-op backend. Used when no observability is wired up."""

    def should_span(self, node_id: str, node_type: str) -> bool:  # noqa: ARG002
        return False

    def open_span(self, record: SpanRecord) -> int:  # noqa: ARG002
        return SPAN_UNSAMPLED

    def close_span(  # noqa: D401, PLR0913
        self,
        handle: int,
        *,
        status: str,
        error: str | None,
        finished_at: datetime,
        child_spans: list[dict[str, Any]] | None = None,
        logs: list[dict[str, Any]] | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        del handle, status, error, finished_at, child_spans, logs, attributes

    def emit_metric(self, point: MetricPoint) -> None:
        del point

    def emit_log(self, handle: int, entry: LogEntry) -> None:
        del handle, entry

    def extract_scope_key(self, node_id: str, item: Any, get_path: Any) -> str:  # noqa: ARG002
        return ""


# ---------------------------------------------------------------------------
# Path resolution helper used by backends to evaluate scope_key expressions
# ---------------------------------------------------------------------------


_PATH_PATTERN = re.compile(r"^\$\.([A-Za-z_][\w.]*)$")


def parse_scope_key_path(expr: str | None) -> list[str] | None:
    """Parse a ``$.foo.bar.baz`` expression into a dotted-path list.

    Returns None for empty / invalid expressions so callers can gracefully
    fall back to an empty ``scope_key`` rather than erroring at runtime
    on every iteration of a hot loop.
    """
    if not expr:
        return None
    m = _PATH_PATTERN.match(str(expr).strip())
    if not m:
        return None
    return [p for p in m.group(1).split(".") if p]


def resolve_path(value: Any, parts: list[str]) -> Any:
    """Walk a dotted path on a (possibly nested) mapping/object.

    Returns None on any miss; never raises. ``parts`` may be empty, in
    which case the input ``value`` is returned as-is.
    """
    cur: Any = value
    for p in parts:
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(p)
            continue
        cur = getattr(cur, p, None)
    return cur
