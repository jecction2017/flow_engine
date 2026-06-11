# 节点类型

## 概述

流程由三类节点组成，可在左侧节点树中添加。

## task

执行 Starlark 脚本的任务节点。脚本末行须为 dict，作为节点输出。

## loop

对 `iterable` 表达式求值得到的集合迭代；可包含子节点，支持 `flow_break` / `flow_continue`。

## subflow

子流程容器，用于分组与作用域隔离；可包含子节点。

## 相关文档

- [执行策略](execution-strategies.md)
- [边界与上下文](boundaries-and-context.md)
