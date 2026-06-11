# 测试断言

## 概述

断言对比运行结束时的 **global_ns**（`assertions.py` 用点分路径读取）。方案级 `assertions` 与 lookup 行内 `_expect` 派生规则**合并执行**。`flow_state != COMPLETED` 时直接 `verdict=fail`。

---

## 规则结构（JSON 数组）

```json
[
  { "id": "ok", "op": "eq", "path": "out.ok", "expected": true }
]
```

| 字段 | 说明 |
|------|------|
| `id` | 可选，默认 `rule_0`… |
| `op` | 比较方式 |
| `path` | `global_ns` 点分路径（`op=starlark` 时可省略） |
| `expected` | 期望值 |
| `expr` / `starlark_expr` | `op=starlark` 时的脚本 |

---

## 支持的 op

| op | 说明 |
|----|------|
| `eq` / `ne` | 严格相等 / 不等 |
| `contains` | `str(expected) in str(actual)` |
| `regex` | `re.search(expected, str(actual))` |
| `json_match` / `json_subset` | **别名**，expected 为 actual 的递归子集 |
| `starlark` | 执行表达式；返回 bool 或 `{pass, message}` |

---

## json_match 示例

只关心子集字段：

```json
{
  "id": "payment_shape",
  "op": "json_match",
  "path": "out.payment",
  "expected": {"status": "SUCCESS", "currency": "CNY"}
}
```

---

## starlark 示例

```json
{
  "id": "items_contains_sku",
  "op": "starlark",
  "expr": "any([x.get('sku') == 'A001' for x in (global_ns.get('out', {}).get('items') or [])])"
}
```

或返回带消息：

```json
{
  "op": "starlark",
  "expr": "{\"pass\": global_ns.get('out', {}).get('code') == 200, \"message\": \"bad code\"}"
}
```

---

## 用例行内 _expect

Runner 会剥离 `_expect` / `_expect.*`，不注入 global_ns（`strip_expect_keys`）。

### 嵌套对象形式

```json
{
  "case_id": "c1",
  "input": 10,
  "_expect": {
    "path": "out.result",
    "op": "eq",
    "expected": 20
  }
}
```

`equals` 可作为 `expected` 的别名。

### 扁平形式

```json
{
  "case_id": "c1",
  "_expect.path": "out.result",
  "_expect.equals": 20,
  "_expect.op": "eq"
}
```

---

## 结果说明

| 情况 | verdict |
|------|---------|
| 流程未完成 | fail（`reason: flow_not_completed`） |
| 无规则 | pass |
| 全部规则通过 | pass |
| 任一失败 | fail |

---

## 相关文档

- [方案与批次](plans-and-batches.md)
- [理解测试结果](acceptance-and-results.md)
- 仓库详解：[test-center-assertions.md](../../test-center-assertions.md)
