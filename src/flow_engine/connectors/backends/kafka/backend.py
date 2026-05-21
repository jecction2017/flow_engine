"""Kafka ConnectorBackend implementation."""

from __future__ import annotations

import logging
import time
from typing import Any

from flow_engine.connectors.backends.kafka import operations as kafka_ops
from flow_engine.connectors.backends.kafka.client_factory import merged_protection
from flow_engine.connectors.backends.kafka.messages import BusMessage, Position
from flow_engine.connectors.config import ProtectionSpec
from flow_engine.connectors.config_kafka import (
    KafkaConfig,
    KafkaDefaults,
    ResolvedConsumerRef,
    ResolvedProducerRef,
    build_kafka_indexes,
    parse_consumer_id,
)
from flow_engine.connectors.errors import ConnectorError, err_envelope, ok_envelope
from flow_engine.connectors.protection.pipeline import ProtectionPipeline, RequestContext

logger = logging.getLogger(__name__)


def _aiokafka_available() -> bool:
    try:
        import aiokafka  # noqa: F401

        return True
    except ImportError:
        return False


class KafkaClusterHandle:
    kind = "kafka"

    def __init__(
        self,
        instance_id: str,
        *,
        defaults: KafkaDefaults,
        consumers: dict[str, ResolvedConsumerRef],
        producers: dict[str, ResolvedProducerRef],
        pipeline: ProtectionPipeline,
    ) -> None:
        self.instance_id = instance_id
        self._defaults = defaults
        self._consumers = {k: v for k, v in consumers.items() if v.cluster_id == instance_id}
        self._producers = {k: v for k, v in producers.items() if v.cluster_id == instance_id}
        self._pipeline = pipeline
        self._sessions: dict[str, Any] = {}
        self._producer_clients: dict[str, Any] = {}

    def _consumer_ref(self, consumer_id: str) -> ResolvedConsumerRef:
        ref = self._consumers.get(consumer_id)
        if ref is None:
            cluster, topic, name = parse_consumer_id(consumer_id)
            if cluster != self.instance_id:
                raise ConnectorError(
                    f"consumer {consumer_id!r} belongs to cluster {cluster!r}, not {self.instance_id!r}",
                    code="CONSUMER_NOT_FOUND",
                )
            raise ConnectorError(
                f"unknown consumer_id {consumer_id!r} for cluster {self.instance_id!r}",
                code="CONSUMER_NOT_FOUND",
            )
        return ref

    def _producer_ref(self, producer_id: str) -> ResolvedProducerRef:
        ref = self._producers.get(producer_id)
        if ref is None:
            raise ConnectorError(
                f"unknown producer_id {producer_id!r} for cluster {self.instance_id!r}",
                code="PRODUCER_NOT_FOUND",
            )
        return ref

    def execute(self, operation: str, **params: Any) -> dict[str, Any]:
        ctx = RequestContext(
            instance_id=self.instance_id,
            operation=operation,
        )
        try:
            return self._pipeline.run(ctx, lambda: self._execute_inner(operation, **params))
        except RuntimeError as exc:
            code = str(exc)
            if code in {"CIRCUIT_OPEN", "CONNECTOR_RATE_LIMIT", "CONNECTOR_CONCURRENCY_LIMIT"}:
                return err_envelope(code, code.replace("_", " ").lower(), instance=self.instance_id)
            raise
        except TimeoutError as exc:
            return err_envelope("CONNECTOR_TIMEOUT", str(exc), instance=self.instance_id)
        except ConnectorError as exc:
            return err_envelope(exc.code, str(exc), instance=self.instance_id)
        except Exception as exc:  # noqa: BLE001
            return err_envelope("KAFKA_ERROR", str(exc), instance=self.instance_id)

    def _execute_inner(self, operation: str, **params: Any) -> dict[str, Any]:
        t0 = time.monotonic()
        if operation == "receive":
            from flow_engine.connectors.async_bridge import run_async

            consumer_id = str(params["consumer_id"])
            max_records = int(params.get("max_records") or 10)
            max_records = self._pipeline.cap_size(max_records)
            timeout_ms = int(params.get("timeout_ms") or 1000)
            messages = run_async(
                kafka_ops.receive_bounded(
                    self._consumer_ref(consumer_id),
                    self._defaults,
                    max_records=max_records,
                    timeout_ms=timeout_ms,
                    partitions=params.get("partitions"),
                    strategy_override=params.get("strategy"),
                )
            )
            data = {"messages": messages}
        elif operation == "send":
            producer_id = str(params["producer_id"])
            import asyncio

            from flow_engine.connectors.async_bridge import run_async

            result = run_async(
                kafka_ops.send_message(
                    self._producer_ref(producer_id),
                    self._defaults,
                    value=params.get("value"),
                    key=params.get("key"),
                    partition=params.get("partition"),
                    headers=params.get("headers"),
                )
            )
            data = result
        elif operation == "session_open":
            import asyncio

            from flow_engine.connectors.async_bridge import run_async

            session_key = str(params["session_key"])
            consumer_id = str(params["consumer_id"])
            session = run_async(
                kafka_ops.open_consumer_session(
                    self._consumer_ref(consumer_id),
                    self._defaults,
                    partitions_override=params.get("partitions"),
                    strategy_override=params.get("strategy"),
                )
            )
            self._sessions[session_key] = session
            data = {"session_key": session_key}
        elif operation == "session_poll":
            session = self._sessions.get(str(params["session_key"]))
            if session is None:
                raise ConnectorError("session not found", code="SESSION_NOT_FOUND")
            from flow_engine.connectors.async_bridge import run_async

            raw: list[BusMessage] = run_async(
                session.poll(
                    max_records=int(params.get("max_records") or 100),
                    timeout_ms=int(params.get("timeout_ms") or 1000),
                )
            )
            if params.get("for_subscription"):
                data = {"messages": raw}
            else:
                consumer_id = str(params.get("consumer_id") or "")
                cref = self._consumer_ref(consumer_id) if consumer_id else None
                ser = cref.spec.serializers if cref else None
                from flow_engine.connectors.backends.kafka import client_factory as cf
                from flow_engine.connectors.backends.kafka.messages import message_to_dict

                data = {
                    "messages": [
                        message_to_dict(
                            m,
                            key=cf.deserialize_key(m.key, ser) if ser else None,
                            value=cf.deserialize_value(m.value, ser) if ser else None,
                        )
                        for m in raw
                    ]
                }
        elif operation == "session_commit":
            session = self._sessions.get(str(params["session_key"]))
            if session is None:
                raise ConnectorError("session not found", code="SESSION_NOT_FOUND")
            positions_raw = params.get("positions") or []
            positions = [
                Position(
                    topic=p["topic"],
                    partition=int(p["partition"]),
                    offset=int(p["offset"]),
                )
                for p in positions_raw
            ]
            import asyncio

            from flow_engine.connectors.async_bridge import run_async

            run_async(session.commit(positions))
            data = {"committed": len(positions)}
        elif operation == "session_pause":
            session = self._sessions.get(str(params["session_key"]))
            if session is None:
                raise ConnectorError("session not found", code="SESSION_NOT_FOUND")
            from flow_engine.connectors.async_bridge import run_async

            run_async(session.pause())
            data = {}
        elif operation == "session_resume":
            session = self._sessions.get(str(params["session_key"]))
            if session is None:
                raise ConnectorError("session not found", code="SESSION_NOT_FOUND")
            from flow_engine.connectors.async_bridge import run_async

            run_async(session.resume())
            data = {}
        elif operation == "session_close":
            session_key = str(params["session_key"])
            session = self._sessions.pop(session_key, None)
            if session is not None:
                from flow_engine.connectors.async_bridge import run_async

                run_async(session.close())
            data = {}
        elif operation == "publish_bytes":
            producer_id = str(params["producer_id"])
            from flow_engine.connectors.async_bridge import run_async

            result = run_async(
                kafka_ops.send_message(
                    self._producer_ref(producer_id),
                    self._defaults,
                    value=params.get("value"),
                    key=params.get("key"),
                    partition=params.get("partition"),
                    headers=params.get("headers"),
                )
            )
            data = result
        else:
            raise ConnectorError(f"unknown operation {operation!r}", code="UNKNOWN_OPERATION")

        took_ms = (time.monotonic() - t0) * 1000.0
        meta: dict[str, Any] = {"instance": self.instance_id}
        if params.get("consumer_id"):
            meta["consumer_id"] = params["consumer_id"]
        if params.get("producer_id"):
            meta["producer_id"] = params["producer_id"]
        return ok_envelope(data, instance=self.instance_id, took_ms=took_ms, extra_meta=meta)

    def cap_size(self, size: int | None) -> int:
        return self._pipeline.cap_size(size)

    def close(self) -> None:
        from flow_engine.connectors.async_bridge import run_async

        for key in list(self._sessions.keys()):
            session = self._sessions.pop(key, None)
            if session is not None:
                try:
                    run_async(session.close())
                except Exception:  # noqa: BLE001
                    logger.debug("session close failed key=%s", key, exc_info=True)
        self._producer_clients.clear()


class KafkaBackend:
    kind = "kafka"

    def __init__(self) -> None:
        self._handles: dict[str, KafkaClusterHandle] = {}

    def bind_instances(
        self,
        cfg: KafkaConfig,
    ) -> dict[str, KafkaClusterHandle]:
        consumers, producers = build_kafka_indexes(cfg)
        out: dict[str, KafkaClusterHandle] = {}
        defaults = cfg.defaults

        for iid, cluster in cfg.instances.items():
            raw_inst = cluster.model_dump()
            prot = merged_protection(defaults.model_dump(), raw_inst)
            timeout = float(defaults.request_timeout_sec)
            pipeline = ProtectionPipeline(prot, request_timeout_sec=timeout)
            handle = KafkaClusterHandle(
                iid,
                defaults=defaults,
                consumers=consumers,
                producers=producers,
                pipeline=pipeline,
            )
            self._handles[iid] = handle
            out[iid] = handle
        return out

    def close_all(self) -> None:
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()
