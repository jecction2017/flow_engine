# 副作用 builtin

## 概述

引擎用两个维度描述 builtin：

1. **`side_effects`**（规格字段）— 描述 I/O 性质：`none`、`disk`、`network` 等
2. **`category`**（规格字段）— **能力策略实际按此类别匹配**

debug/shadow 下系统默认抑制的是这些 **category**：`integration`、`db_read`、`db_write`、`mq_publish`（见 `mode_context.py`）。**不是**凡 `side_effects != none` 就抑制。

---

## category 与 debug 下的行为

| category | debug 系统默认 | 典型 builtin |
|----------|------------------|--------------|
| `integration` | **SUPPRESS** | `http_call`、`kafka_send`、`kafka_receive` |
| `db_read` | **SUPPRESS** | `es_search`、`es_mget` 等 |
| `db_write` | **SUPPRESS** | `user_create`、`user_delete` |
| `mq_publish` | **SUPPRESS** | （占位类目） |
| `dictionary` | ALLOW | `dict_get` |
| `lookup` | ALLOW | `lookup_query` |
| `runtime` / `demo` / `user` / `system` | ALLOW | `resolve`、`log_*`、`cache_*`、`time_*` |

因此：**`dict_get` 与 `lookup_query` 在试运行/测试中可正常调用**，尽管其 `side_effects` 标记为 `disk`。

---

## side_effects 字段含义

| side_effects | 含义 |
|--------------|------|
| `none` | 无外部 I/O |
| `disk` | 读本地配置/表（字典、lookup） |
| `network` | 网络 I/O |

`side_effects` 用于文档与观测；**是否抑制以 `category` + 能力规则为准**。

---

## 抑制时的行为

命中 **suppress** 时函数体不执行，返回注册表中的 `suppress_result` 占位值，通常含 `_suppressed` 或 `SUPPRESSED` 错误码。不同集成返回形状不同：

- HTTP：`success: false`, `error_code: "SUPPRESSED"`
- Kafka：`ok: false`, `error: {code: "SUPPRESSED", ...}`

---

## 如何查阅

**能力与脚本 → Python 内置** 查看每个函数的 `category` 与 `side_effects`。

---

## 相关文档

- [默认抑制行为](default-behavior.md)
- [各层优先级](layer-priority.md)
- [调用为何被抑制](why-calls-are-suppressed.md)
