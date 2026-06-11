# 脚本中的 lookup_query

## 示例

```python
rows = lookup_query("my_ns", {"field": "value"})
first = rows[0] if rows else {}
{"row": first}
```

## 相关文档

- [SOC 模板](../scripting/recipes/soc-alert-handling.md)
