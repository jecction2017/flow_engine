# 脚本快速开始

## 概述

流程节点使用 **Starlark**（Python 风格子集）编写脚本。只需少量语法即可返回结构化结果。

## 操作步骤

1. 打开 **能力与脚本 → 用户脚本**，左侧添加模块，再在模块下添加脚本（路径 `模块/名称.star`，id 为 `user://…`）。
2. 编写返回字典的小脚本。
3. 点击 **调试**，在「调试上下文 JSON」中填入模拟数据，查看输出后保存。

## 示例

```python
{"ok": True, "msg": "hello"}
```

## 常见问题

**Q: 报错 “Task script must evaluate to a dict”**  
A: 脚本最终返回值必须是字典，请确保末尾是 `{...}` 或返回 dict 的函数调用。

## 相关文档

- [基础语法](syntax-essentials.md)
- [第一次写脚本](../getting-started/first-script-and-debug.md)
- [用户脚本管理](../capability-center/user-scripts.md)
