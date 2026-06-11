# 第一次写脚本并调试

## 概述

流程逻辑写在 **Starlark 脚本**中。推荐路径：先在 **能力与脚本** 创建用户脚本并调试，再挂到 Flow Studio 任务节点；或直接在节点编辑器编写并用 **节点调试** 验证。

---

## 路径 A：用户脚本（可复用库）

### 步骤

1. **能力与脚本 → 用户脚本**
2. 左侧 **添加模块**（如 `utils`）
3. 模块下 **添加脚本**（如 `greet.star`），路径为 `user://…/utils/greet.star`
4. 编写脚本，末行返回 dict：
   ```python
   name = "world"
   {"greeting": "hello, " + name}
   ```
5. 点击 **调试**，在 **调试上下文 JSON** 填入：
   ```json
   {"name": "Alice"}
   ```
   （若脚本用 `resolve` 读上下文，需在 JSON 中提供对应路径）
6. 查看输出，调整后 **保存**

### 在流程中引用

任务节点脚本中：

```python
load("user://tenant/utils/greet.star", "greet")
greet.greet_fn()
```

（具体 load 路径以界面显示为准。）

---

## 路径 B：任务节点直接编写

1. Flow Studio → 选中 task 节点
2. 在 **脚本** 编辑器编写
3. 保存草稿
4. 点击 **节点调试**（抽屉），填写上下文与本次附加策略
5. 执行并查看输出

---

## 推荐调试步骤

1. **先最小返回** — `{"ok": True}` 确认管线通
2. **加 resolve** — 从上下文读一个字段
3. **加逻辑** — 包在 `def` 内的 if/for
4. **加集成** — `dict_get`、`lookup_query`（不抑制）先于 `http_call`（可能抑制）
5. **全流程试运行** — 节点联调

---

## 常见 первые 错误

| 错误 | 处理 |
|------|------|
| Task must evaluate to dict | 末行改为 `{...}` 或 `fn()` 返回 dict |
| if outside def | 逻辑移入 `def` |
| SUPPRESSED on http_call | debug 预期；allow 或 Mock |

---

## 相关文档

- [脚本快速开始](../scripting/quick-start.md)
- [基础语法](../scripting/syntax-essentials.md)
- [脚本调试](../capability-center/script-debug.md)
- [节点调试](../flow-studio/node-debug.md)
- [用户脚本管理](../capability-center/user-scripts.md)
