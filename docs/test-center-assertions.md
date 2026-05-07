# 测试中心断言（assertions）使用说明

测试中心支持把**断言规则**绑定在测试方案（Plan）上，或在临时批次（`POST /api/test-batches`）里内联传入。每条用例（lookup namespace 的一行）运行结束后，会对运行输出 `global_ns` 做评估，结果写入 `FeFlowRun.evaluation` 并在前端展示为 `verdict=pass/fail`。

本文面向实际使用，给出各种断言写法与可复制示例。

---

## 1. 断言数据从哪里来（global_ns）

断言的对比对象是运行结束时的 `global_ns`（已剔除 `dictionary`），来源于：

- **lookup 行注入**：测试集的每行数据会按「上下文映射（context_mapping）」注入到 `global_ns`。
- **流程节点输出**：各节点（Task/Subflow/Loop）执行过程中对 context 的写入/输出，也会体现在最终 `global_ns`。

因此断言的 `path` 实际上是对 `global_ns` 的点路径读取：

- `a.b.c`：表示 `global_ns["a"]["b"]["c"]`
- 若路径中间不是 dict，则读取失败返回 `None`（该规则通常会 fail，除非你期望的是 `None`）

实现参考：`flow_engine/runner/assertions.py::_get_path`。

---

## 2. 断言规则结构（JSON 数组）

在方案编辑页的 **断言 assertions（JSON 数组）** 中填写，格式如下：

```json
[
  { "id": "rule_1", "op": "eq", "path": "out.ok", "expected": true }
]
```

- **id**：可选；不填会自动生成 `rule_0/rule_1/...`。建议写成稳定可读的标识，便于定位失败原因。
- **op**：必填；比较方式（见下文 3）。
- **path**：除 `op=starlark` 外必填；从 `global_ns` 读取实际值的点路径。
- **expected**：比较目标（不同 op 含义略有差异）。

---

## 3. 支持的 op（比较方式）

当前实现位于 `flow_engine/runner/assertions.py::_compare` 与 `evaluate_assertions`。

### 3.1 `eq`：相等（严格等于）

```json
[
  { "id": "ok_true", "op": "eq", "path": "out.ok", "expected": true },
  { "id": "code_200", "op": "eq", "path": "out.code", "expected": 200 }
]
```

适合：布尔开关、枚举、状态码、精确字符串。

### 3.2 `ne`：不等

```json
[
  { "id": "msg_not_empty", "op": "ne", "path": "out.message", "expected": "" }
]
```

### 3.3 `contains`：包含（字符串包含）

实现：把 `actual/expected` 都转字符串，判断 `str(expected) in str(actual)`。

```json
[
  { "id": "msg_contains_order", "op": "contains", "path": "out.message", "expected": "order_id" }
]
```

注意：这是字符串包含，不是数组 contains；数组场景建议用 `starlark`（见 3.6）。

### 3.4 `regex`：正则匹配（字符串）

实现：`re.search(str(expected), str(actual)) is not None`

```json
[
  { "id": "id_like_UUID", "op": "regex", "path": "out.id", "expected": "^[0-9a-fA-F-]{36}$" }
]
```

### 3.5 `json_match` / `json_subset`：JSON 子集匹配（推荐用于结构化输出）

实现：**expected 是 actual 的子集**（递归）：

- dict：expected 的每个 key 都要在 actual 中出现且递归匹配
- list：expected 是 actual 的前缀（按索引逐个递归匹配）
- 标量：严格相等

示例：只关心核心字段，忽略其它字段：

```json
[
  {
    "id": "payment_shape",
    "op": "json_match",
    "path": "out.payment",
    "expected": {
      "status": "SUCCESS",
      "amount": 100,
      "currency": "CNY"
    }
  }
]
```

示例：数组前 N 项对齐（前缀匹配）：

```json
[
  {
    "id": "first_item_basic",
    "op": "json_match",
    "path": "out.items",
    "expected": [
      { "sku": "A001", "qty": 2 }
    ]
  }
]
```

---

## 3.6 `starlark`：表达式断言（最强，适合复杂逻辑）

当 `op=starlark` 时，不使用 `path/expected`（可留空），而是执行 `expr`（或 `starlark_expr`）这段 Starlark 脚本，并把 `global_ns` 注入为一个变量。

两种返回方式：

1. **返回 bool**：true 通过，false 失败
2. **返回 dict** 且包含 `pass`：形如 `{ "pass": true/false, "message": "..." }`，可自定义失败原因

### 示例 A：数组包含（`contains` 做不了的那种）

```json
[
  {
    "id": "items_contains_sku_A001",
    "op": "starlark",
    "expr": "any([x.get('sku') == 'A001' for x in (global_ns.get('out', {}).get('items') or [])])"
  }
]
```

### 示例 B：数值范围（区间判断）

```json
[
  {
    "id": "latency_lt_200ms",
    "op": "starlark",
    "expr": "{'pass': (global_ns.get('metrics', {}).get('latency_ms') or 999999) < 200, 'message': 'latency too high'}"
  }
]
```

### 示例 C：多条件组合（给出具体失败提示）

```json
[
  {
    "id": "order_paid_and_has_id",
    "op": "starlark",
    "expr": "\n# Starlark: 你可以写多行脚本\nout = global_ns.get('out', {})\norder = out.get('order', {})\nok = (order.get('status') == 'PAID') and bool(order.get('id'))\nreturn {'pass': ok, 'message': 'order.status must be PAID and order.id must exist'}\n"
  }
]
```

提示：

- 表达式执行环境是 Starlark；建议只用 `global_ns` 做读取，避免写入副作用。
- 若脚本抛异常，该规则会被记为 fail，message 是异常信息。

---

## 4. 低门槛写法：在测试集行里写 `_expect`（每行独立）

如果不想在方案里维护 assertions，也可以在 lookup namespace 的行里放期望字段。Runner 会在注入 `global_ns` 前剥离 `_expect`（避免污染），并自动生成断言规则。

支持两种形态（等价）：

### 4.1 `_expect` 对象

```json
{
  "id": "case_001",
  "x": 1,
  "_expect": {
    "id": "expect_ok",
    "op": "eq",
    "path": "out.ok",
    "equals": true
  }
}
```

其中：

- `equals` / `expected` 都可以用（实现里优先取 `equals`）
- `op` 默认 `eq`
- `id` 默认 `_row._expect`

### 4.2 扁平字段 `_expect.path` / `_expect.equals`

```json
{
  "id": "case_002",
  "_expect.path": "out.code",
  "_expect.equals": 200
}
```

这会生成一个规则 id=`_row._expect.path`，op 默认 `eq`。

### 4.3 与方案 assertions 的合并规则

一次用例最终会执行：

> `rules = plan_assertions + row_derived_assertion_rules(row)`

也就是说：

- 方案级规则对所有用例统一生效
- 行内 `_expect` 适合做 “每行不同期望值” 的补充

---

## 5. 常见案例（端到端）

### 案例 1：支付回归（结构性输出 + 单字段）

```json
[
  { "id": "ok", "op": "eq", "path": "out.ok", "expected": true },
  {
    "id": "payment_subset",
    "op": "json_match",
    "path": "out.payment",
    "expected": { "status": "SUCCESS", "currency": "CNY" }
  }
]
```

### 案例 2：订单列表包含某 SKU（Starlark）

```json
[
  {
    "id": "sku_exists",
    "op": "starlark",
    "expr": "{'pass': any([x.get('sku') == 'A001' for x in (global_ns.get('out', {}).get('items') or [])]), 'message': 'missing sku A001'}"
  }
]
```

### 案例 3：每行不同期望（只用 `_expect`）

行 1：

```json
{ "case": "c1", "input": 1, "_expect.path": "out.result", "_expect.equals": 2 }
```

行 2：

```json
{ "case": "c2", "input": 2, "_expect.path": "out.result", "_expect.equals": 4 }
```

---

## 6. 结果怎么判定（verdict）

- 如果流程状态不是 `COMPLETED`：直接 `verdict=fail`（reason=`flow_not_completed`），不会执行规则列表。
- 如果没有任何规则：`verdict=pass`。
- 否则：所有规则 `pass=true` 才算 `verdict=pass`，任何一条失败即 `verdict=fail`。

实现参考：`flow_engine/runner/assertions.py::evaluate_assertions`。