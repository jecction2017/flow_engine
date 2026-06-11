# 调用为何被抑制

## 概述

说明哪些内置函数属于「副作用」、为何在调试/试运行/测试里常被抑制，以及如何通过**规则列表**（界面 JSON，技术字段名多为 `capability_policy` 或节点上的 `capability_overrides`）做放行（allow）或重定向（redirect）。

## 界面上的策略入口（对照）

| 界面名称 | 说明 | 技术字段 |
|----------|------|----------|
| 环境能力策略 | 环境（Profile）配置，按 debug / shadow / production 分别保存 | `system_capability_policy` |
| 部署附加策略 | 创建部署时填写，仅该部署运行生效 | `capability_policy` |
| 本次附加策略 | 节点调试、流程试运行、用户脚本调试等折叠区，只影响**当前这一次** | 请求体 `capability_policy` |
| 测试方案 · 默认附加策略 / 测试批次 · 附加策略 | 测试中心；批次可覆盖方案默认 | `capability_policy` |
| 节点能力策略（仅此节点） | 写在流程节点上，随版本发布 | `capability_overrides` |

## 安全边界（重要）

用户脚本调试、节点调试、流程试运行、测试中心均属于「临时 / 受控执行」入口：服务端固定为**调试模式**（`RunMode.DEBUG`），默认抑制副作用类内置函数。真实生产行为须通过**部署**启动。

## 相关文档

- [默认抑制行为](default-behavior.md)
- [规则 JSON](policy-rules-json.md)
- [各层优先级](layer-priority.md)
