# 用户脚本

## 概述

在 **能力与脚本 → 用户脚本** 管理可复用的 `.star` 模块。多个流程任务可通过 `load()` 引用同一脚本，避免复制粘贴。路径形如 `模块/名称.star`，URI 为 `user://租户/模块/名称.star`（租户以系统配置为准）。

---

## 操作步骤

### 创建模块与脚本

1. 左侧 **添加模块**（如 `payment_utils`）
2. 模块下 **添加脚本**（如 `calc_fee.star`）
3. 在编辑器编写 Starlark 代码
4. **保存** — 仅用户脚本分区可写；Starlark 内置库为只读

### 定义可导出函数

```python
def calc_fee(amount, rate):
    fee = amount * rate / 100.0
    return {"fee": fee, "net": amount - fee}
```

### 调试

选中脚本 → **调试** 面板 → 填写上下文 JSON → 运行。见 [脚本调试](script-debug.md)。

### 在任务节点引用

```python
load("user://default/payment_utils/calc_fee.star", "calc_fee")
amount = resolve("$.global.order.amount")
calc_fee.calc_fee(amount, 3)
```

`load` 第二个参数为模块内要使用的符号名；也可 `load(..., "*")` 导入多个（若方言支持）。

---

## 与 internal:// 的区别

| | user:// | internal:// |
|---|---------|-------------|
| 管理 | 能力与脚本 → 用户脚本 | 系统打包，只读 |
| 编辑 | 用户可 CRUD | 不可改 |
| 用途 | 业务复用库 | 平台标准库 |

---

## 规范建议

1. 一个文件多个 `def`，由调用方 `load` 后调用
2. 模块顶层避免复杂逻辑；导出函数返回 dict 或标量
3. 命名模块按业务域划分（`http_utils`、`rules`）
4. 用户脚本变更**即时生效**，不依赖流程版本提交（但流程仍引用固定 load 路径）

---

## 相关文档

- [脚本快速开始](../scripting/quick-start.md)
- [load 与模块](../scripting/load-and-modules.md)
- [脚本调试](script-debug.md)
