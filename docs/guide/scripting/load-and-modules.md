# load 与模块

## 概述

通过 `load("internal://...", "...")` 引入内置 Starlark 库导出符号；用户脚本使用 `user://` 路径。

## 示例

```python
load("internal://lib/helpers.star", "double_int", "prefix_key")

v = double_int(21)
key = prefix_key("ioc", "ip")

{"value": v, "key": key}
```

## 结果说明

内置脚本只读，源码可在 **能力与脚本 → Starlark 内置** 查看。

## 相关文档

- [internal 库](../capability-center/internal-starlib.md)
- [用户脚本](../capability-center/user-scripts.md)
