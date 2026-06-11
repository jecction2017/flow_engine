# 能力策略常见问题

## Q: 抑制是按 side_effects 还是 category？

按 **category**。debug 默认抑制 `integration`、`db_read`、`db_write`、`mq_publish` 类别，见 `mode_context._SYSTEM_DEFAULT_POLICY`。

---

## Q: dict_get / lookup_query 会被抑制吗？

**不会**（默认）。二者 category 分别为 `dictionary`、`lookup`，不在抑制列表中。尽管 `side_effects` 标记为 `disk`。

---

## Q: 规则有几层？

4 层（高→低）：节点 `capability_overrides` → 运行附加 `deployment_capability_policy`（试运行/部署/测试同一槽位）→ Profile `system_capability_policy` → 模式内置默认。

---

## Q: allow / suppress / redirect？

| action | 行为 |
|--------|------|
| suppress | 不执行，返回 suppress_result |
| allow | 正常执行 |
| redirect | 带 redirect_params 执行 |

---

## Q: 试运行能改 production 吗？

不能，服务端锁死 `RunMode.DEBUG`。

---

## 相关文档

- [各层优先级](../capability-policy/layer-priority.md)
- [默认抑制行为](../capability-policy/default-behavior.md)
