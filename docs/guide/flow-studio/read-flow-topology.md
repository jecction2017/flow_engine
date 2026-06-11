# 读懂流程拓扑

## 概述

Flow Studio 左侧 **节点树** 展示流程的完整拓扑：执行顺序、嵌套结构（loop/subflow）、并行关系与策略信息。读懂树结构是编辑、调试和沟通设计的基础。

---

## 树节点展示元素

| 元素 | 含义 |
|------|------|
| **类型徽章** | task / loop / subflow |
| **id** | 逻辑主键（跳转、Mock、指标用） |
| **name** | 展示名（Task 必填） |
| **策略模式** | sync / async / thread / process（由 `strategy_ref` 决定） |
| **wait 标记** | `wait_before=true`，此前并行组须全部完成 |
| **并行组提示** | 相邻非 sync 节点可能隐式并行 |

点击节点在中间区域打开对应编辑器；点击流程根编辑流程元数据。

---

## 结构层次

```
流程根
├── task_A（同步）
├── task_B（async）─┐
├── task_C（async）─┼─ 隐式并行组
├── task_D（sync, wait_before）← 等待 B、C
└── loop_E
    ├── task_E1
    └── subflow_F
        └── task_F1
```

- **顺序**：同层子节点默认按树顺序执行（受策略与 wait_before 影响）
- **loop**：`iterable` 驱动子树重复执行
- **subflow**：分组，不改变迭代语义

---

## 搜索与导航

- 左侧搜索框按 id/name 过滤节点
- 大型流程先定位目标子树再编辑，避免误改相邻节点

---

## 从拓扑推断执行行为

1. 看 **strategy_ref** → 判断是否可能并行
2. 看 **wait_before** → 判断同步汇合点
3. 看 **condition** → 节点可能被 SKIP
4. 看 **loop** → 子树执行次数 = iterable 长度（受 break/continue 影响）

---

## 常见拓扑问题

| 现象 | 可能原因 |
|------|----------|
| 两节点意外并行 | 均为 async 且无 wait_before |
| 循环只跑一次 | iterable 为空或 condition 为 false |
| 子节点不执行 | 父 loop iterable 错误或父节点失败 |
| 跳转后顺序错乱 | `flow_jump` 目标 id 写错 |

---

## 相关文档

- [节点类型](node-types.md)
- [执行策略](execution-strategies.md)
- [试运行流程](trial-run.md)
