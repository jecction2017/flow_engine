# 电商订单履约金丝雀示例（order_fulfillment_canary）

端到端验证编排引擎核心能力的示例流程。主定义文件：[order_fulfillment_canary.yaml](./order_fulfillment_canary.yaml)。

## 业务场景

电商订单履约：读取字典税率/运费规则 → Lookup 客户主数据 → 并行库存/风控/促销 → 行项目循环计价 → 支付子流程 → VIP/标准配送分支 → 闪购折扣（含 on_error 恢复）→ 结案。

## 快速试运行

```bash
pytest tests/test_order_fulfillment_canary.py -q
```

或在 Flow Studio 打开 `order_fulfillment_canary`，使用默认 `initial_context` 点击「流程试运行」（`profile=default`）。

## 导入种子数据（MySQL）

```bash
flow-db migrate-data --data-dir tests/fixtures/db_seed
```

包含：

- 数据字典：`dict/base/business/order.yaml`（`sit` profile 覆盖税率）
- Lookup：`customers`、`products`、`order_fulfillment_cases`
- 流程版本：`flows/order_fulfillment_canary/versions/v1.yaml`

## 节点调试

在 Studio 选中节点（如 `call_fraud_api`），将其 `script` 与片段上下文提交到 `POST /api/debug/node`：

```json
{
  "script": "<节点 script>",
  "initial_context": { "customer": { "risk_score": 10 } },
  "profile": "default"
}
```

## 测试中心（测试集 + 断言 + Mock）

1. 确保已 migrate lookup namespace `order_fulfillment_cases`。
2. 创建测试批次（或测试方案），推荐配置：

```json
{
  "flow_code": "order_fulfillment_canary",
  "test_ns_code": "order_fulfillment_cases",
  "profile_code": "default",
  "concurrency": 2,
  "context_mapping": { "mode": "wrap", "wrap_key": "order" },
  "mock_config": {
    "call_fraud_api": {
      "mode": "fixed",
      "result": { "shard": { "flagged": false, "risk_score": 5, "mocked": true } }
    }
  },
  "assertions": [
    { "id": "status_fulfilled", "op": "eq", "path": "fulfillment.status", "expected": "FULFILLED" },
    { "id": "has_payment_ref", "op": "contains", "path": "fulfillment.payment_ref", "expected": "PAY-" }
  ]
}
```

测试行 `T-001` 期望 `FULFILLED`，`T-002`（高风险客户）期望 `REJECTED`，`T-003`（`apply_risky_discount`）期望 `pricing.recovered=true`。

## 部署运行

1. 发布流程版本（commit `order_fulfillment_canary` v1）。
2. 创建 Deployment，`profile_code=default`。
3. 手动或定时触发；在 Run Detail 查看 `fe_deploy_run` 与 span 森林。

## 能力对照

| 能力 | 流程内节点/配置 |
|------|----------------|
| 并发调度 | `async_checks` + `wait_before` 屏障 |
| Starlark | 全部 task `script` |
| 数据字典 | `bootstrap_config` → `dict_get("business.order.*")` |
| Lookup | `resolve_customer`、`inventory_check` |
| 条件分支 | `vip_shipping` / `standard_shipping` |
| 循环 | `process_line_items`（`copy_item: deep`） |
| Subflow | `payment_subflow` |
| on_error | `apply_flash_discount` → `recover_discount` |
| Hooks | flow + loop + task |
| load 模块 | `apply_pricing_helper` → `helpers.star` |
