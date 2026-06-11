# 第一次试运行

## 概述

在 Flow Studio 中对已保存的流程发起一次受控执行，查看节点时间线与日志，验证流程是否按预期运行。

## 前置条件

- 已在 Flow Studio 打开目标流程（草稿或已提交版本均可试运行）

## 操作步骤

1. 点击 **试运行** 打开侧栏面板。
2. 选择 **Profile**（环境），必要时填写初始上下文 JSON。
3. 设置超时时间，点击运行。
4. 在 **节点执行时间线** 查看各节点状态；可展开节点日志并按级别筛选。

## 结果说明

- 节点状态：COMPLETED / FAILED / SKIPPED 等
- 试运行固定为调试模式，副作用类调用可能被抑制 — 见 [调用为何被抑制](../capability-policy/why-calls-are-suppressed.md)

## 相关文档

- [试运行详解](../flow-studio/trial-run.md)
- [读懂流程拓扑](../flow-studio/read-flow-topology.md)
