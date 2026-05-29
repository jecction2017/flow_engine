# HTTP integration (unified connector)

HTTP integration is now implemented through the same connectors layer as Elasticsearch/Kafka:

- data dictionary configuration (`middleware.http`)
- connector registry bind (`ConnectorRegistry`)
- Starlark builtin entry (`http_call`)
- unified response shape for scripts

## Dictionary layout

Module code: `middleware.http`

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
          retry_backoff_sec: 0.2
          default_headers:
            X-Env: test
        auth_providers:
          iam_default:
            type: iam
            token_url: https://iam.example.com/oauth/token
            client_id: secret://iam_client_id
            client_secret: secret://iam_client_secret
            scope: api.read
            ttl_sec: 3600
          soa_default:
            type: soa
          apig_default:
            type: apig
        services:
          user_service:
            base_url: https://api.example.com
            common_headers:
              X-Service: user
            auth_provider: iam_default
            endpoints:
              get_user:
                path: /v1/users/{user_id}
                method: GET
                extra_headers:
                  X-Endpoint: get_user
```

## Starlark builtin

```python
r = http_call(
    "user_service",
    "get_user",
    path_params={"user_id": "123"},
    header_params={"X-Req-Id": "abc"},
)
if r["success"]:
    user = r["data"]
else:
    log_error("http failed:", r["error_code"], r["error_msg"])
{"result": r}
```

Return shape:

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

## Parameter precedence

Request parameters are resolved in this order:

`instance.base < service < endpoint < runtime args`

This applies to timeout, headers, query/path params, method override, and auth override.

## Auth providers

- `iam`: implemented, token fetch with TTL cache
- `soa`: plugin slot is present, currently returns `AUTH_NOT_IMPLEMENTED`
- `apig`: plugin slot is present, currently returns `AUTH_NOT_IMPLEMENTED`

## Reliability and policy

- protected by `ProtectionPipeline` (rate limit, concurrency, circuit breaker, timeout)
- capability policy still applies (`category="integration"`)
- in DEBUG/SHADOW defaults, side-effect builtins are suppressed unless explicitly allowed

## Migration note

Legacy builtin APIs `http_simple_get` and `http_request` have been removed.
Use `http_call(service_name, endpoint_name, ...)` with dictionary-driven connector config.
