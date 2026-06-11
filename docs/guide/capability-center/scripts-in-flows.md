# 脚本在流程中的作用

## 概述

任务节点通过 Starlark 脚本实现业务逻辑：读取上下文、调用内置能力、返回 dict 结果。可复用逻辑可放在 **用户脚本** 或 `internal://` 库中，经 `load` 引入。

## 相关文档

- [用户脚本](user-scripts.md)
- [脚本快速开始](../scripting/quick-start.md)
