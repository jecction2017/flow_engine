# 试运行流程

## 概述

Flow Studio 右侧 **试运行** 面板对当前流程发起单次调试执行（固定 `RunMode.DEBUG`）。

## 操作步骤

1. 选择 **Profile** 与超时时间。
2. 可选：填写初始上下文 JSON、数据字典 YAML 覆盖。
3. 展开 **本次附加策略** 可临时 allow/redirect 副作用 builtin。
4. 运行后查看节点时间线、日志与失败报告。

## 结果说明

- 时间线按节点 `order` 排列，可展开子节点与日志抽屉。
- 副作用调用可能被抑制 — 见 [调用为何被抑制](../capability-policy/why-calls-are-suppressed.md)。

## 相关文档

- [第一次试运行](../getting-started/first-trial-run.md)
- [失败报告](failure-reports.md)
