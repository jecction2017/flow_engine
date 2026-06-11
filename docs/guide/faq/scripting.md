# 脚本常见问题

## Q: 报错 "`if` cannot be used outside `def`"

Starlark 方言要求 `if`/`for` 只能在函数内。把逻辑包进 `def` 并末尾调用：

```python
def build():
    if resolve("$.global.flag"):
        return {"ok": True}
    return {"ok": False}

build()
```

见 [基础语法](../scripting/syntax-essentials.md)。

---

## Q: 报错 "Task script must evaluate to a dict"

任务脚本最后一行必须是 dict。检查是否误返回了字符串、数字或 `None`。

---

## Q: 能用 import 吗？

不能。用 `load("internal://path", "symbol")` 或 `load("user://tenant/module/script.star", "sym")`。

---

## Q: 怎么读上下文？

`resolve("$.global.path.to.field")`，路径不存在返回 `None`。

---

## Q: 怎么打日志？

`log_info("msg", key, value)`、`log_error(...)` 等，在试运行时间线与运行详情中查看。

---

## Q: 函数内赋值会影响外层变量吗？

会创建**局部**绑定（无 `global` 关键字）。通过参数传递或返回 dict 交换数据。

---

## Q: 字符串怎么遍历？

用 `"abc".elems()`，不能 `for c in "abc"`。

---

## Q: 怎么做错误处理？

无 try/except。先判断再执行，或用 `fail("说明")` 中断并带消息。

---

## 相关文档

- [脚本快速开始](../scripting/quick-start.md)
- [内置能力概览](../scripting/builtins-overview.md)
- [上下文与流程控制](../scripting/context-and-flow-control.md)
