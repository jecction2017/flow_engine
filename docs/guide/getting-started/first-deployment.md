# 第一次创建部署

## 概述

把流程的指定版本绑定到环境与调度，由 Worker 执行。生产行为通过部署触发，不能依赖试运行入口。

## 操作步骤

1. 打开 **运行中心 → 部署管理**，新建部署。
2. 选择流程、**已提交版本**、Profile、**RunMode**（如 production / shadow）。
3. 配置调度（一次性 / cron / 订阅）与 Worker 策略。
4. 保存后查看运行记录与链路详情。

## 相关文档

- [部署管理](../operations-center/deployments.md)
- [部署与运行模式](../capability-policy/deployment-and-run-modes.md)
