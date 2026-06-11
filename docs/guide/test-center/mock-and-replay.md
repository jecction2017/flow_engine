# Mock 与录制回放

## 概述

测试方案可配置 **`mock_config`**：按**节点 id** 指定 Mock 模式。Mock 执行时**完全替代**该节点的主脚本，且 **不参与** `pre_exec` / `post_exec` / `on_error` 钩子（见 `orchestrator._execute_mock`）。

配置在测试中心 → 方案编辑 → Mock 配置（JSON）。

---

## 四种 Mock 模式

| mode | 说明 | 必填字段 |
|------|------|----------|
| `fixed` | 直接返回预设 dict | `result` |
| `script` | 用另一段 Starlark 替代节点脚本 | `script` |
| `record_replay` | 查 lookup 录制表；未命中时可录制真实执行结果 | `lookup_ns` |
| `fault` | 注入故障 | `fault_type` |

---

## fixed 模式

```json
{
  "fetch_user_node": {
    "mode": "fixed",
    "result": {"user": {"id": "u001"}, "status": "ok"}
  }
}
```

---

## script 模式

```json
{
  "http_call_node": {
    "mode": "script",
    "script": "{\"success\": true, \"data\": {\"order_id\": \"MOCK-001\"}}"
  }
}
```

Mock 脚本须返回 dict（与任务脚本相同约束）。

---

## record_replay 模式

1. 用 `key_expr`（Starlark 表达式）或**默认键**（boundary inputs 的 SHA256 哈希）在 `lookup_ns` 中查找 `_key` 列
2. **命中** → 返回录制行（去掉 `_key`）
3. **未命中** 且 `record_on_miss=true`（默认）→ **执行真实节点脚本**，将结果追加到 lookup（仍受能力策略约束），并返回该结果
4. **未命中** 且 `record_on_miss=false` → 抛出 `MockCacheMissError`

```json
{
  "external_api_node": {
    "mode": "record_replay",
    "lookup_ns": "mock_recordings",
    "profile_code": "default",
    "key_expr": "resolve(\"$.global.case_id\")",
    "record_on_miss": true
  }
}
```

| 字段 | 说明 |
|------|------|
| `lookup_ns` | 存储录制的命名空间 |
| `profile_code` | 可选，默认当前运行 Profile |
| `key_expr` | 可选；省略时用 boundary inputs 自动哈希 |
| `record_on_miss` | 默认 `true` |

**注意**：首次录制会真实执行节点脚本，集成 builtin 仍受 debug 能力策略影响；若需录制真实 HTTP 响应，须配置 allow 或先在 shadow 环境录制。

---

## fault 模式

| fault_type | 行为 | fault_params |
|------------|------|--------------|
| `timeout` | 睡眠后抛出 `asyncio.TimeoutError` | `timeout_ms`（默认 5000） |
| `exception` | 抛出 `RuntimeError` | `message` |
| `dirty_data` | **节点视为成功**，返回脏数据 dict | `result`（dict） |

```json
{
  "unstable_node": {
    "mode": "fault",
    "fault_type": "timeout",
    "fault_params": {"timeout_ms": 3000}
  }
}
```

```json
{
  "bad_data_node": {
    "mode": "fault",
    "fault_type": "dirty_data",
    "fault_params": {"result": {"status": "OK", "amount": -1}}
  }
}
```

---

## 与能力策略的关系

| 模式 | 是否执行真实节点脚本 |
|------|----------------------|
| `fixed` / `script` / `fault` | 否（完全替代） |
| `record_replay` 命中 | 否 |
| `record_replay` 未命中 + record_on_miss | **是**（脚本内 builtin 仍受策略约束） |

---

## 相关文档

- [方案与批次](plans-and-batches.md)
- [测试断言](assertions.md)
