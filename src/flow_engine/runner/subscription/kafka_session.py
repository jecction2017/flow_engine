"""Subscription session adapter over Kafka connector handle."""

from __future__ import annotations

import logging
from typing import Any

from flow_engine.connectors.backends.kafka.messages import BusMessage, Position

logger = logging.getLogger(__name__)


class ConnectorSubscriptionSession:
    """Async session wrapping KafkaClusterHandle session_* operations."""

    def __init__(
        self,
        handle: Any,
        *,
        session_key: str,
        consumer_id: str,
    ) -> None:
        self._handle = handle
        self._session_key = session_key
        self._consumer_id = consumer_id

    async def poll(self, *, max_records: int, timeout_ms: int) -> list[BusMessage]:
        import asyncio

        result = await asyncio.to_thread(
            self._handle.execute,
            "session_poll",
            session_key=self._session_key,
            consumer_id=self._consumer_id,
            max_records=max_records,
            timeout_ms=timeout_ms,
            for_subscription=True,
        )
        if not result.get("ok"):
            logger.warning(
                "subscription session_poll failed session_key=%s consumer_id=%s error=%s",
                self._session_key,
                self._consumer_id,
                result.get("error"),
            )
            return []
        data = result.get("data") or {}
        messages = data.get("messages") or []
        return list(messages)

    async def commit(self, positions: list[Position]) -> None:
        import asyncio

        await asyncio.to_thread(
            self._handle.execute,
            "session_commit",
            session_key=self._session_key,
            positions=[
                {"topic": p.topic, "partition": p.partition, "offset": p.offset}
                for p in positions
            ],
        )

    async def pause(self) -> None:
        import asyncio

        await asyncio.to_thread(
            self._handle.execute,
            "session_pause",
            session_key=self._session_key,
        )

    async def resume(self) -> None:
        import asyncio

        await asyncio.to_thread(
            self._handle.execute,
            "session_resume",
            session_key=self._session_key,
        )

    async def close(self) -> None:
        import asyncio

        await asyncio.to_thread(
            self._handle.execute,
            "session_close",
            session_key=self._session_key,
        )
