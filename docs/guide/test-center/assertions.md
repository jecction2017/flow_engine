# 测试断言

## 概述

断言对比对象是运行结束时的 `global_ns`。方案级 `assertions` 与用例行内 `_expect` 会合并执行，结果显示为 `verdict=pass/fail`。

## 规则结构（JSON 数组）

```json
[
  { "id": "ok", "op": "eq", "path": "out.ok", "expected": true }
]
```

- **path**：从 `global_ns` 读取的点路径（`a.b.c`）
- **op**：比较方式（见下表）
- **id**：可选，便于定位失败

## 支持的 op

| op | 说明 |
|----|------|
| `eq` / `ne` | 严格相等 / 不等 |
| `contains` | 字符串包含（值转字符串） |
| `regex` | 正则匹配 |
| `json_match` | expected 是 actual 的子集（忽略多余字段） |
| `starlark` | 执行表达式，可读 `global_ns`；返回 bool 或 `{pass, message}` |

## 示例：json_match

```json
[
  {
    "id": "payment_subset",
    "op": "json_match",
    "path": "out.payment",
    "expected": { "status": "SUCCESS", "currency": "CNY" }
  }
]
```

## 示例：starlark

```json
[
  {
    "id": "items_contains_sku",
    "op": "starlark",
    "expr": "{'pass': any([x.get('sku') == 'A001' for x in (global_ns.get('out', {}).get('items') or [])]), 'message': 'missing sku A001'}"
  }
]
```

## 用例行内 _expect

Runner 会剥离 `_expect` / `_expect.*`，避免注入 global_ns，并自动生成断言规则：

```json
{
  "case_id": "c1",
  "input": 1,
  "_expect.path": "out.result",
  "_expect.equals": 2
}
```

## 结果说明

- 流程未完成：直接 `verdict=fail`
- 无规则：`verdict=pass`
- 否则：全部规则通过才 `pass`

## 进阶

更完整说明见仓库文档 [test-center-assertions.md](../../test-center-assertions.md)。

## 相关文档

- [理解测试结果](acceptance-and-results.md)
- [方案与批次](plans-and-batches.md)
