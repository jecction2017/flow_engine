# 排障清单

## 概述

按现象快速定位问题。更细的说明见各专题文档；也可用帮助文档顶部 **搜索** 查关键词。

---

## 试运行与调试

| 现象 | 可能原因 | 建议 |
|------|----------|------|
| HTTP/Kafka 无真实请求 | debug 模式抑制副作用 | [本次附加策略](../capability-policy/trial-debug-and-test.md) allow，或改用 Mock |
| 返回 SUPPRESSED | 能力策略 suppress | 预期行为；检查脚本是否误判为业务失败 |
| 修改脚本无效 | 未保存草稿 | Flow Studio 保存后再试运行 |
| 语法错误 | 顶层 if/for | [基础语法](../scripting/syntax-essentials.md) |
| 超时 | 节点或整体 timeout 过小 | 增大超时；检查慢集成 |

---

## 部署与 Worker

| 现象 | 可能原因 | 建议 |
|------|----------|------|
| 部署无运行记录 | 未启动部署 / Worker 离线 | [工作节点](workers.md)、[部署管理](deployments.md) |
| 选不到版本 | 未提交版本 | Flow Studio 提交 Vn |
| cron 不触发 | 表达式错误 / 部署停止 | 检查调度配置与部署状态 |
| Kafka 订阅无消费 | consumer_id 错误 / 无消息 | [Kafka 订阅](subscription-kafka.md)、字典配置 |
| 重复执行 | multi_active + 非幂等 | 改 single_active 或流程幂等设计 |

---

## 节点与流程

| 现象 | 可能原因 | 建议 |
|------|----------|------|
| 节点 FAILED | 脚本 fail()、集成错误、类型错误 | [失败报告](../flow-studio/failure-reports.md)、节点日志 |
| 节点 SKIPPED | condition 为 false | 检查 condition 表达式与上下文 |
| flow_jump 无效 | 目标写成了 name 而非 id | 使用节点 **id** |
| 并行结果错乱 | async 节点写同一 global 路径 | wait_before 或 isolation |

---

## 测试中心

| 现象 | 可能原因 | 建议 |
|------|----------|------|
| verdict fail | 断言不通过 | [断言](assertions.md)、检查 global_ns 路径 |
| 全部 fail 无规则 | 流程未完成 | 先看 Spans 失败节点 |
| Mock 不生效 | mock_config 键不是节点 id | 用 id 作键 |
| record_replay 未命中 | key_expr 变化 / 无录制 | 检查 lookup 录制表 |

---

## 配置与环境

| 现象 | 可能原因 | 建议 |
|------|----------|------|
| dict_get 返回 default | 路径错误或 Profile 无覆盖 | [模块树与 YAML](../data-dictionary/module-tree-and-yaml.md) |
| lookup 空结果 | 命名空间/Profile/过滤条件错误 | [lookup_query](../lookup/lookup-in-scripts.md) |
| 鉴权失败 | secret:// 未配置 | [密钥管理](../data-dictionary/secrets.md) |

---

## 推荐排查流程

```
1. 确认场景：试运行 / 测试 / 部署？
2. 打开失败 run 的 Spans → 定位 FAILED 节点
3. 读失败报告 + 节点日志
4. 检查 Profile、能力策略、字典与 lookup
5. 本地试运行复现 → 逐步放开策略或 Mock
```

---

## 相关文档

- [失败报告](../flow-studio/failure-reports.md)
- [链路、指标与日志](spans-metrics-logs.md)
- [FAQ](../faq/index.md)
