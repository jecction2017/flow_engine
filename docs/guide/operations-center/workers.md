# 工作节点

## 概述

**Worker** 是执行部署的后台进程。通过 CLI `flow-worker start` 启动，向控制面注册心跳、拉取分配到的部署任务并运行流程。在 **运行中心 → 工作节点** 查看在线状态与基本信息。

---

## 启动 Worker

```bash
flow-worker start --control-url http://localhost:8000
```

具体参数以项目 CLI 帮助为准（`flow-worker --help`）。Worker 需能访问：

- 控制面 API（注册、心跳、拉取任务）
- 流程运行所需的外部依赖（Kafka、HTTP、ES 等，按部署 Profile）

---

## 界面信息

工作节点列表通常展示：

| 字段 | 说明 |
|------|------|
| Worker ID | 唯一标识 |
| 状态 | 在线 / 离线 |
| 最后心跳 | 最近一次心跳时间 |
| 分配部署 | 当前负责的部署（若有） |

心跳超时后标记离线，相关部署可能无法触发直到 Worker 恢复。

---

## 部署 Worker 策略

创建部署时配置：

| 策略 | 说明 |
|------|------|
| **single_active** | 同一部署仅一个 Worker 活跃执行，避免重复消费 |
| **multi_active** | 允许多 Worker 并行（需流程与调度支持） |
| **target_workers** | 限定可执行该部署的 Worker 列表；空则任意在线 Worker |

Kafka 订阅部署通常配合 `single_active` 或明确 partition 分配，避免重复处理同一消息。

---

## 扩容与缩容

1. 在新机器启动 `flow-worker start`
2. 确认工作节点列表出现新实例
3. 部署若未限定 target_workers，新 Worker 可参与任务分配
4. 缩容：优雅停止 Worker 进程，等待进行中 run 完成

---

## 故障排查

| 现象 | 可能原因 |
|------|----------|
| 无在线 Worker | 进程未启动、网络不通、control-url 错误 |
| 部署不执行 | 部署未启动、无 Worker 匹配 target_workers |
| 重复执行 | multi_active + 非幂等流程；订阅未正确分片 |
| 心跳频繁离线 | 时钟漂移、负载过高、API 超时 |

---

## 相关文档

- [部署管理](deployments.md)
- [调度方式](scheduling.md)
- [故障排查](troubleshooting.md)
- [安装与访问](../getting-started/install-and-access.md)
