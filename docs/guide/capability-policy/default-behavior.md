# 默认抑制行为

## 概述

在临时调试/试运行/测试中心，系统默认会对副作用 builtin 做 `SUPPRESS`：调用被短路，函数体不会执行，直接返回「被抑制时的返回值」（由后端 builtin spec 定义）。

## 被抑制时的输出示例

```python
# 示例：当副作用 builtin 被 SUPPRESS
{
  "success": false,
  "error_code": "SUPPRESSED",
  "meta": {"_suppressed": true}
}
```

## 结果说明

输出里常见 `_suppressed: true` 标记（不同 builtin 字段可能略有差异），便于脚本可测试地处理被抑制情况，而不是静默失败。

## 相关文档

- [调用为何被抑制](why-calls-are-suppressed.md)
- [规则 JSON](policy-rules-json.md)
