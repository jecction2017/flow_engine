# 脚本中的 lookup_query

## 概述

`lookup_query(namespace, filter)` 在 Starlark 脚本中查询当前 Profile 下的 Lookup 表。

- **category** = `lookup` → debug 模式下**不被默认抑制**
- **filter** 参数名在 Starlark 中为 `filter`（非 `filters`）
- 过滤语义：**等值 AND**（所有键须在行中存在且值相等）
- 空 filter → 返回全部行，**最多 10_000 行**（`MAX_QUERY_ROWS`）

> HTTP API 的 `lookup_query_page` 支持表达式过滤（`==`、`in`、`>` 等），**Starlark builtin 不支持表达式**，仅 dict 等值匹配。

---

## 基本用法

```python
def find_rule():
    severity = resolve("$.global.alert.severity")
    rows = lookup_query("alert_routing_rules", {"severity": severity, "enabled": True})
    if not rows:
        return {"rule": None}
    return {"rule": rows[0]}

find_rule()
```

### 参数

| 参数 | 说明 |
|------|------|
| `namespace` | Lookup 命名空间 |
| `filter` | 可选 dict；键须在**行数据**中存在，否则无匹配 |

### 返回值

匹配行的 list；无匹配为 `[]`。

---

## 常见模式

### 取首条

```python
rows = lookup_query("config_table", {"key": "timeout"})
value = rows[0]["value"] if rows else 30
```

### 全表（注意上限）

```python
all_rules = lookup_query("routing_rules", {})
# 超过 10000 行时仅返回前 10000 行
```

### 未知 filter 键

```python
lookup_query("ns", {"nonexistent_column": 1})  # → []
```

filter 键不在行中则 `_filter_row` 返回 false，**不校验 schema**。

---

## 与 dict_get 的选择

| 场景 | 推荐 |
|------|------|
| YAML 模块树配置 | `dict_get` |
| 多行表、用例、可 CRUD 数据 | `lookup_query` |

---

## 相关文档

- [命名空间与 schema](namespace-and-schema.md)
- [表与行数据](tables-and-rows.md)
