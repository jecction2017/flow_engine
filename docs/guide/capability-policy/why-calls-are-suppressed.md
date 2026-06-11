# 调用为何被抑制

## 概述

能力策略按 builtin 的 **`category`** 匹配规则（非简单按 `side_effects`）。debug/shadow 下系统默认对 `integration`、`db_read`、`db_write`、`mq_publish` 类别执行 **SUPPRESS**。

试运行、节点调试、脚本调试、测试中心均由服务端锁定 **`RunMode.DEBUG`**，因此 HTTP、Kafka、ES 等集成调用常被抑制。`dict_get`、`lookup_query` 等 **dictionary/lookup 类别默认不抑制**。

---

## 界面上的策略入口

| 界面名称 | 技术字段 | 优先级层 |
|----------|----------|----------|
| 节点能力策略 | `capability_overrides` | 最高 |
| 本次附加策略 / 部署附加策略 / 测试 capability_policy | `capability_policy` → `deployment_capability_policy` | 同一层 |
| 环境能力策略 | `system_capability_policy`（按 debug/shadow/production 分段） | 次之 |
| （内置） | `system_default_policy(mode)` | 最低 |

「本次附加」与「部署附加」**不是两层**，而是同一 `deployment_capability_policy` 槽位在不同入口填入。

---

## 被抑制时发生什么

- 函数体**不执行**
- 返回注册表 `suppress_result`（含 `SUPPRESSED` / `_suppressed`）
- 脚本须区分抑制与真实错误

---

## 如何放行

试运行/调试/测试：在 **本次附加策略** 添加 allow 规则。生产：配置 Profile production 段 + 部署 `capability_policy`。

```json
[{"builtin_name": "http_call", "action": "allow"}]
```

---

## 安全边界

真实生产副作用须通过 **部署**（production/shadow），具备调度、Worker、审计等完整路径。

---

## 相关文档

- [默认抑制行为](default-behavior.md)
- [副作用 builtin](side-effects.md)
- [各层优先级](layer-priority.md)
- [规则 JSON](policy-rules-json.md)
