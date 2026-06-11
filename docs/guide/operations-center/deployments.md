# 部署管理

## 概述

在 **运行中心 → 部署管理** 创建与维护部署：绑定流程版本、Profile、RunMode、调度与 Worker 策略。

## 操作步骤

1. **新建部署**：选择流程、**已提交版本**（非草稿）、Profile、RunMode。
2. 配置 **部署附加策略**（`capability_policy`）与节点策略按层合并。
3. 选择调度类型：一次性 / cron / Kafka 订阅。
4. 保存后在 **运行记录** 查看执行情况。

## 相关文档

- [第一次部署](../getting-started/first-deployment.md)
- [调度方式](scheduling.md)
- [部署与运行模式](../capability-policy/deployment-and-run-modes.md)
