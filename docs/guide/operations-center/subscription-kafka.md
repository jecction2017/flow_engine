# Kafka 订阅部署

## 概述

`schedule_type=subscription` 时，部署常驻 **Ingress** 进程消费 Kafka 消息；每条消息解码后触发一次流程运行（插入 `fe_deploy_run`）。成功处理后提交 offset（`commit_policy: on_success`）。

---

## 前置条件

1. 数据字典 `middleware.kafka` 中配置好 consumer（见 [Kafka 集成](../integrations/kafka.md)）
2. 流程已提交版本
3. Worker 在线
4. `schedule_config` 为合法 `SubscriptionSpec`

---

## schedule_config 示例

```json
{
  "schema_version": 1,
  "subscription": {
    "consumer_id": "memory.alerts.default",
    "partitions": null,
    "start_position": "latest"
  },
  "consumption": {
    "batch_max_records": 50,
    "poll_timeout_ms": 2000,
    "commit_policy": "on_success",
    "max_retries": 3,
    "dlq": {
      "producer_id": "soc_cluster_a.alerts.dlq"
    }
  },
  "dispatch": {
    "max_in_flight": 4,
    "run_timeout_s": 120
  },
  "parse": {
    "codec": "json",
    "transform": "mapping",
    "mapping": {
      "mode": "rules",
      "rules": [
        {"source": "alert_id", "target": "alert.id"},
        {"source": "severity", "target": "alert.severity"}
      ]
    }
  },
  "ingress_policy": {
    "max_restarts": 5,
    "restart_backoff_s": 15
  }
}
```

> 若消息体已是扁平字段且与 `global_ns` 键名一致，用 `{"mode": "spread"}` 即可。

---

## 消息 → global_ns

1. 消费原始 Kafka 记录
2. `parse.codec=json` 解码 UTF-8 JSON
3. `parse.transform=mapping` → 调用 `apply_context_mapping`（与测试中心相同）
4. 或 `parse.transform=script` → Starlark 脚本读 `payload` 变量并返回 dict
5. 合并 `event_meta`（topic、partition、offset、correlation_id 等）后作为流程初始上下文

---

## 幂等与 DLQ

- `fe_subscription_dedup` 表记录消息位置账本，避免重复处理
- 重试耗尽后可写入 `consumption.dlq` 指定的 producer
- 部署详情页可查看订阅消息与失败记录

---

## 与脚本 kafka_receive 的区别

| | 订阅部署 | 脚本 `kafka_receive` |
|---|----------|----------------------|
| 触发方式 | 每条消息自动启动流程 | 节点内主动 poll |
| 配置位置 | 部署 `schedule_config` | 数据字典 consumer_id |
| 适用 | 事件驱动流水线 | 流程内批量拉取 |

---

## 运维注意

- `subscription.consumer_id` 须与数据字典 ID 完全一致（`cluster.topic.consumer_name`）
- `start_position` 可覆盖字典默认策略
- Ingress 崩溃按 `ingress_policy` 指数退避重启
- 建议 `single_active` + `target_workers=1` 避免重复消费（视 topic 分区策略而定）

---

## 相关文档

- [调度方式](scheduling.md)
- [Kafka 集成](../integrations/kafka.md)
- [上下文映射](../test-center/context-mapping.md)
