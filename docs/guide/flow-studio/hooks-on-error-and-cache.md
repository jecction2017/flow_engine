# 钩子、容错与缓存

## 概述

除主脚本外，节点和流程可配置**钩子**（特定时机执行的 Starlark）、**on_error**（失败处置）与 **cache**（结果缓存）。均在 Flow Studio 节点/流程元数据编辑器中配置。

---

## 流程级钩子（FlowHooks）

在流程元数据中配置，作用于整个流程生命周期：

| 钩子 | 触发时机 | 返回值要求 |
|------|----------|------------|
| `on_start` | 流程开始执行前 | 无强制 dict |
| `on_complete` | 流程成功结束后 | 无强制 dict |
| `on_failure` | 流程失败后 | 无强制 dict |

典型用途：初始化全局变量、记录审计日志、发送通知。

---

## 节点级钩子

### Task / Subflow 节点（NodeHooks）

| 钩子 | 触发时机 |
|------|----------|
| `pre_exec` | 节点主脚本执行前 |
| `post_exec` | 节点主脚本成功后 |

### Loop 节点（LoopHooks）

除 `pre_exec` / `post_exec` 外，还有：

| 钩子 | 触发时机 |
|------|----------|
| `on_iteration_start` | 每次迭代开始前 |
| `on_iteration_end` | 每次迭代结束后 |

钩子脚本写法与任务脚本相同，但**不强制返回 dict**（返回值通常被忽略）。

### 示例：pre_exec 校验

```python
def check():
    payload = resolve("$.global.payload")
    if payload == None:
        fail("payload is required")
    return None

check()
```

---

## on_error（容错配置）

节点主脚本失败时，按 `on_error.action` 处置：

| action | 行为 | 附加字段 |
|--------|------|----------|
| `retry` | 按策略重试（受 execution strategy 的 `retry_count` 约束） | — |
| `jump` | 跳转到指定节点 id | `target`：目标节点 id |
| `continue` | 标记失败但继续执行后续兄弟节点 | — |
| `break` | 在 loop 内结束循环 | — |
| `ignore` | 忽略错误，视为成功 | — |
| `custom` | 执行自定义 Starlark 脚本决定后续 | `script` |

### 示例：失败后跳转

```yaml
on_error:
  action: jump
  target: error_handler_task
```

### custom 脚本

`custom` 模式下 `script` 可返回控制指令或恢复数据，具体语义见引擎实现；常用于记录错误上下文后决定跳转或继续。

---

## cache（节点结果缓存）

仅 **task** 节点支持。配置后，相同 `cache_key` 在 TTL 内命中则跳过脚本执行，直接返回缓存结果。

| 字段 | 说明 |
|------|------|
| `cache_key` | 缓存键表达式或字面量；为空则不启用 |
| `ttl` | 过期时间（秒），须 > 0 |
| `max_entries` | 最大缓存条目数 |
| `threshold_ms` | 仅当上次执行耗时超过此阈值（毫秒）才写入缓存，默认 0（总是缓存） |

### 使用场景

- 昂贵的外部查询（ES 聚合、复杂计算）在短时间窗口内重复调用
- 同一流程多次试运行时加速调试（注意 Profile 与数据时效）

### 脚本侧缓存 API

除节点级 cache 外，脚本还可直接调用：

| 函数 | 说明 |
|------|------|
| `cache_get(key)` | 读取缓存 |
| `cache_set(key, value, ttl)` | 写入缓存 |
| `cache_remember(key, ttl, fn)` | 不存在时执行 fn 并缓存 |

这些函数的 `side_effects` 为 `none`，不受能力策略抑制。

---

## 配置步骤（界面）

1. 在 Flow Studio 选中目标节点或流程根
2. 在中间编辑器找到 **钩子**、**容错（on_error）**、**缓存** 折叠区
3. 填写 Starlark 脚本或选择 action
4. 保存草稿 → 试运行验证 → 提交版本

---

## 注意事项

- 钩子与主脚本均须遵守 Starlark 方言约束（顶层不能有 `if`/`for`，须包在 `def` 内）
- `on_error` 的 `jump` 目标必须是节点 **id**
- 节点 cache 与脚本 `cache_*` 是不同层级的机制，可组合使用
- 缓存不考虑 Profile 隔离时可能返回过期数据，生产环境谨慎设置 TTL

---

## 相关文档

- [节点类型](node-types.md)
- [执行策略](execution-strategies.md)
- [失败报告](failure-reports.md)
- [上下文与流程控制](../scripting/context-and-flow-control.md)
