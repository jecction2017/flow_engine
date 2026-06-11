# 部署常见问题

## Q: 创建部署时选不到草稿？

部署必须绑定 **已提交版本**（V1、V2…）。在 Flow Studio 先 **提交版本**。

---

## Q: 部署创建后为什么不运行？

检查清单：
1. 部署是否已 **启动**（非仅保存）
2. **Worker** 是否在线（运行中心 → 工作节点）
3. 调度配置是否正确（cron 表达式、Kafka consumer_id）
4. `target_workers` 是否限制了不存在的 Worker

---

## Q: production 和 shadow 有什么区别？

两者都不是 debug。具体副作用行为由 Profile 的 `system_capability_policy` 对应段 + 部署 `capability_policy` 决定。shadow 常用于旁路观察、灰度对比。

---

## Q: 如何更新流程逻辑？

1. Flow Studio 修改并 **提交新版本**
2. 编辑部署切换版本，或新建部署
3. 重启/启动部署使配置生效

---

## Q: Kafka 订阅部署收不到消息？

- 检查数据字典 `middleware.kafka` 中 consumer 配置
- 确认 `consumer_id` 与部署 subscription 一致
- 查看部署详情 → Kafka 订阅面板与失败消息
- 确认 topic 有数据、group_id 无冲突

---

## Q: 多 Worker 会重复执行吗？

取决于 **Worker 策略**（`single_active` vs `multi_active`）与调度类型。Kafka 订阅通常需 `single_active` 或正确分片。

---

## 相关文档

- [部署管理](../operations-center/deployments.md)
- [调度方式](../operations-center/scheduling.md)
- [工作节点](../operations-center/workers.md)
