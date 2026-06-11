# 各层优先级

## 概述

运行时合并顺序（高 → 低）；越靠前越先命中匹配：

1. **节点能力策略** — 节点字段 `capability_overrides`（节点编辑器「节点能力策略」）
2. **本次运行附加** — 同一次执行传入的规则列表（技术名 `deployment_capability_policy`）：部署「部署附加策略」、试运行「本次附加策略」、调试与测试请求里的 `capability_policy` 等（入口名称不同，语义相同）
3. **环境能力策略** — 当前 Profile、对应当前 `RunMode` 的 `system_capability_policy`
4. **运行模式内置默认** — 与 `RunMode` 绑定的兜底（调试模式默认抑制副作用）

## 结果说明

调试/试运行里的「本次附加策略」与创建部署时的「部署附加策略」处于**同一优先级层**，都高于环境能力策略；节点上的策略又高于它们。

## 相关文档

- [试运行与测试入口](trial-debug-and-test.md)
- [部署与运行模式](deployment-and-run-modes.md)
