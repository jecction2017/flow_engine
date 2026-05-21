#!/usr/bin/env python3
"""向 simple_alarms 发送示例 JSON（需 pip install aiokafka）。"""

from __future__ import annotations

import asyncio
import json
import sys

SAMPLES = [
    {"id": "2026040101", "activity_level": "low", "activity_feature": "app_type_01"},
    {"id": "2026040102", "activity_level": "high", "activity_feature": "app_type_02"},
    {"id": "2026040103", "activity_level": "medium", "activity_feature": "app_type_01"},
]

BOOTSTRAP = "localhost:9092"
TOPIC = "simple_alarms"


async def main() -> None:
    try:
        from aiokafka import AIOKafkaProducer
    except ImportError:
        print("请先安装: pip install aiokafka", file=sys.stderr)
        sys.exit(1)

    producer = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP)
    await producer.start()
    try:
        for doc in SAMPLES:
            raw = json.dumps(doc, ensure_ascii=False).encode("utf-8")
            meta = await producer.send_and_wait(TOPIC, raw, key=doc["id"].encode())
            print(f"sent id={doc['id']} partition={meta.partition} offset={meta.offset}")
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
