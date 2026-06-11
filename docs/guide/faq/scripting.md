# 脚本常见问题

## 报错 “Task script must evaluate to a dict”

脚本最终返回值不是字典。请确保末尾是 `{...}` 或返回 dict 的函数调用。

## 函数没自动补全

先输入前缀（如 `dict_`），或确认函数在 **能力与脚本 → Python 内置** 列表中存在。

## internal 函数未定义

先写正确的 `load("internal://...", "...")` 再使用导出名。见 [load 与模块](../scripting/load-and-modules.md)。
