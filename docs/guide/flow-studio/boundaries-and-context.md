# 边界与上下文

## 概述

- **initial_context**：流程级初始 JSON，映射到 `$.global.*`
- **boundary**：节点 `inputs` / `outputs` 将上下文路径与 Starlark 变量绑定
- 脚本内用 `resolve("$.global.path")` 读取

## 相关文档

- [上下文与流程控制](../scripting/context-and-flow-control.md)
