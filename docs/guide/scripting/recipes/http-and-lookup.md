# HTTP 与 Lookup 组合示例

## 概述

常见模式：用 `lookup_query` 读取配置或情报，再 `http_call` 调用外部 API（注意调试模式下 HTTP 可能被抑制）。

```python
rows = lookup_query("config_ns", {"key": "endpoint"})
cfg = rows[0] if rows else {}
# r = http_call("my_api", "action", {"id": cfg.get("id")})
{"cfg": cfg}
```

## 相关文档

- [HTTP 集成](../../integrations/http.md)
- [Lookup 脚本访问](../../lookup/lookup-in-scripts.md)
