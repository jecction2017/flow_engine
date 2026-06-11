# 第一次配置测试

## 概述

测试中心用 Lookup 表驱动用例，运行流程并评估断言。服务端固定 **RunMode.DEBUG**。

---

## 前置条件

- 流程已提交版本
- Lookup 命名空间已有用例行
- 了解 context_mapping 模式（非扁平 `$.global` 映射）

---

## 操作步骤

### 1. 准备 Lookup 表

命名空间 `test_double_cases`：

| case_id | input_value | expected_result |
|---------|-------------|-----------------|
| case_1 | 10 | 20 |
| case_2 | 5 | 10 |

### 2. 新建测试方案

- 流程 + 版本通道
- 测试 lookup 命名空间
- Profile

### 3. context_mapping（spread 示例）

整行并入 global_ns：

```json
{"mode": "spread"}
```

脚本读 `resolve("$.global.input_value")`，断言读 `out.result`。

### 4. context_mapping（rules 示例）

```json
{
  "mode": "rules",
  "rules": [
    {"source": "case_id", "target": "case_id"},
    {"source": "input_value", "target": "input.value"},
    {"source": "expected_result", "target": "expected.result"}
  ]
}
```

### 5. 断言

```json
[
  {
    "id": "match_expected",
    "op": "starlark",
    "expr": "global_ns.get('out', {}).get('result') == global_ns.get('expected', {}).get('result')"
  }
]
```

或行内 `_expect`：

```json
{"case_id": "case_1", "input_value": 10, "expected_result": 20, "_expect.path": "out.result", "_expect.equals": 20}
```

### 6. 运行批次

查看每条用例 verdict。

---

## 相关文档

- [上下文映射](../test-center/context-mapping.md)
- [测试断言](../test-center/assertions.md)
- [方案与批次](../test-center/plans-and-batches.md)
