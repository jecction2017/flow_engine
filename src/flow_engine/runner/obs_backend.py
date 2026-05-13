"""Concrete :class:`ObservabilityBackend` backed by the engine DB.

Hot-path semantics
------------------

The engine calls ``open_span`` / ``close_span`` / ``emit_metric`` /
``emit_log`` on every node execution. These methods MUST be synchronous
and effectively O(1) — they only enqueue work onto in-memory buffers.
A separate background coroutine (:meth:`AsyncBufferedDBBackend.flush_loop`)
drains the buffers, computes percentiles, and writes to MySQL in batches.

Three buffers:

* **Open-span map** (``_open_spans``): handle → in-flight ``SpanRecord``.
  Removed on ``close_span``. Memory bounded by the number of
  simultaneously open spans (typically very small).

* **Span queue** (``_span_queue``, ``queue.Queue`` of completed records).
  Drained in 100-row batches or every 2 s, whichever comes first. Queue
  full → drop with a single ``log.warning`` (degradation > crash).

* **Metric buffer** (``_metric_buf``): keyed by (node_id, bucket_at). Holds
  a :class:`MetricAccumulator` that tracks counts plus a tail-1000
  duration deque. Buckets older than the current one are finalized on
  the flush tick (percentiles computed once, UPSERTed, then evicted).

Failure modes
-------------

* Backend never raises into the engine path — every public method
  swallows its own errors after logging.
* DB transient errors during flush are logged and the batch is
  retried up to a small bounded number of times before being dropped to
  prevent unbounded queue growth.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import random
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from flow_engine.engine.observability import (
    SPAN_UNSAMPLED,
    LogEntry,
    LOG_LEVELS,
    MetricPoint,
    ObservabilityBackend,
    RunRef,
    SpanRecord,
    log_level_value,
    parse_scope_key_path,
)
from flow_engine.runner import metric_persistence, span_persistence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeObsConfig:
    """Per-node observability policy resolved from
    ``FeFlowDeployment.observability.span_nodes[<id>]``."""

    rate: float = 1.0
    always_on_failure: bool = False
    scope_key_path: list[str] | None = None


@dataclass
class ObsRuntimeConfig:
    """Effective observability config for one run.

    ``log_level_min`` (int) is precomputed for fast log-emit filtering.
    ``span_retention_days`` is informative here; actual purging is
    driven by the worker's purge loop.
    """

    log_level_min: int = LOG_LEVELS["ERROR"]
    span_retention_days: int = 3
    default: NodeObsConfig = field(default_factory=NodeObsConfig)
    nodes: dict[str, NodeObsConfig] = field(default_factory=dict)

    def for_node(self, node_id: str) -> NodeObsConfig:
        if node_id in self.nodes:
            return self.nodes[node_id]
        return self.default


def parse_obs_config(raw: dict[str, Any] | None) -> ObsRuntimeConfig:
    """Validate / normalize the JSON config attached to a deployment.

    Unknown keys are ignored. Sampling rates are clamped to [0, 1]; an
    invalid value falls back silently to 1.0 (engine is fail-open: we'd
    rather emit too much than crash a long-running consumer).
    """
    raw = raw or {}
    log_level_min = log_level_value(raw.get("log_level"))
    retention = int(raw.get("span_retention_days") or 3)
    if retention < 1:
        retention = 1

    nodes_raw = raw.get("span_nodes") or {}
    if not isinstance(nodes_raw, dict):
        nodes_raw = {}

    def _one(node_raw: Any) -> NodeObsConfig:
        if not isinstance(node_raw, dict):
            return NodeObsConfig()
        rate_raw = node_raw.get("rate", 1.0)
        try:
            rate = max(0.0, min(1.0, float(rate_raw)))
        except (TypeError, ValueError):
            rate = 1.0
        always_on_failure = bool(node_raw.get("always_on_failure"))
        scope_key_path = parse_scope_key_path(node_raw.get("scope_key"))
        return NodeObsConfig(
            rate=rate,
            always_on_failure=always_on_failure,
            scope_key_path=scope_key_path,
        )

    default = _one(nodes_raw.get("__default__"))
    nodes = {
        str(k): _one(v)
        for k, v in nodes_raw.items()
        if k != "__default__" and isinstance(k, str)
    }
    return ObsRuntimeConfig(
        log_level_min=log_level_min,
        span_retention_days=retention,
        default=default,
        nodes=nodes,
    )


# ---------------------------------------------------------------------------
# In-memory state types
# ---------------------------------------------------------------------------


@dataclass
class _OpenSpan:
    """Server-side view of a span between open and close.

    Stored in a dict keyed by the handle returned to the engine.

    ``parent_handle`` is the engine-supplied parent's IN-MEMORY handle
    (NOT the DB id) — we keep it around so that at flush time we can
    look up the DB id even if the parent was flushed after this span
    was opened.

    ``pending_children`` collects child :class:`_OpenSpan` records that
    have already been closed but whose enqueue was deferred so the
    parent's DB id can be resolved first. The list is drained when this
    span itself is enqueued.
    """

    record: SpanRecord
    handle: int
    parent_handle: int | None
    sampled: bool
    pending_children: list["_OpenSpan"] = field(default_factory=list)
    closed: bool = False


@dataclass
class _MetricAccumulator:
    """Per-(node_id, bucket_at) accumulator for the metric pipeline."""

    span_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    total_ms: int = 0
    max_ms: int | None = None
    min_ms: int | None = None
    # Tail-1000 sample window for percentile estimation. Bounded memory
    # so a single hot node can't OOM the worker.
    tail: deque[int] = field(default_factory=lambda: deque(maxlen=1000))

    def add(self, duration_ms: int, status: str) -> None:
        self.span_count += 1
        if status == "success":
            self.success_count += 1
        elif status == "failed":
            self.failed_count += 1
        elif status == "skipped":
            self.skipped_count += 1
        if status != "skipped":
            self.total_ms += duration_ms
            self.tail.append(int(duration_ms))
            if self.max_ms is None or duration_ms > self.max_ms:
                self.max_ms = int(duration_ms)
            if self.min_ms is None or duration_ms < self.min_ms:
                self.min_ms = int(duration_ms)

    def percentiles(self) -> tuple[int | None, int | None, int | None]:
        n = len(self.tail)
        if n == 0:
            return None, None, None
        sorted_tail = sorted(self.tail)

        def _pick(p: float) -> int:
            idx = max(0, min(n - 1, int(round(p * (n - 1)))))
            return int(sorted_tail[idx])

        return _pick(0.5), _pick(0.95), _pick(0.99)


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class AsyncBufferedDBBackend(ObservabilityBackend):
    """Production backend used by worker-driven runs.

    Parameters
    ----------
    run_ref:
        Identifies the owning :class:`fe_deploy_run` or :class:`fe_test_run`.
    flow_code:
        Business code stamped onto every span / metric row.
    obs_cfg:
        Per-deployment policy (see :func:`parse_obs_config`).
    span_batch_size / span_flush_interval_s:
        Span pipeline tunables.
    metric_flush_interval_s:
        Metric pipeline tunable; defaults to 60 s so the dashboard
        refreshes within a minute even when the cluster is quiet.
    """

    def __init__(
        self,
        *,
        run_ref: RunRef,
        flow_code: str,
        obs_cfg: ObsRuntimeConfig,
        span_batch_size: int = 100,
        span_flush_interval_s: float = 2.0,
        metric_flush_interval_s: float = 60.0,
        span_queue_maxsize: int = 10_000,
    ) -> None:
        self._run_ref = run_ref
        self._flow_code = flow_code
        self._cfg = obs_cfg
        self._span_batch_size = max(1, int(span_batch_size))
        self._span_flush_interval_s = max(0.1, float(span_flush_interval_s))
        self._metric_flush_interval_s = max(1.0, float(metric_flush_interval_s))

        # Span pipeline — `queue.Queue` is fully thread-safe so the
        # engine (main thread) can `put_nowait` while the flush worker
        # thread (via asyncio.to_thread) does `get_nowait` without
        # corrupting internal state. asyncio.Queue is coroutine-safe
        # only and would race here.
        self._span_queue: queue.Queue[_OpenSpan] = queue.Queue(maxsize=span_queue_maxsize)
        # Open spans + lock. Protected because deferred-child bookkeeping
        # in close_span has to read/mutate parent's pending_children list
        # atomically; if a parent and child close on different tasks
        # (concurrent loop iterations) there is a real interleave.
        self._open_spans: dict[int, _OpenSpan] = {}
        self._open_lock = threading.Lock()
        # Maps a handle to its eventual DB id. Populated by the flush
        # thread after INSERT. Only read/written inside the flush
        # thread, so no locking required.
        self._handle_to_db_id: dict[int, int] = {}
        self._dropped_spans = 0
        self._sampled_emitted = 0
        self._total_emitted = 0

        # Metric pipeline. asyncio is single-threaded for emit but the
        # flush runs in a worker thread; threading.Lock guards both
        # readers and writers.
        self._metric_buf: dict[tuple[str, datetime], _MetricAccumulator] = {}
        self._metric_lock = threading.Lock()

        # Handle counter (in-memory monotonic). Increments only on main
        # thread (engine's open_span) so no lock is necessary.
        self._handle_counter: int = 0

        self._stopping = asyncio.Event()
        self._flush_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # ObservabilityBackend protocol implementation
    # ------------------------------------------------------------------

    def should_span(self, node_id: str, node_type: str) -> bool:
        del node_type  # node_type-specific gating is no longer needed
        cfg = self._cfg.for_node(node_id)
        # always_on_failure forces every span to OPEN regardless of
        # rate, because we cannot retroactively capture a failure if
        # the span was never tracked. The actual sampled/unsampled
        # decision (which controls whether a success-status close
        # persists) is then made in open_span using the rate.
        if cfg.always_on_failure:
            return True
        if cfg.rate >= 1.0:
            return True
        if cfg.rate <= 0.0:
            return False
        return random.random() < cfg.rate

    def open_span(self, record: SpanRecord) -> int:
        # Engine resolved node-policy via should_span. We arrive here
        # whenever the engine decides to track; the backend is
        # responsible for the actual record bookkeeping.
        try:
            cfg = self._cfg.for_node(record.node_id)
            self._handle_counter += 1
            handle = self._handle_counter
            self._total_emitted += 1
            # Initial sampling decision. ``should_span`` already
            # returned True; here we decide whether — barring failure —
            # the close will persist. For ``always_on_failure`` nodes
            # we re-run the rate roll independently so that *every*
            # failure is captured, regardless of how the random success
            # samples landed.
            if cfg.rate >= 1.0:
                sampled = True
            elif cfg.rate <= 0.0:
                sampled = False
            else:
                sampled = random.random() < cfg.rate
            record.span_seq = handle
            # record.parent_span_id arrives from the engine as a parent
            # HANDLE. Keep it on _OpenSpan; the SpanRecord's
            # ``parent_span_id`` will be rewritten to a DB id at flush
            # time (or remain None if parent isn't sampled).
            parent_handle = record.parent_span_id
            record.parent_span_id = None
            open_span = _OpenSpan(
                record=record,
                handle=handle,
                parent_handle=parent_handle,
                sampled=sampled,
            )
            with self._open_lock:
                self._open_spans[handle] = open_span
            return handle
        except Exception:  # noqa: BLE001 — never raise into engine path
            logger.exception("open_span failed for node_id=%s", record.node_id)
            return SPAN_UNSAMPLED

    def close_span(  # noqa: PLR0913
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
        if handle == SPAN_UNSAMPLED:
            return
        try:
            with self._open_lock:
                open_span = self._open_spans.pop(handle, None)
            if open_span is None:
                return
            rec = open_span.record
            rec.finished_at = finished_at
            rec.status = status
            rec.error = error
            if child_spans is not None:
                rec.child_spans = child_spans
            if logs is not None:
                rec.logs = self._filter_logs(logs)
            if attributes is not None:
                rec.attributes = attributes
            if rec.started_at and rec.finished_at:
                rec.duration_ms = max(
                    0,
                    int((rec.finished_at - rec.started_at).total_seconds() * 1000),
                )
            # always_on_failure: a previously-unsampled span gets
            # promoted to sampled when the close status is "failed".
            if not open_span.sampled and status == "failed":
                cfg = self._cfg.for_node(rec.node_id)
                if cfg.always_on_failure:
                    open_span.sampled = True
            open_span.closed = True
            if not open_span.sampled:
                # Unsampled spans never enter the DB pipeline, but they
                # may have deferred children — release those (their own
                # sampling decisions stand).
                self._release_pending_children(open_span)
                return
            rec.sampled = True
            self._sampled_emitted += 1
            # Defer enqueue if our own parent hasn't been enqueued yet,
            # so that the flush thread always sees a parent BEFORE its
            # children — that is the invariant that lets us write
            # ``parent_span_id`` correctly in a single batched INSERT.
            self._enqueue_or_defer(open_span)
        except Exception:  # noqa: BLE001
            logger.exception("close_span failed for handle=%s", handle)

    def _enqueue_or_defer(self, open_span: _OpenSpan) -> None:
        """Enqueue ``open_span`` for flush, or park under its parent.

        Parent-then-child ordering in the queue means each batch's
        in-memory ``handle -> db_id`` map can resolve every child's
        ``parent_span_id`` without revisiting completed rows.
        """
        parent_handle = open_span.parent_handle
        if parent_handle is not None:
            with self._open_lock:
                parent_open = self._open_spans.get(parent_handle)
                if parent_open is not None and not parent_open.closed:
                    parent_open.pending_children.append(open_span)
                    return
        self._enqueue_span(open_span)
        # Now drain our own pending children (if any) — recursive but
        # bounded by total span depth, which is shallow in practice.
        self._release_pending_children(open_span)

    def _release_pending_children(self, open_span: _OpenSpan) -> None:
        pending, open_span.pending_children = open_span.pending_children, []
        for child in pending:
            if child.sampled:
                self._enqueue_span(child)
            # Even if this child wasn't sampled, walk its own pending
            # subtree so deeper sampled spans aren't stuck.
            self._release_pending_children(child)

    def _enqueue_span(self, open_span: _OpenSpan) -> None:
        try:
            self._span_queue.put_nowait(open_span)
        except queue.Full:
            self._dropped_spans += 1
            if self._dropped_spans <= 5 or self._dropped_spans % 1000 == 0:
                logger.warning(
                    "obs span queue full; dropped=%d (sampled=%d total=%d)",
                    self._dropped_spans,
                    self._sampled_emitted,
                    self._total_emitted,
                )

    def emit_metric(self, point: MetricPoint) -> None:
        if point.deploy_run_id is None:
            return
        try:
            bucket = metric_persistence.bucket_for(point.at)
            key = (point.node_id, bucket)
            with self._metric_lock:
                acc = self._metric_buf.get(key)
                if acc is None:
                    acc = _MetricAccumulator()
                    self._metric_buf[key] = acc
                acc.add(point.duration_ms, point.status)
        except Exception:  # noqa: BLE001
            logger.exception("emit_metric failed for node_id=%s", point.node_id)

    def emit_log(self, handle: int, entry: LogEntry) -> None:
        if handle == SPAN_UNSAMPLED:
            return
        try:
            if log_level_value(entry.level) < self._cfg.log_level_min:
                return
            with self._open_lock:
                open_span = self._open_spans.get(handle)
                if open_span is None or open_span.closed:
                    return
                log_dict = {
                    "level": entry.level,
                    "msg": entry.msg,
                    "source": entry.source,
                    "t_ms": int(entry.t_ms),
                }
                if open_span.record.logs is None:
                    open_span.record.logs = [log_dict]
                else:
                    open_span.record.logs.append(log_dict)
        except Exception:  # noqa: BLE001
            logger.exception("emit_log failed for handle=%s", handle)

    def extract_scope_key(self, node_id: str, item: Any, get_path: Any) -> str:
        cfg = self._cfg.for_node(node_id)
        if not cfg.scope_key_path:
            return ""
        try:
            value = get_path(cfg.scope_key_path)
        except Exception:  # noqa: BLE001
            return ""
        if value is None:
            return ""
        s = str(value)
        if len(s) > 512:
            return s[:512]
        return s

    # ------------------------------------------------------------------
    # Public lifecycle (driven by Worker)
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._flush_task is not None:
            return
        self._flush_task = asyncio.create_task(self._flush_loop(), name="obs-flush")

    async def drain(self, *, timeout_s: float = 5.0) -> None:
        """Flush remaining buffers and stop the background loop.

        Drain order (important):

        1. Mark stopping; await the periodic loop to exit.
        2. Sweep any spans still in ``_open_spans`` (i.e. abandoned by
           a crash). Treat them as ``status="running"`` with the current
           time as ``finished_at`` so on-call still sees the partial
           tree — losing in-flight spans on crash hides the most
           interesting evidence.
        3. Final synchronous flush of both span and metric queues.
        """
        self._stopping.set()
        if self._flush_task is not None:
            try:
                await asyncio.wait_for(self._flush_task, timeout=timeout_s)
            except asyncio.TimeoutError:
                logger.warning("obs flush loop did not finish within %.1fs", timeout_s)
                self._flush_task.cancel()
                try:
                    await self._flush_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            self._flush_task = None

        # Sweep abandoned open spans (parent_handle relationships are
        # preserved so the tree is still navigable).
        self._sweep_abandoned_open_spans()

        await asyncio.to_thread(self._flush_spans_sync, force_all=True)
        await asyncio.to_thread(self._flush_metrics_sync, finalize_all=True)

    def _sweep_abandoned_open_spans(self) -> None:
        """Forcibly close any span still open at drain time.

        Encountering an open span here means the engine exited without
        a matching ``close_span`` — almost always a crash. We persist
        the partial record with status="running" so the operator can
        see what was in flight.
        """
        now = datetime.now(timezone.utc)
        with self._open_lock:
            stragglers = list(self._open_spans.values())
            self._open_spans.clear()
        if not stragglers:
            return
        logger.warning(
            "obs drain: persisting %d abandoned spans (engine exited without close)",
            len(stragglers),
        )
        # Process deepest-first so children flush before their (still
        # open) parents could possibly land — but since we cleared the
        # dict above, the deferral check sees no parents and everything
        # enqueues directly. Promote any unsampled stragglers to
        # sampled so they actually persist (we always want crash data).
        for open_span in stragglers:
            rec = open_span.record
            if rec.finished_at is None:
                rec.finished_at = now
            if rec.status == "running":
                # leave as "running" — it signals the crash explicitly
                pass
            if rec.started_at and rec.finished_at:
                rec.duration_ms = max(
                    0,
                    int((rec.finished_at - rec.started_at).total_seconds() * 1000),
                )
            open_span.sampled = True
            open_span.closed = True
            rec.sampled = True
            self._sampled_emitted += 1
            self._enqueue_span(open_span)
            self._release_pending_children(open_span)

    @property
    def stats(self) -> dict[str, Any]:
        """Diagnostic counters for the worker / API to expose."""
        with self._open_lock:
            open_count = len(self._open_spans)
        with self._metric_lock:
            metric_count = len(self._metric_buf)
        return {
            "total_emitted": self._total_emitted,
            "sampled_emitted": self._sampled_emitted,
            "dropped_spans": self._dropped_spans,
            "span_queue_size": self._span_queue.qsize(),
            "open_spans": open_count,
            "metric_buckets": metric_count,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _filter_logs(self, logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        min_v = self._cfg.log_level_min
        out: list[dict[str, Any]] = []
        for entry in logs:
            level = entry.get("level") if isinstance(entry, dict) else None
            if log_level_value(level) < min_v:
                continue
            out.append(dict(entry))
        return out

    async def _flush_loop(self) -> None:
        """Background coroutine. Coalesces writes and emits buckets.

        The loop wakes on whichever happens first:
          * ``_span_flush_interval_s`` elapsed
          * span queue size >= ``_span_batch_size``
          * ``_stopping`` set
        """
        last_metric_flush = asyncio.get_event_loop().time()
        try:
            while not self._stopping.is_set():
                try:
                    await asyncio.wait_for(
                        self._stopping.wait(),
                        timeout=self._span_flush_interval_s,
                    )
                except asyncio.TimeoutError:
                    pass

                try:
                    await asyncio.to_thread(self._flush_spans_sync, False)
                except Exception:  # noqa: BLE001
                    logger.exception("obs span flush failed")

                now_loop = asyncio.get_event_loop().time()
                if now_loop - last_metric_flush >= self._metric_flush_interval_s:
                    last_metric_flush = now_loop
                    try:
                        await asyncio.to_thread(self._flush_metrics_sync, False)
                    except Exception:  # noqa: BLE001
                        logger.exception("obs metric flush failed")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("obs flush loop crashed")

    def _drain_span_queue(self, *, force_all: bool) -> list[_OpenSpan]:
        out: list[_OpenSpan] = []
        max_drain = self._span_queue.qsize() if force_all else self._span_batch_size
        for _ in range(max_drain):
            try:
                out.append(self._span_queue.get_nowait())
            except queue.Empty:
                break
        return out

    def _flush_spans_sync(self, force_all: bool) -> int:
        """Pull from queue, INSERT, then patch in-batch parent ids.

        Invariants relied upon:
          * The queue is parent-before-children for every (parent, child)
            pair (guaranteed by ``_enqueue_or_defer``).
          * ``s.flush()`` assigns ids in insertion order, so within a
            single batch a child's row's parent already has an id by
            the time we patch.

        We perform a single INSERT for the batch, then update
        ``parent_span_id`` for rows whose parent was within this batch
        (those still NULL after the cross-batch lookup), then commit.
        Cross-batch links are resolved via ``_handle_to_db_id`` which
        is populated AFTER each batch's flush.
        """
        batch = self._drain_span_queue(force_all=force_all)
        if not batch:
            return 0

        from flow_engine.db.models import FeRunSpan
        from flow_engine.db.session import db_session

        run_ref = self._run_ref
        rows: list[FeRunSpan] = []
        for open_span in batch:
            rec = open_span.record
            cross_batch_parent_id: int | None = None
            if open_span.parent_handle is not None:
                cross_batch_parent_id = self._handle_to_db_id.get(open_span.parent_handle)
            rows.append(
                FeRunSpan(
                    deploy_run_id=run_ref.deploy_run_id,
                    test_run_id=run_ref.test_run_id,
                    flow_code=rec.flow_code,
                    node_id=rec.node_id,
                    node_type=rec.node_type,
                    span_seq=int(rec.span_seq),
                    parent_span_id=cross_batch_parent_id,
                    scope_key=(rec.scope_key or "")[:512],
                    started_at=rec.started_at,
                    finished_at=rec.finished_at,
                    duration_ms=rec.duration_ms,
                    status=rec.status,
                    error=rec.error,
                    child_spans=rec.child_spans,
                    logs=rec.logs,
                    attributes=rec.attributes or None,
                    sampled=int(bool(rec.sampled)),
                )
            )

        inserted = 0
        try:
            with db_session() as s:
                s.add_all(rows)
                s.flush()  # auto-increment ids assigned here
                # Build the local handle->db_id map for this batch.
                local_map: dict[int, int] = {
                    int(open_span.handle): int(rows[i].id)
                    for i, open_span in enumerate(batch)
                }
                # Patch in-batch parent links: rows whose parent was in
                # this same batch still have parent_span_id=None at this
                # point. Resolve them now; SQLAlchemy will emit UPDATEs
                # on commit.
                for i, open_span in enumerate(batch):
                    if rows[i].parent_span_id is not None:
                        continue
                    ph = open_span.parent_handle
                    if ph is None:
                        continue
                    same_batch_id = local_map.get(ph)
                    if same_batch_id is not None:
                        rows[i].parent_span_id = same_batch_id
                inserted = len(rows)
                # Update the persistent handle map AFTER the batch is
                # committed (do it inside the session block so the map
                # only contains durable ids).
            self._handle_to_db_id.update(local_map)
            # Trim the handle map periodically to prevent unbounded
            # growth on long-running resident flows.
            if len(self._handle_to_db_id) > 50_000:
                excess = len(self._handle_to_db_id) - 25_000
                for key in list(self._handle_to_db_id.keys())[:excess]:
                    self._handle_to_db_id.pop(key, None)
            return inserted
        except Exception:  # noqa: BLE001
            logger.exception("span flush insert failed; dropping %d rows", len(rows))
            return 0
        finally:
            if inserted and run_ref.deploy_run_id is not None:
                try:
                    metric_persistence.update_deploy_run_counters(
                        run_id=int(run_ref.deploy_run_id),
                        sampled_span_count_delta=inserted,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("update_deploy_run_counters failed")

    def _flush_metrics_sync(self, finalize_all: bool) -> int:
        """UPSERT in-memory metric buckets. ``finalize_all`` writes every
        bucket; otherwise only buckets older than the current one are
        flushed (so the current bucket keeps accumulating until it rolls
        over)."""
        now = datetime.now(timezone.utc)
        current_bucket = metric_persistence.bucket_for(now)

        with self._metric_lock:
            keys_to_flush: list[tuple[str, datetime]] = []
            for key in list(self._metric_buf.keys()):
                _, bucket_at = key
                if finalize_all or bucket_at < current_bucket:
                    keys_to_flush.append(key)
            if not keys_to_flush:
                return 0
            buckets_data: list[tuple[tuple[str, datetime], _MetricAccumulator]] = [
                (k, self._metric_buf[k]) for k in keys_to_flush
            ]

        run_ref = self._run_ref
        deploy_run_id = run_ref.deploy_run_id
        if deploy_run_id is None:
            # Test runs don't write metrics — drop the buckets.
            with self._metric_lock:
                for k in keys_to_flush:
                    self._metric_buf.pop(k, None)
            return 0

        flushed = 0
        total_span_count = 0
        for (node_id, bucket_at), acc in buckets_data:
            p50, p95, p99 = acc.percentiles()
            try:
                metric_persistence.upsert_metric_bucket(
                    deploy_run_id=int(deploy_run_id),
                    flow_code=self._flow_code,
                    node_id=node_id,
                    bucket_at=bucket_at,
                    span_count=acc.span_count,
                    success_count=acc.success_count,
                    failed_count=acc.failed_count,
                    skipped_count=acc.skipped_count,
                    total_ms=acc.total_ms,
                    p50_ms=p50,
                    p95_ms=p95,
                    p99_ms=p99,
                    max_ms=acc.max_ms,
                    min_ms=acc.min_ms,
                )
                flushed += 1
                total_span_count += acc.span_count
                with self._metric_lock:
                    self._metric_buf.pop((node_id, bucket_at), None)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "metric upsert failed (node=%s bucket=%s); keeping in buffer",
                    node_id,
                    bucket_at,
                )

        if total_span_count and deploy_run_id is not None:
            try:
                metric_persistence.update_deploy_run_counters(
                    run_id=int(deploy_run_id),
                    span_count_delta=int(total_span_count),
                )
            except Exception:  # noqa: BLE001
                logger.exception("update_deploy_run_counters (total) failed")

        return flushed
