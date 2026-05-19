# Database seed fixtures

This directory mirrors the layout expected by `flow_engine.db.migrate_data` (profiles, dict, lookup, flows, starlark_user).

Seed a local MySQL database from the repo checkout root:

```bash
flow-db migrate-data --data-dir tests/fixtures/db_seed
```

The repository root `data/` directory is kept empty (placeholder only); default `flow-db migrate-data` without `--data-dir` imports nothing beyond empty trees.

## 金丝雀示例：order_fulfillment_canary

`flows/order_fulfillment_canary/` 为电商订单履约端到端示例，配套：

- `dict/base/business/order.yaml` — 税率与运费规则
- `lookup/profiles/default/customers.json`、`products.json`、`order_fulfillment_cases.json`
- 详细验证步骤见 [examples/order_fulfillment_canary.md](../../examples/order_fulfillment_canary.md)
