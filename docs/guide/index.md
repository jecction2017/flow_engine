# 帮助文档

flow_engine 是一套流程编排与运行平台：在 **Flow Studio** 里设计流程，用 **试运行** 或 **测试中心** 验证，通过 **运行中心** 部署到目标环境。

使用顶部 **搜索框** 可跨章节查找关键词（至少 2 个字符）；左侧目录与 `docs/guide` 文件夹结构一致。

---

## 我想…

| 我想… | 去看 |
|--------|------|
| 了解这个平台能做什么 | [平台简介](overview/what-is-flow-engine.md) |
| 搞懂常用术语 | [术语表](overview/glossary.md) |
| 知道每个主界面在哪 | [界面与文档对照](overview/ui-navigation.md) |
| 从零跑通第一条链路 | [快速开始](getting-started/index.md) |
| 试运行一个流程并看懂结果 | [第一次试运行](getting-started/first-trial-run.md) → [试运行详解](flow-studio/trial-run.md) |
| 写第一个节点脚本 | [第一次写脚本](getting-started/first-script-and-debug.md) → [脚本快速开始](scripting/quick-start.md) |
| 搞懂 Starlark 语法限制 | [基础语法](scripting/syntax-essentials.md) |
| 配置 HTTP / Kafka 调用 | [HTTP 集成](integrations/http.md) · [Kafka 集成](integrations/kafka.md) |
| 搞懂为什么调试时 HTTP 没发出去 | [调用为何被抑制](capability-policy/why-calls-are-suppressed.md) |
| 配置测试方案与断言 | [第一次测试](getting-started/first-test-plan.md) → [断言规则](test-center/assertions.md) |
| Mock 外部依赖做测试 | [Mock 与录制回放](test-center/mock-and-replay.md) |
| 把流程部署到生产 | [第一次部署](getting-started/first-deployment.md) → [部署管理](operations-center/deployments.md) |
| 查运行链路与日志 | [链路、指标与日志](operations-center/spans-metrics-logs.md) |
| 管理环境与密钥 | [Profile 管理](profiles/profile-management.md) · [密钥管理](data-dictionary/secrets.md) |

---

## 文档章节

| 章节 | 内容 |
|------|------|
| [overview](overview/index.md) | 概念、术语、界面对照 |
| [getting-started](getting-started/index.md) | 安装与第一条任务链 |
| [flow-studio](flow-studio/index.md) | 流程编排、节点、试运行 |
| [capability-center](capability-center/index.md) | 能力与用户脚本 |
| [scripting](scripting/index.md) | Starlark 脚本专题 |
| [capability-policy](capability-policy/index.md) | 能力策略与副作用 |
| [test-center](test-center/index.md) | 测试方案、断言、Mock |
| [operations-center](operations-center/index.md) | 部署、调度、监控、Worker |
| [profiles](profiles/index.md) | 环境配置 |
| [data-dictionary](data-dictionary/index.md) | YAML 模块树与密钥 |
| [lookup](lookup/index.md) | 表格式数据 |
| [integrations](integrations/index.md) | HTTP、Kafka、ES、指标特征 |
| [faq](faq/index.md) | 按主题的常见问题 |

---

## 推荐阅读路径

**新人（第 1 天）**  
平台简介 → 核心概念 → 安装与访问 → 第一次试运行 → 第一次写脚本

**开发集成（第 2–3 天）**  
基础语法 → 内置能力概览 → HTTP/Kafka 集成 → 数据字典模块树 → 能力策略

**测试与上线**  
第一次测试 → 断言 → Mock → 第一次部署 → 链路日志 → 故障排查

---

## 说明

- 界面以中文为主；技术字段名（如 `capability_policy`、`global_ns`）与 API/存储一致，便于对照日志与 JSON 配置。
- 内置函数完整列表以 **能力与脚本 → Python 内置** 为准，文档提供用法与场景说明。
- 更深的设计细节见仓库 `docs/*-design.md`，帮助文档侧重**可操作的日常使用**。
