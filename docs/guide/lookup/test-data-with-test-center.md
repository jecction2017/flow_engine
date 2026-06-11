# Lookup 与测试中心

## 概述

测试方案绑定 **test_ns_code**（Lookup 命名空间）。Runner 拉取该命名空间行（经 `lookup_query_page`，有分页上限），**每行一条用例**。

行数据经 **context_mapping** 转为 `global_ns` 片段后执行流程；默认 `{"mode": "spread"}` 即整行并入。

---

## 推荐工作流

```
1. Lookup Tab 建命名空间 + schema + 用例行
2. 测试中心建方案，绑定该命名空间
3. 配置 context_mapping（spread 或 rules）
4. 配置 assertions / mock_config
5. 运行批次 → 查看 verdict
```

---

## context_mapping 示例

### spread（最简单）

Lookup 行：`{"case_id":"c1","amount":100}`  
mapping：`{"mode":"spread"}`  
→ `global_ns.case_id`、`global_ns.amount`

### rules（结构化）

```json
{
  "mode": "rules",
  "rules": [
    {"source": "amount", "target": "order.amount"}
  ]
}
```

### 行内断言

```json
{"case_id": "c1", "amount": 100, "_expect.path": "out.ok", "_expect.equals": true}
```

`_expect` 键不会进入 global_ns。

---

## 与 Profile

测试方案选择 Profile，决定 lookup 数据路径与 `dict_get` 解析的字典树。

---

## 相关文档

- [上下文映射](../test-center/context-mapping.md)
- [测试方案与批次](../test-center/plans-and-batches.md)
- [表与行数据](tables-and-rows.md)
