# 命名空间与 Schema

## 概述

Lookup 的**命名空间**是逻辑表名；**schema** 定义列结构（主要用于界面校验与文档）。数据按 **Profile** 隔离。

脚本 `lookup_query` 过滤时匹配**行数据的键**，不强制校验 schema 列是否存在。

---

## 命名空间

- Profile 内唯一字符串
- 脚本与测试方案通过名称引用，如 `test_payment_cases`
- 存储路径：`lookup/profiles/{profile}/{namespace}.json`（实现细节）

---

## Schema

界面中定义字段名与类型，便于：

- 表单编辑与导入校验
- 团队约定列含义

**运行时**：`lookup_query` 的 filter 键须在**行 dict** 中存在；行可含 schema 未声明的额外键（取决于导入/编辑方式）。

---

## lookup_query 过滤语义

```python
lookup_query("my_ns", {"field": "value", "enabled": True})
```

- 多键为 **AND** 关系
- 值比较为 **严格相等**（`==`）
- 键不在行中 → 该行不匹配
- 空 filter `{}` → 全部行，**上限 10_000**

表达式过滤（`field == 1 && other in [1,2]`）仅 **HTTP API** `lookup_query_page` 支持，不在 Starlark builtin 中。

---

## 与测试中心

测试方案绑定命名空间；每行通过 **context_mapping**（`spread`/`wrap`/`rules`/`script`）注入 `global_ns`，不是扁平 `字段→$.global` 映射。

---

## 相关文档

- [表与行数据](tables-and-rows.md)
- [上下文映射](../test-center/context-mapping.md)
