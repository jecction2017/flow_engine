# 执行策略

## 概述

每个节点通过 `strategy_ref` 引用流程元数据中定义的执行策略，控制**同步/异步**、**并发度**、**超时**与**重试**。在 Flow Studio → 流程元数据 → 执行策略 中维护策略列表。

---

## 策略模式（mode）

| mode | 说明 | 典型场景 |
|------|------|----------|
| `sync` | 同步执行，阻塞等待完成 | 顺序依赖的步骤 |
| `async` | 异步调度，与其它 async 节点可并行 | I/O 密集型、可并行任务 |
| `thread` | 线程池执行 | CPU 轻量、需隔离阻塞 |
| `process` | 进程池执行 Starlark | CPU 密集、需强隔离 |

### 策略字段

```yaml
strategies:
  - name: default_sync
    mode: sync
    concurrency: 4
    timeout: 30
    retry_count: 0
  - name: parallel_io
    mode: async
    concurrency: 8
    timeout: 60
    retry_count: 1
```

| 字段 | 说明 |
|------|------|
| `name` | 策略名，节点 `strategy_ref` 引用此值 |
| `mode` | sync / async / thread / process |
| `concurrency` | 并发上限（≥ 1） |
| `timeout` | 超时秒数，null 表示不限制 |
| `retry_count` | 失败重试次数（配合 on_error.retry） |

---

## wait_before（同步屏障）

节点字段 `wait_before: true` 时，在该节点**开始前**等待此前所有已调度节点完成，形成同步屏障。

### 使用场景

```
[A: async] ─┐
[B: async] ─┼─→ [C: sync, wait_before=true] ─→ [D]
```

A、B 并行执行；C 等待 A、B 都完成后才开始；D 在 C 之后。

---

## 隐式并行组

当**相邻**多个节点均满足：

- `strategy_ref` 指向的策略 mode 不是 `sync`
- 后一节点**没有** `wait_before: true`

引擎可能将它们作为**隐式并行组**同时调度。节点树界面会对这类分组给出提示。

### 注意

- 并行节点写入同一 `$.global` 路径可能产生竞态；必要时用 `iteration_isolation=fork` 或避免共享写
- 需要严格顺序时，使用 `sync` 策略或 `wait_before`

---

## 节点选择策略

1. 默认顺序步骤 → `default_sync`（sync）
2. 无依赖的 I/O 调用 → `async`，适当提高 `concurrency`
3. 可能阻塞的 CPU 脚本 → `thread` 或 `process`
4. 合并分支前 → 在汇合节点设 `wait_before: true`

---

## 超时与重试

- **策略 timeout**：引擎层强制终止长时间运行的节点
- **retry_count**：策略级重试次数
- **on_error.action=retry**：节点失败时的容错重试，与策略重试配合使用

试运行面板也有**整体超时**，与单节点 timeout 是不同层级。

---

## 相关文档

- [节点类型](node-types.md)
- [钩子、容错与缓存](hooks-on-error-and-cache.md)
- [读懂流程拓扑](read-flow-topology.md)
