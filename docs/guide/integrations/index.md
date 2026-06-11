# 集成能力

流程脚本可通过内置函数调用外部系统。配置项通常在 **数据字典** 的 `middleware.*` 模块中维护。

| 集成 | 文档 | 设计说明 |
|------|------|----------|
| HTTP | [http](http.md) | [http-integration-design.md](../../http-integration-design.md) |
| Kafka | [kafka](kafka.md) | [kafka-integration-design.md](../../kafka-integration-design.md) |
| Elasticsearch | [elasticsearch](elasticsearch.md) | — |
| 指标特征 | [metric-feature](metric-feature.md) | [metric-feature-universal-contract.md](../../metric-feature-universal-contract.md) |

副作用类集成在调试模式下可能被抑制 — 见 [调用为何被抑制](../capability-policy/why-calls-are-suppressed.md)。
