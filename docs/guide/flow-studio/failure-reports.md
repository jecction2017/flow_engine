# 失败报告

## 概述

节点或流程失败时，试运行面板与运行中心详情会展示**结构化失败报告**，帮助快速定位：哪个节点、什么错误、是否可重试、是否与能力策略抑制相关。

---

## 在哪里查看

| 场景 | 位置 |
|------|------|
| 试运行 | Flow Studio 右侧试运行面板 → 失败节点展开 |
| 部署/测试运行 | 运行中心 → 运行记录 → 详情 → Spans / 日志 |

---

## 报告常见字段

| 字段 | 说明 |
|------|------|
| 失败节点 id / name | 出错的节点 |
| 错误类别 | 脚本错误、超时、引擎错误、Mock 故障等 |
| 错误消息 | `fail()` 文本或异常摘要 |
| 脚本位置 | 语法错误时可能有行号提示 |
| 重试信息 | on_error.retry 或策略重试次数 |
| 关联 Span | 链路中的失败片段 |

---

## 错误类型与处理

### 脚本语法错误

```
error: `if` cannot be used outside `def` in this dialect
```

**处理**：把控制流包进 `def`，末尾调用函数。见 [基础语法](../scripting/syntax-essentials.md)。

### 返回值类型错误

```
Task script must evaluate to a dict
```

**处理**：确保末行是 `{...}` 或返回 dict 的函数调用。

### fail() 业务中断

脚本主动 `fail("reason")`，报告含自定义消息。检查业务校验逻辑与输入数据。

### 集成调用失败

HTTP/ES 返回 `success=false` 或 Kafka `ok=false`。检查数据字典配置、网络、鉴权。

### SUPPRESSED（非真失败）

debug 模式下能力策略抑制副作用，返回占位结果。若脚本未处理 `_suppressed`，可能误判为业务失败。

**处理**：确认是否预期抑制；若需真实调用，配置 allow 策略或使用部署/测试 Mock。

### 超时

节点或整体 run 超时。增大 timeout 或优化慢调用。

---

## 排查步骤

```
1. 读失败报告中的节点 id 与错误消息
2. 展开该节点日志（脚本 log_* 输出）
3. 试运行复现 → 必要时添加本次附加策略 allow
4. 检查 Profile 下数据字典与 lookup 数据
5. 对比测试中心 Mock 是否掩盖了真实错误
```

---

## 相关文档

- [试运行流程](trial-run.md)
- [钩子、容错与缓存](hooks-on-error-and-cache.md)
- [运行中心排障](../operations-center/troubleshooting.md)
- [调用为何被抑制](../capability-policy/why-calls-are-suppressed.md)
