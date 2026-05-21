"""Shared memory-transport Kafka dictionary for subscription tests."""

from __future__ import annotations

MEMORY_KAFKA_DICT: dict = {
    "middleware": {
        "kafka": {
            "defaults": {},
            "instances": {
                "memory": {
                    "transport": "memory",
                    "topics": {
                        "alerts": {
                            "consumers": {
                                "default": {
                                    "group_id": "g1",
                                    "serializers": {"value": "json"},
                                    "strategy": "earliest",
                                }
                            },
                        },
                        "alerts_dlq": {
                            "producers": {
                                "dlq": {
                                    "serializers": {"value": "bytes"},
                                }
                            },
                        },
                    },
                }
            },
        }
    }
}

MEMORY_CONSUMER_ID = "memory.alerts.default"
MEMORY_DLQ_PRODUCER_ID = "memory.alerts_dlq.dlq"
