# 基础语法

## 概述

任务脚本常用语法如下；最后一行表达式的求值结果作为节点输出（必须是 **dict**）。

## 够用语法清单

- 变量：`a = 1`
- 字典：`{"k": "v"}`
- 列表：`[1, 2, 3]`
- 条件：`if/else`
- 函数：`def fn(x): return x`

## 示例

```python
sev = "HIGH"
score = 90

if sev == "HIGH" and score >= 80:
    level = "P1"
else:
    level = "P2"

{"level": level, "score": score}
```

## 结果说明

流程引擎将末行 dict 作为该节点输出，并可通过 boundary 映射写入全局上下文。

## 相关文档

- [内置能力概览](builtins-overview.md)
- [上下文与流程控制](context-and-flow-control.md)
