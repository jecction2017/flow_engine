# 执行策略

## 概述

每个节点引用 `strategy_ref`，对应流程元数据中的执行策略：`sync`、`async`、`thread`、`process` 等，控制并发与超时。

## 进阶

- **wait_before**：为 true 时在该节点前形成同步屏障
- 相邻节点均为非 sync 且下一节点无 `wait_before` 时，可能形成隐式并行组（节点树有提示）

## 相关文档

- [节点类型](node-types.md)
