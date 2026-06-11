# 调度方式

## 概述

部署 `schedule_type` 支持三种值：`once`、`cron`、`subscription`。配置保存在 `schedule_config` JSON 中。创建/编辑部署时在 **运行中心 → 部署管理** 配置。

---

## once（一次性）

手动或创建后单次触发执行。

### 约束（代码校验）

- `worker_policy.target_workers` **必须为 1**（`http_api._validate_worker_policy`）

### 执行后状态

Worker 完成单次 run 后自动更新部署状态：

- 流程 **COMPLETED** → 部署 `stopped`
- 否则 → 部署 `failed`

---

## cron（定时）

须提供 `schedule_config.cron_expr`：

```json
{
  "cron_expr": "0 */5 * * *"
}
```

引擎可能持久化 `last_run_at`、`next_run_at` 等辅助字段。修改表达式后保存并确保部署处于 **启动** 状态。

| 表达式示例 | 含义 |
|------------|------|
| `0 */5 * * *` | 每 5 分钟 |
| `0 0 * * *` | 每天 0 点 |
| `0 9 * * 1-5` | 工作日 9 点 |

时区以服务器/Worker 为准。

---

## subscription（Kafka 订阅）

`schedule_config` 须为完整的 **SubscriptionSpec** JSON（`runner/subscription/spec.py`），非扁平字段。

### 结构概要

```json
{
  "schema_version": 1,
  "subscription": {
    "consumer_id": "soc_cluster_a.alerts.ingress",
    "producer_id": "soc_cluster_a.alerts.dlq",
    "partitions": [0, 1],
    "start_position": "latest",
    "filters": {},
    "extensions": {}
  },
  "consumption": {
    "batch_max_records": 100,
    "poll_timeout_ms": 1000,
    "commit_policy": "on_success",
    "max_retries": 3,
    "retry_backoff_ms": 1000,
    "dlq": {"producer_id": "soc_cluster_a.alerts.dlq"}
  },
  "dispatch": {
    "max_in_flight": 8,
    "run_timeout_s": 300
  },
  "parse": {
    "codec": "json",
    "transform": "mapping",
    "mapping": {"mode": "spread"}
  },
  "ingress_policy": {
    "max_restarts": 3,
    "restart_backoff_s": 15
  }
}
```

### 关键字段

| 段 | 字段 | 说明 |
|----|------|------|
| `subscription` | `consumer_id` | 数据字典 Kafka consumer ID |
| `subscription` | `start_position` | 可覆盖字典消费策略 |
| `consumption` | `commit_policy` | 固定 `on_success` |
| `parse` | `transform` | `mapping` 或 `script` |
| `parse` | `mapping` | 同测试中心 context_mapping（spread/wrap/rules） |
| `parse` | `script` | transform=script 时的 Starlark |

详见 [Kafka 订阅部署](subscription-kafka.md)。

---

## Worker 策略（与调度配合）

| 字段 | 说明 |
|------|------|
| `type` | `single_active` / `multi_active` |
| `target_workers` | 目标 Worker 数量；once 必须为 1 |
| `max_restarts` | subscription Ingress 崩溃最大重启次数 |

`worker_targeting` 支持 `any` / `pin` / `pool` 模式，pin 与 pool 对 `target_workers` 有额外约束。

---

## 配置步骤

1. 运行中心 → 部署管理 → 新建/编辑
2. 选择 `schedule_type`
3. 填写对应 `schedule_config`
4. 配置 `worker_policy`
5. 保存 → 启动部署
6. 在运行记录观察触发

---

## 相关文档

- [部署管理](deployments.md)
- [Kafka 订阅部署](subscription-kafka.md)
- [Kafka 集成](../integrations/kafka.md)
