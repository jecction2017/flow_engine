# 上下文与流程控制

## 概述

- `resolve("$.global.path")` — 读取全局上下文路径
- `flow_jump("node_id")` — 跳转到同层节点
- `flow_continue()` / `flow_break()` — 循环内跳过迭代或结束循环
- `flow_terminate()` — 终止当前任务

## 进阶

上下文路径与节点 boundary 映射见 [边界与上下文](../flow-studio/boundaries-and-context.md)。

条件边 `when` 与循环 `iterable` 只能写**单行表达式**，不能写 `def` 或多语句。

## 相关文档

- [节点类型](../flow-studio/node-types.md)
- 仓库设计文档：[starlark-scripting-guide.md](../../starlark-scripting-guide.md)
