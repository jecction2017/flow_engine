"""Colocated subscription ingress: poll → parse → FlowRuntime.run per message."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

from flow_engine.connectors.backends.kafka.messages import BusMessage, Position
from flow_engine.connectors.config_kafka import parse_consumer_id
from flow_engine.connectors.registry import get_registry
from flow_engine.engine.models import FlowState
from flow_engine.runner import deploy_persistence
from flow_engine.runner.subscription.dedup import (
    begin_message_processing,
    finish_message_processing,
    idempotency_enabled,
    idempotency_window_s,
)
from flow_engine.runner.subscription.kafka_session import ConnectorSubscriptionSession
from flow_engine.runner.subscription.message_parse import build_trigger_context
from flow_engine.runner.subscription.spec import SubscriptionSpec, load_subscription_spec

logger = logging.getLogger(__name__)


class SubscriptionIngressError(Exception):
    """Fatal subscription ingress error (e.g. session_open rejected by connector)."""

    def __init__(self, error: dict[str, Any]) -> None:
        self.error = error
        message = str(error.get("message") or error.get("code") or "subscription ingress failed")
        super().__init__(message)


PrepareRuntimeFn = Callable[
    [dict[str, Any], dict[str, Any] | None],
    Awaitable[tuple[int, Any, str, Any]],
]

_commit_lock = asyncio.Lock()


async def run_subscription_ingress(
    deployment: dict[str, Any],
    *,
    stop_evt: asyncio.Event,
    prepare_runtime: PrepareRuntimeFn,
    worker_id: str,
) -> None:
    """Run until ``stop_evt`` is set."""
    spec = load_subscription_spec(deployment.get("schedule_config"))
    sub = spec.subscription
    profile_id = deployment.get("env_profile_code") or "default"
    from flow_engine.stores import data_dict
    from flow_engine.stores.data_dict import dictionary_scope
    from flow_engine.stores.profile_store import profile_scope

    dict_tree = await asyncio.to_thread(data_dict.tree_copy, profile_id)
    reg = get_registry()
    with profile_scope(profile_id), dictionary_scope(dict_tree):
        reg.bind(dict_tree, profile=profile_id)
        cluster_id, _, _ = parse_consumer_id(sub.consumer_id)
        handle = reg.get("kafka", cluster_id)
        session_key = f"deploy-{deployment['id']}"
        open_result = await asyncio.to_thread(
            handle.execute,
            "session_open",
            session_key=session_key,
            consumer_id=sub.consumer_id,
            partitions=sub.partitions,
            strategy=sub.start_position,
        )
        if not open_result.get("ok"):
            err = open_result.get("error") or {}
            logger.error(
                "subscription session_open failed deployment_id=%s error=%s",
                deployment.get("id"),
                err,
            )
            raise SubscriptionIngressError(
                err if isinstance(err, dict) else {"message": str(err)}
            )
        session = ConnectorSubscriptionSession(
            handle,
            session_key=session_key,
            consumer_id=sub.consumer_id,
        )
        await _ingress_loop(
            deployment,
            spec=spec,
            session=session,
            handle=handle,
            sub=sub,
            stop_evt=stop_evt,
            prepare_runtime=prepare_runtime,
            worker_id=worker_id,
        )


async def _ingress_loop(
    deployment: dict[str, Any],
    *,
    spec: SubscriptionSpec,
    session: ConnectorSubscriptionSession,
    handle: Any,
    sub: Any,
    stop_evt: asyncio.Event,
    prepare_runtime: PrepareRuntimeFn,
    worker_id: str,
) -> None:
    _ = handle
    _ = worker_id
    sem = asyncio.Semaphore(spec.dispatch.max_in_flight)
    in_flight: set[asyncio.Task[None]] = set()

    async def _wait_capacity() -> None:
        while len(in_flight) >= spec.dispatch.max_in_flight and not stop_evt.is_set():
            await asyncio.sleep(0.05)

    try:
        while not stop_evt.is_set():
            await _wait_capacity()
            # Backpressure: _wait_capacity blocks until in_flight < max_in_flight.
            # Do not pause the Kafka consumer here — aiokafka pause/resume can stick
            # across rebalances when assignment() is briefly empty.

            batch = await session.poll(
                max_records=spec.consumption.batch_max_records,
                timeout_ms=spec.consumption.poll_timeout_ms,
            )
            if not batch:
                continue

            logger.debug(
                "subscription polled batch deployment_id=%s count=%d",
                deployment.get("id"),
                len(batch),
            )

            for msg in batch:
                if stop_evt.is_set():
                    break
                await sem.acquire()
                task = asyncio.create_task(
                    _process_one(
                        deployment,
                        spec=spec,
                        msg=msg,
                        session=session,
                        handle=handle,
                        sub=sub,
                        prepare_runtime=prepare_runtime,
                        sem=sem,
                    )
                )
                in_flight.add(task)
                task.add_done_callback(lambda t, s=in_flight: s.discard(t))

        if in_flight:
            await asyncio.gather(*in_flight, return_exceptions=True)
    finally:
        await session.close()


async def _process_one(
    deployment: dict[str, Any],
    *,
    spec: SubscriptionSpec,
    msg: BusMessage,
    session: ConnectorSubscriptionSession,
    handle: Any,
    sub: Any,
    prepare_runtime: PrepareRuntimeFn,
    sem: asyncio.Semaphore,
) -> None:
    deployment_id = int(deployment["id"])
    pos = Position(topic=msg.topic, partition=msg.partition, offset=msg.offset)
    idem_raw = spec.consumption.idempotency
    idem_on = idempotency_enabled(idem_raw)
    run_id: int | None = None
    try:
        should_process = await asyncio.to_thread(
            begin_message_processing,
            deployment_id=deployment_id,
            topic=msg.topic,
            partition=msg.partition,
            offset=msg.offset,
            window_s=idempotency_window_s(idem_raw) if idem_on else None,
            idempotency=idem_on,
        )
        if not should_process:
            await _commit_positions(session, [pos])
            return

        trigger_context = build_trigger_context(
            msg,
            subscription=spec.subscription,
            parse=spec.parse,
            correlation_id=f"{deployment_id}:{msg.partition}:{msg.offset}",
            run_mode=str(deployment.get("mode") or "production"),
            capability_policy=list(deployment.get("capability_policy") or []),
        )

        run_id, runtime, profile_id, backend = await prepare_runtime(
            deployment, trigger_context
        )
        if isinstance(trigger_context.get("event_meta"), dict):
            trigger_context["event_meta"]["correlation_id"] = str(run_id)
        runtime.ctx.global_ns.update(trigger_context)

        from flow_engine.stores.profile_store import profile_scope

        await backend.start()
        try:
            with profile_scope(profile_id):
                result = await runtime.run()
        finally:
            try:
                await backend.drain()
            except Exception:  # noqa: BLE001
                logger.exception("obs drain failed run_id=%s", run_id)

        if result.state == FlowState.COMPLETED:
            await asyncio.to_thread(deploy_persistence.complete_deploy_run, run_id, result)
            await asyncio.to_thread(
                finish_message_processing,
                deployment_id=deployment_id,
                topic=msg.topic,
                partition=msg.partition,
                offset=msg.offset,
                status="completed",
                deploy_run_id=run_id,
            )
            await _commit_positions(session, [pos])
        else:
            err = getattr(result, "error", None) or str(result.state)
            await asyncio.to_thread(
                deploy_persistence.fail_deploy_run,
                run_id,
                err,
            )
            await asyncio.to_thread(
                finish_message_processing,
                deployment_id=deployment_id,
                topic=msg.topic,
                partition=msg.partition,
                offset=msg.offset,
                status="failed",
                deploy_run_id=run_id,
                error=str(err),
            )
            await _handle_poison(spec, msg, session, handle, sub, pos, error=str(err))
    except Exception as e:  # noqa: BLE001
        logger.exception(
            "subscription message failed deployment_id=%s %s:%s:%s",
            deployment_id,
            msg.topic,
            msg.partition,
            msg.offset,
        )
        await asyncio.to_thread(
            finish_message_processing,
            deployment_id=deployment_id,
            topic=msg.topic,
            partition=msg.partition,
            offset=msg.offset,
            status="failed",
            deploy_run_id=run_id,
            error=str(e),
        )
        await _handle_poison(spec, msg, session, handle, sub, pos, error=str(e))
    finally:
        sem.release()


async def _commit_positions(session: ConnectorSubscriptionSession, positions: list[Position]) -> None:
    if not positions:
        return
    async with _commit_lock:
        await session.commit(positions)


async def _handle_poison(
    spec: SubscriptionSpec,
    msg: BusMessage,
    session: ConnectorSubscriptionSession,
    handle: Any,
    sub: Any,
    pos: Position,
    *,
    error: str,
) -> None:
    dlq = spec.consumption.dlq
    producer_id = (sub.producer_id or "").strip() if sub else ""
    if dlq and isinstance(dlq, dict):
        producer_id = str(dlq.get("producer_id") or producer_id).strip()
        topic = str(dlq.get("topic") or "").strip()
        if producer_id:
            try:
                wrap = json.dumps(
                    {
                        "error": error,
                        "source_topic": msg.topic,
                        "partition": msg.partition,
                        "offset": msg.offset,
                        "original": msg.value.decode("utf-8", "replace"),
                    },
                    ensure_ascii=False,
                )
                await asyncio.to_thread(
                    handle.execute,
                    "publish_bytes",
                    producer_id=producer_id,
                    value=wrap.encode("utf-8"),
                    key=msg.key,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "DLQ publish failed producer_id=%s consumer_id=%s",
                    producer_id,
                    sub.consumer_id,
                )
        elif topic:
            logger.warning(
                "DLQ topic=%s without producer_id is no longer supported; "
                "set consumption.dlq.producer_id",
                topic,
            )
    await _commit_positions(session, [pos])
