# 测试方案与批次

## 概述

**测试方案**绑定流程、版本通道、lookup 命名空间、Profile、**context_mapping**（模式对象）、assertions、mock_config、capability_policy。

**测试批次**是一次批量执行；可覆盖方案默认的 `capability_policy` 与 `mock_config`。

API 默认 context_mapping：`{"mode": "spread"}`（`http_api` 创建方案时）。

---

## context_mapping

不是「列名 → `$.global` 路径」扁平表，而是带 `mode` 的对象：

| mode | 用途 |
|------|------|
| `spread` | 整行并入 global_ns（默认） |
| `wrap` | 包进 `wrap_key` |
| `rules` | `source` 列 → `target` 点分路径 |
| `script` | Starlark 转换 |

见 [上下文映射](context-mapping.md)。

---

## 创建方案

1. 测试中心 → 新建
2. 流程、版本通道、lookup 命名空间、Profile
3. context_mapping、assertions、mock_config
4. 保存 → 运行

---

## 批次

- 继承方案配置
- 批次级可覆盖 `capability_policy`、`mock_config`
- 每行 lookup → 独立 run + verdict
- API：`POST /api/test-plans/{id}/batches/compare` 可对比两次批次

---

## 相关文档

- [测试断言](assertions.md)
- [Mock 与录制回放](mock-and-replay.md)
- [第一次测试](../getting-started/first-test-plan.md)
