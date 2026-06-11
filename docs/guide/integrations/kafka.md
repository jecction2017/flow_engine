# Kafka 集成

## 概述

配置在数据字典 `middleware.kafka`；脚本用 `kafka_receive` / `kafka_send`（**category=integration**，debug 默认抑制）。订阅部署用 `schedule_config` 的 `SubscriptionSpec`，见 [Kafka 订阅部署](../operations-center/subscription-kafka.md)。

---

## consumer_id / producer_id

格式：`{cluster_id}.{topic_name}.{consumer_or_producer_name}`

示例：`soc_cluster_a.alerts.ingress`、`soc_cluster_a.alerts.dlq`

由 `config_kafka.parse_consumer_id` 解析。

---

## kafka_receive

```python
def poll_alerts():
    recv = kafka_receive(
        "soc_cluster_a.alerts.ingress",
        max_records=10,
        timeout_ms=3000,
    )
    if not recv.get("ok"):
        return {"alarms": [], "error": recv.get("error")}
    messages = recv.get("data", {}).get("messages", [])
    return {"alarms": [m.get("value") for m in messages], "count": len(messages)}

poll_alerts()
```

### 成功返回

```json
{
  "ok": true,
  "data": {
    "messages": [
      {"topic": "...", "partition": 0, "offset": 1, "key": null, "value": {}, "headers": {}, "timestamp_ms": 0}
    ]
  },
  "meta": {"took_ms": 12, "consumer_id": "..."}
}
```

### 被抑制

```json
{
  "ok": false,
  "error": {"code": "SUPPRESSED", "message": "integration suppressed"},
  "_suppressed": true
}
```

---

## kafka_send

```python
def send_dlq():
    payload = resolve("$.global.failed_record")
    r = kafka_send("soc_cluster_a.alerts.dlq", value=payload, key=payload.get("id"))
    return {"ok": r.get("ok"), "data": r.get("data"), "meta": r.get("meta")}

send_dlq()
```

成功时 `data` 含 `topic`、`partition`、`offset`。

---

## 数据字典

见 `middleware.kafka` 模块；`transport: memory` 可无真实 broker 联调。

---

## 订阅 vs 脚本消费

| 方式 | 配置 | 用途 |
|------|------|------|
| 订阅部署 | `schedule_config` SubscriptionSpec | 每消息触发流程 |
| kafka_receive | 脚本内调用 | 流程内批量 poll |

---

## 相关文档

- [Kafka 订阅部署](../operations-center/subscription-kafka.md)
- [调度方式](../operations-center/scheduling.md)
