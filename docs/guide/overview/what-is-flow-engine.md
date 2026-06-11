# 平台简介

## 概述

flow_engine 用于把业务步骤编排成**可版本化的流程（Flow）**，在指定**环境（Profile）**下**试运行、测试或部署运行**。流程节点可执行 Starlark 脚本，并调用 HTTP、Kafka、Lookup 等集成能力。

## 典型使用方式

1. 在 **Flow Studio** 编辑流程拓扑与节点脚本，保存草稿并提交版本。
2. 用 **试运行** 或 **测试中心** 在受控模式下验证行为。
3. 在 **运行中心** 创建**部署**，按调度或订阅触发，由 **Worker** 执行。
4. 在 **运行中心** 查看运行记录、链路（Spans）与日志，排查问题。

## 相关文档

- [核心概念](core-concepts.md)
- [界面与文档对照](ui-navigation.md)
- [第一次试运行](../getting-started/first-trial-run.md)
