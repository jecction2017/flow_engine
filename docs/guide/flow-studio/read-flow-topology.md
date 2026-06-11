# 读懂流程拓扑

## 概述

Flow Studio 左侧 **节点树** 展示流程拓扑：顺序、嵌套与子流程结构。

## 操作步骤

点击节点可在右侧编辑；树中显示：

- **类型徽章**：task / loop / subflow
- **策略模式**：sync / async 等（由 `strategy_ref` 决定）
- **wait** 标记：该节点前有同步屏障

## 进阶

相邻节点均为非 sync 策略且下一节点未设 `wait_before` 时，可能形成 **隐式并行组**（树上有提示）。

## 相关文档

- [节点类型](node-types.md)
- [执行策略](execution-strategies.md)
