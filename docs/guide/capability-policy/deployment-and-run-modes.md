# 部署与运行模式

## 概述

部署使用所选 `RunMode`（如 production / shadow）。创建部署时的 **部署附加策略** 与节点、环境能力策略、模式默认按 [各层优先级](layer-priority.md) 合并。

## 最佳实践

把生产安全边界写在策略里而不是写在脚本里：例如仅允许访问明确白名单域名，或对写入类 builtin 强制 REDIRECT 到网关。

## 相关文档

- [运行中心：部署管理](../operations-center/deployments.md)
- [环境能力策略](../profiles/system-capability-policy.md)
