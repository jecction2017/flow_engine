# 内置能力概览

## 概述

引擎向 Starlark 脚本注入大量 **builtin 函数**。在 **能力与脚本 → Python 内置** 查看完整注册表（参数签名、`side_effects`、分类）。编辑器输入函数名时会自动补全。

无需 `load` 即可直接调用的函数占大多数；`internal://` 库需 `load()` 引用。

---

## 按类别速查

### 上下文与运行时（side_effects: none）

| 函数 | 说明 |
|------|------|
| `resolve(path)` | 读取上下文路径，如 `$.global.order.id` |
| `regex_match(pattern, text)` | 正则匹配 |
| `log` / `log_info` / `log_warn` / `log_error` / `log_debug` | 写运行日志 |

### 流程控制（不受 capability 抑制）

| 函数 | 说明 |
|------|------|
| `flow_jump(node_id)` | 跳转到节点逻辑 id |
| `flow_continue()` | loop 内跳过当前迭代 |
| `flow_break()` | 结束 loop |
| `flow_terminate()` | 终止当前任务（跳过重试） |

### 配置与数据（mostly disk / none）

| 函数 | 说明 |
|------|------|
| `dict_get(path, default)` | 读数据字典 |
| `lookup_query(ns, filter)` | 查 Lookup 表（等值 AND；空 filter 最多 1 万行） |
| `user_script_list()` | 列出用户脚本 |

### 缓存（side_effects: none）

| 函数 | 说明 |
|------|------|
| `cache_get(key)` | 读缓存 |
| `cache_set(key, value, ttl)` | 写缓存 |
| `cache_remember(key, ttl, fn)` | 不存在时计算并缓存 |

### 时间（side_effects: none）

| 函数 | 说明 |
|------|------|
| `time_now()` | 当前时间 |
| `time_now_ts()` | 时间戳 |
| `time_format` / `time_parse` | 格式化与解析 |
| `time_convert_tz` / `time_add` / `time_diff` | 时区与运算 |

### 集成（side_effects: network，debug 默认抑制）

| 函数 | 说明 |
|------|------|
| `http_call(service, endpoint, ...)` | HTTP 调用 |
| `kafka_send` / `kafka_receive` | Kafka 生产/消费 |
| `es_search` / `es_mget` / `es_count` / `es_scroll` | Elasticsearch |
| `user_create` / `user_delete` / `user_bulk_update` | 业务写操作 |

### 指标特征（metric_feature_*）

管道计算相关，见 [指标特征流水线](../integrations/metric-feature.md)。

### 演示

| 函数 | 说明 |
|------|------|
| `demo_echo` / `demo_add` | 学习用示例 |

---

## 示例脚本

```python
def main():
    n = demo_add(3, 4)
    timeout = dict_get("app.http.timeout_sec", 10)
    order_id = resolve("$.global.order.id")
    rows = lookup_query("routing", {"enabled": True})
    now = time_now()
    log_info("processing", order_id, "rules=", len(rows))
    return {"sum": n, "timeout": timeout, "order_id": order_id, "ts": str(now)}

main()
```

---

## side_effects 与调试

- `side_effects == "none"`：任何 RunMode 均执行
- `side_effects != "none"`：经能力策略检查；debug 默认 suppress

试运行时若 HTTP 返回 `SUPPRESSED`，在 **本次附加策略** 添加 allow 规则，或改用测试 Mock。

---

## 权威来源

界面注册表 > 本文档。后端新增 builtin 后注册表自动更新；撰写脚本时以补全提示为准。

---

## 相关文档

- [load 与模块](load-and-modules.md)
- [Python 内置](../capability-center/python-builtins.md)
- [副作用 builtin](../capability-policy/side-effects.md)
- [基础语法](syntax-essentials.md)
