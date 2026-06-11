# 上下文映射

## 概述

**context_mapping** 决定如何把 Lookup 用例行（或订阅消息解码后的 payload）转换成写入 `global_ns` 的片段。实现位于 `runner/context_mapping.py`，测试中心与 Kafka 订阅 ingress **共用同一套语义**。

在测试中心 → 方案编辑页配置 JSON 对象；**未配置或为空时，默认 `{"mode": "spread"}`**（整行展开合并进 `global_ns`）。

---

## 四种模式

### spread（默认）

整行字段原样合并进 `global_ns`（浅拷贝）。

```json
{"mode": "spread"}
```

**示例**：Lookup 行 `{"case_id": "c1", "amount": 100}` → `global_ns` 含 `case_id`、`amount` 两个顶层键。

省略 `mode` 时等价于 spread；`mapping` 为 `null` 时也是整行 spread。

---

### wrap

把整行包进一个键下，可选包成列表。

```json
{
  "mode": "wrap",
  "wrap_key": "order",
  "wrap_as_list": false
}
```

**示例**：行 `{"id": "O1", "amount": 99}` → `global_ns.order = {"id": "O1", "amount": 99}`。

`wrap_as_list: true` 时 → `global_ns.order = [{"id": "O1", "amount": 99}]`。

`wrap_key` 默认 `"input"`。

---

### rules

按规则把**行字段**映射为 `global_ns` 内的**点分路径**（自动建嵌套 dict）。

```json
{
  "mode": "rules",
  "rules": [
    {"source": "case_id", "target": "meta.case_id"},
    {"source": "amount", "target": "order.amount"},
    {"source": "currency", "target": "order.currency"}
  ]
}
```

| 字段 | 说明 |
|------|------|
| `source` | Lookup 行上的列名；行中不存在则跳过该条规则 |
| `target` | 写入 `global_ns` 的点分路径，如 `alert.id` → `global_ns["alert"]["id"]` |

**注意**：`target` 是点分键名，**不是** `$.global.xxx` 路径字符串。

---

### script

执行 Starlark 转换脚本，入参为 `payload`（整行 dict），须返回 dict。

```json
{
  "mode": "script",
  "script": "..."
}
```

脚本在 `eval_transform_script` 中执行，可读 `payload` 全局变量。须返回 `dict`，否则报错。

---

## 与流程脚本的配合

映射结果合并进 `global_ns` 后，流程脚本用 `resolve("$.global.xxx")` 读取：

| mapping 结果 | resolve 示例 |
|--------------|--------------|
| spread：`{"amount": 100}` | `resolve("$.global.amount")` |
| rules → `order.amount` | `resolve("$.global.order.amount")` |
| wrap → `order` | `resolve("$.global.order.amount")` |

---

## 完整示例（rules 模式）

### Lookup 行

| case_id | amount | currency |
|---------|--------|----------|
| pay_01 | 100 | CNY |

### context_mapping

```json
{
  "mode": "rules",
  "rules": [
    {"source": "case_id", "target": "case_id"},
    {"source": "amount", "target": "order.amount"},
    {"source": "currency", "target": "order.currency"}
  ]
}
```

### 流程脚本

```python
amt = resolve("$.global.order.amount")
{"charged": amt > 0}
```

---

## 常见错误

| 错误写法 | 正确做法 |
|----------|----------|
| `{"case_id": "$.global.case_id"}` 扁平映射 | 使用 `rules` 模式 |
| target 写 `$.global.order` | target 写 `order` 或 `order.amount` |
| 期望不存在的 source 字段出现 | source 不在行中则该规则被跳过 |

---

## 订阅部署中的复用

Kafka 订阅部署的 `schedule_config.parse.mapping` 使用相同模式（`spread` / `wrap` / `rules`）；`parse.transform=script` 时用 Starlark 解析消息体。见 [Kafka 订阅部署](../operations-center/subscription-kafka.md)。

---

## 相关文档

- [测试断言](assertions.md)
- [方案与批次](plans-and-batches.md)
- [边界与上下文](../flow-studio/boundaries-and-context.md)
- [Lookup 测试数据](../lookup/test-data-with-test-center.md)
