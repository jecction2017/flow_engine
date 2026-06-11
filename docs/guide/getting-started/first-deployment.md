# 第一次创建部署

## 概述

**部署**把流程的**已提交版本**绑定到环境、运行模式与调度，由 **Worker** 执行。生产环境的真实副作用（HTTP、Kafka 等）通过部署产生，**不能**依赖试运行或测试中心入口。

---

## 前置条件

- [ ] 流程已在 Flow Studio **提交版本**（V1 等）
- [ ] 目标 **Profile** 已配置数据字典与能力策略
- [ ] 至少一个 **Worker** 在线（`flow-worker start`）
- [ ] 试运行或测试已验证基本逻辑

---

## 操作步骤

### 1. 新建部署

**运行中心 → 部署管理 → 新建部署**

| 字段 | 说明 |
|------|------|
| 名称 | 便于识别的部署名 |
| 流程 | 选择目标流程 |
| 版本 | **必须**选已提交版本，不能选草稿 |
| Profile | 运行环境 |
| RunMode | `production` 或 `shadow` |

### 2. 配置调度

| 类型 | 适用 |
|------|------|
| once | 手动触发 |
| cron | 定时，如 `0 */5 * * *` |
| subscription | Kafka 消息驱动 |

详见 [调度方式](../operations-center/scheduling.md)。

### 3. Worker 策略

- `single_active` — 单 Worker 执行（订阅类常用）
- `multi_active` — 多 Worker 并行
- 可选 **目标 Worker** 列表

### 4. 部署附加策略（可选）

若生产需允许集成调用，配置 `capability_policy`。常与 Profile 的 production 段系统策略配合。

### 5. 保存并启动

保存后在部署详情 **启动**。在 **运行记录** 查看执行情况；失败时看 [链路、指标与日志](../operations-center/spans-metrics-logs.md)。

---

## 与试运行的关键区别

| | 试运行 | 部署 |
|---|--------|------|
| RunMode | 固定 debug | production / shadow |
| 副作用 | 默认抑制 | 按策略真实执行 |
| 版本 | 草稿亦可 | 仅 Vn |
| 触发 | 手动 | 调度 / 订阅 |

---

## 下一步

- 配置监控与告警（Spans、日志）
- shadow 部署对比生产行为
- 流程更新后提交新版本并切换部署版本

---

## 相关文档

- [部署管理](../operations-center/deployments.md)
- [工作节点](../operations-center/workers.md)
- [部署与运行模式](../capability-policy/deployment-and-run-modes.md)
- [FAQ：部署](../faq/deployment.md)
