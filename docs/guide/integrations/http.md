# HTTP 集成

## 概述

脚本通过 **`http_call`** 调用数据字典中配置的 HTTP 连接器。连接信息、鉴权、限流均在**数据字典** `middleware.http` 模块维护，脚本侧只需指定 service 与 endpoint 名称。

`http_call` 的 `side_effects` 为 `network`，在 debug 模式下默认被抑制，除非能力策略 allow。

---

## 配置步骤

### 1. 数据字典中定义连接器

**数据字典** Tab → 选择 Profile → 编辑 `middleware.http` 模块：

```yaml
middleware:
  http:
    defaults:
      protection:
        max_in_flight: 16
        max_rps: 100
        circuit_failure_threshold: 5
        circuit_open_sec: 30
    instances:
      main:
        base:
          request_timeout_sec: 10
          verify_ssl: true
          retries: 1
          default_headers:
            X-Env: test
        auth_providers:
          iam_default:
            type: iam
            token_url: https://iam.example.com/oauth/token
            client_id: secret://iam_client_id
            client_secret: secret://iam_client_secret
            scope: api.read
        services:
          user_service:
            base_url: https://api.example.com
            auth_provider: iam_default
            endpoints:
              get_user:
                path: /v1/users/{user_id}
                method: GET
              create_order:
                path: /v1/orders
                method: POST
```

### 2. 脚本中调用

```python
def fetch_user():
    user_id = resolve("$.global.user_id")
    r = http_call(
        "user_service",
        "get_user",
        path_params={"user_id": user_id},
        header_params={"X-Req-Id": "trial-001"},
    )
    if not r["success"]:
        fail("http failed: " + str(r.get("error_msg")))
    return {"user": r["data"], "cost_ms": r["cost_ms"]}

fetch_user()
```

---

## 返回值结构

```json
{
  "success": true,
  "data": {},
  "error_msg": null,
  "error_code": null,
  "status_code": 200,
  "cost_ms": 12.3,
  "meta": {
    "instance": "main",
    "correlation_id": "..."
  }
}
```

失败时 `success=false`，检查 `error_code`、`error_msg`、`status_code`。

被能力策略抑制时：`error_code` 为 `SUPPRESSED`，`meta._suppressed` 为 true。

---

## 参数说明

| 参数 | 说明 |
|------|------|
| `service_name` | 数据字典中 `services` 下的服务名 |
| `endpoint_name` | 该服务下 `endpoints` 的端点名 |
| `instance` | 实例名，默认 `main` |
| `path_params` | 路径参数（替换 `{user_id}` 等占位符） |
| `query_params` | 查询字符串参数 |
| `header_params` | 额外请求头 |
| `method` | 覆盖端点默认 method |
| `body` / `json` | 请求体 |
| `timeout_ms` | 覆盖超时（毫秒） |
| `auth_override` | 覆盖鉴权 provider 名 |

参数优先级：`instance.base` < `service` < `endpoint` < 运行时参数。

---

## 鉴权

当前支持的 `auth_providers.type`：

| type | 状态 |
|------|------|
| `iam` | 已实现，OAuth token 获取与 TTL 缓存 |
| `soa` / `apig` | 插件槽位，当前返回 `AUTH_NOT_IMPLEMENTED` |

密钥通过 `secret://` 引用，在数据字典密钥管理中配置。

---

## 可靠性与保护

每个实例受 **ProtectionPipeline** 保护：

- 并发上限（`max_in_flight`）
- 速率限制（`max_rps`）
- 熔断（`circuit_failure_threshold`、`circuit_open_sec`）
- 超时

---

## 调试时放行 HTTP

试运行或测试时，在 **本次附加策略** 中添加：

```json
[{"builtin_name": "http_call", "action": "allow"}]
```

---

## 常见问题

**Q: 试运行返回 SUPPRESSED**  
A: debug 模式默认抑制。添加 allow 规则或使用部署/测试方案级策略放行。

**Q: 401 / 鉴权失败**  
A: 检查 `auth_provider` 配置与 `secret://` 密钥是否正确。

**Q: 连接超时**  
A: 调大 `request_timeout_sec` 或运行时 `timeout_ms`；检查网络与 `base_url`。

---

## 相关文档

- [调用为何被抑制](../capability-policy/why-calls-are-suppressed.md)
- [模块树与 YAML](../data-dictionary/module-tree-and-yaml.md)
- [HTTP 与 Lookup 示例](../scripting/recipes/http-and-lookup.md)
- 设计文档：[http-integration-design.md](../../http-integration-design.md)
