# 基础语法

## 概述

流程节点使用 **Starlark**（Python 风格子集）。任务脚本按顺序执行，**最后一行表达式**的求值结果作为节点输出，**必须是 dict**。

条件表达式（`condition`、`when`）、循环 `iterable` 只能是**单行表达式**。

---

## 够用语法清单

| 语法 | 示例 |
|------|------|
| 赋值 | `a = 1` |
| 字典 | `{"k": "v"}` |
| 列表 | `[1, 2, 3]` |
| 函数 | `def fn(x): return x + 1` |
| 条件（须在 def 内） | `if x > 0: return {"ok": True}` |
| 循环（须在 def 内） | `for x in items: ...` |
| 三元表达式 | `"ok" if flag else "fail"` |
| 列表推导 | `[x for x in items if x > 0]` |

---

## 最高频错误：顶层不能有 if / for

模块顶层**不能**写 `if` / `for` / `while`，须包在 `def` 内并在末尾调用：

```python
# ❌ 解析失败
if resolve("$.global.enabled"):
    level = "P1"
{"level": level}

# ✅ 正确
def build():
    if resolve("$.global.enabled"):
        level = "P1"
    else:
        level = "P2"
    return {"level": level}

build()
```

---

## 任务脚本示例

```python
def process():
    sev = resolve("$.global.severity")
    score = resolve("$.global.score") or 0
    if sev == "HIGH" and score >= 80:
        level = "P1"
    else:
        level = "P2"
    return {"level": level, "score": score}

process()
```

或直接返回字面量：

```python
{"level": "P1", "score": 90}
```

---

## 禁用语法（与 Python 不同）

| 禁用 | 请改用 |
|------|--------|
| `import` | `load("internal://...", "sym")` |
| `while` | `for i in range(n):` |
| `try` / `except` / `raise` | 先判断；`fail("msg")` 中断 |
| `class` | 用 `dict` |
| f-string `f"{x}"` | `+` 或 `.format()` |
| `is` | `==` |
| `1 < x < 5` | `1 < x and x < 5` |

---

## 条件与 iterable（单行）

边的 `when`、节点 `condition`、loop 的 `iterable` 只能写**一个表达式**：

```python
# condition / when
resolve("$.global.enabled") and len(resolve("$.global.items") or []) > 0

# iterable
resolve("$.global.items")
```

---

## 错误处理

无异常机制，推荐：

```python
def build():
    data = resolve("$.global.payload")
    if data == None:
        fail("payload is missing")
    return {"id": data.get("id")}

build()
```

---

## 字符串遍历

字符串不能像列表直接 `for c in "abc"`，须用 `.elems()`：

```python
chars = [c for c in "abc".elems()]
```

---

## 相关文档

- [脚本快速开始](quick-start.md)
- [内置能力概览](builtins-overview.md)
- [上下文与流程控制](context-and-flow-control.md)
- 开发者详解：[starlark-scripting-guide.md](../../starlark-scripting-guide.md)
