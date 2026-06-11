# 试运行常见问题

## Q: 试运行时 HTTP 没有真正发出去？

预期行为。试运行固定 `RunMode.DEBUG`，系统默认抑制 **category=integration** 的 builtin（如 `http_call`、`kafka_send`）。返回 `SUPPRESSED` 或 `integration suppressed`。

`dict_get`、`lookup_query`（dictionary/lookup 类别）**不会被默认抑制**。

**解决**：
- 在试运行 **本次附加策略** 添加 `{"builtin_name": "http_call", "action": "allow"}`
- 或用测试中心 Mock 节点，无需真实 HTTP
- 真实联调须通过 **部署**（production/shadow）

见 [调用为何被抑制](../capability-policy/why-calls-are-suppressed.md)。

---

## Q: 修改了脚本但试运行结果没变？

确认已 **保存草稿**。试运行读取当前编辑器中的草稿，不是旧版本文件。

---

## Q: 草稿和版本哪个能试运行？

**都可以**。但部署只能用已提交版本。

---

## Q: 试运行超时怎么办？

增大试运行面板的超时秒数；检查慢节点 execution strategy 的 `timeout` 与外部调用耗时。

---

## Q: 如何注入测试数据？

在试运行面板填写 **初始上下文 JSON**，或配置 **数据字典 YAML 覆盖**（仅当次有效）。

---

## Q: 试运行成功但部署失败？

常见差异：Profile 不同、能力策略不同、debug 下被抑制的调用在 production 下真实执行并失败。对比两环境的字典与策略配置。

---

## 相关文档

- [试运行详解](../flow-studio/trial-run.md)
- [失败报告](../flow-studio/failure-reports.md)
