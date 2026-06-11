# 边界与上下文

## 概述

运行时数据在 **ContextStack** 中，脚本用 `resolve("$.path")` 读取。Task 节点末行 dict 为输出；`boundary` 可做 inputs/outputs 映射。

---

## 路径约定

| 前缀 | 含义 |
|------|------|
| `$.global.*` | 全局命名空间 |
| `$.local.*` | 节点局部（较少直接使用） |

运行结束时的 `$.global` 即断言用的 **global_ns**（剔除系统字段后）。

---

## initial_context

流程元数据中的 JSON；部署/试运行启动时注入 `$.global`。

**试运行**：默认 `merge=false`，面板 JSON **替换**流程定义；勾选 merge 才合并。

---

## boundary

### inputs

YAML：`上下文路径 → Starlark 变量名`

```yaml
boundary:
  inputs:
    "$.global.order": "order"
```

### outputs

```yaml
boundary:
  outputs:
    "result": "$.global.processed_order"
```

---

## 测试 context_mapping（勿与 boundary 混淆）

测试中心用 **context_mapping 模式对象**，不是 `字段名 → $.global.xxx` 扁平表：

| mode | 效果 |
|------|------|
| `spread` | 整行并入 global_ns |
| `wrap` | 包进 `wrap_key` |
| `rules` | `source` 列 → `target` 点分路径 |
| `script` | Starlark 转换 `payload` |

详见 [上下文映射](../test-center/context-mapping.md)。

---

## resolve

```python
resolve("$.global.order.id")  # 不存在 → None
```

`category=runtime`，任何模式可用。

---

## 相关文档

- [上下文与流程控制](../scripting/context-and-flow-control.md)
- [节点类型](node-types.md)
