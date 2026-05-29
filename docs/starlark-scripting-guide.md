# Starlark 流程脚本编写指南

本文档面向在 flow_engine 中编写任务节点脚本、条件表达式、循环数据源和用户自定义 `.star` 库的**开发者**。  
若你使用 Cursor Agent 生成脚本，项目内另有精简规则：`.cursor/rules/starlark-scripting.mdc`。

---

## 1. 这是什么？

flow_engine 使用 **Starlark**（一种受 Python 启发但刻意精简、可沙箱化的语言）作为流程脚本语言，运行时基于 `starlark-pyo3`（方言：`Dialect.standard()` + `load()`）。

**与 Python 的核心区别：**

- 语法更像 Python，但**禁用**大量 Python 特性（`import`、`while`、`try`、f-string 等）。
- **不能**在模块顶层写 `if` / `for`，必须包在函数里。
- **不能**直接访问文件、网络、系统时钟；需要的能力由引擎以 **builtin 函数** 形式注入（如 `resolve`、`kafka_receive`、`http_call`、`log_info`）。

语法约束由测试锁定：`tests/test_starlark_dialect_syntax.py`。修改方言或文档示例后建议运行：

```bash
pytest tests/test_starlark_dialect_syntax.py -q
```

---

## 2. 脚本用在什么地方？

| 场景 | 配置位置 | 写法要求 | 返回值 |
|------|----------|----------|--------|
| **任务节点** | YAML 中节点的 `script` | 多行模块级语句 | **最后一个表达式**必须是 `dict`（若为 `None` 则当作 `{}`） |
| **钩子** | `hooks.*` | 同任务脚本 | 无强制 dict |
| **条件分支** | 边的 `when`、测试断言等 | **只能写一行表达式** | `bool` |
| **循环数据** | 循环节点的 `iterable` | **只能写一行表达式** | 可迭代对象 |
| **可复用库** | `.star` 文件，经 `load()` 引用 | 可定义多个 `def` | 无 |

### 2.1 任务脚本：末行必须是 dict

任务脚本按顺序执行，**最后一行的表达式**的求值结果就是节点输出。

```python
# ✅ 直接返回 dict
{"status": "ok", "count": 1}

# ✅ 调用函数，函数 return dict
def build():
    return {"status": "ok", "count": 1}

build()
```

### 2.2 条件与 iterable：只能是表达式

不能写 `def`、不能写多语句、不能写顶层 `if`。

```python
# ✅ 条件 when
resolve("$.global.enabled") and len(resolve("$.global.items")) > 0

# ✅ 循环 iterable
resolve("$.global.items")

# ✅ 或用推导式
[x for x in resolve("$.global.items") if x.get("enabled")]
```

裸写 `$.global.x` 时，引擎可能自动改写为 `resolve("$.global.x")`（iterable 路径）。

---

## 3. 最高频错误：顶层不能有 if / for

从 Python 迁过来时，最容易在**模块顶层**写控制流，在本引擎中会**直接解析失败**：

```text
error: `if` cannot be used outside `def` in this dialect
```

### ❌ 错误示例

```python
recv = kafka_receive(...)
alarms = []
if "ok" in recv and recv["ok"]:
    for m in recv["data"]["messages"]:
        alarms = alarms + [m["value"]]
{"alarms": alarms}
```

### ✅ 正确写法：包进函数，末尾调用

```python
def build():
    recv = kafka_receive(...)
    alarms = []
    if "ok" in recv and recv["ok"]:
        for m in recv["data"]["messages"]:
            alarms = alarms + [m["value"]]
    return {"alarms": alarms}

build()
```

### 顶层可以写什么？

- 赋值、`def`、`load(...)`、`pass`、`print`
- **表达式级**三元：`"ok" if flag else "fail"`
- **推导式**（在表达式里）：`[x for x in items if x > 0]`
- 以 **dict / 函数调用** 结尾的表达式

---

## 4. 不能用哪些 Python 语法？

以下在**整个脚本**中都不能用（包括函数内部），否则会解析失败：

| 禁用 | 请改用 |
|------|--------|
| `import xxx` | `load("internal://...", "symbol")` |
| `while` | `for i in range(n):` |
| `try` / `except` / `raise` | 先判断再执行；出错用 `fail("说明")` |
| `class` | 用 `dict` 表示结构 |
| `global` / `nonlocal` | 通过参数传递；注意函数内赋值会**遮蔽**外层同名变量 |
| `f"{x}"` | `+`、`%`、`.format()`（见第 6 节） |
| `is` | `==` |
| `1 < x < 5` | `1 < x and x < 5` |
| `"a" "b"` 隐式拼接 | `"a" + "b"` |
| `{1, 2}` 集合字面量 | 用 `list` 或 `dict` |
| `**` 幂运算 | 用 `*` 连乘或_builtin_ |
| `a, *rest = seq` 解包赋值 | 用索引或循环 |

**只能在 `def` 里面写的：** `if` / `elif` / `else`、`for`、`return`、`break`、`continue`。

---

## 5. 容易踩坑的语言规则

### 5.1 字符串不能像列表一样遍历

```python
# ❌
for c in "abc":
    pass

# ✅
for c in "abc".elems():
    pass

# ✅ 或推导
chars = [c for c in "abc".elems()]
```

### 5.2 遍历集合时不要边遍历边改

```python
# ❌ 运行报错
for x in items:
    items.remove(x)

# ✅ 遍历副本
for x in items[:]:
    items.remove(x)
```

### 5.3 字典：有序、键不能重复

- 遍历顺序为**插入顺序**。
- `{"a": 1, "a": 2}` 会报错：`Dictionary key repeated`。

### 5.4 模块变量与“冻结”

- 一次脚本求值过程中，**顶层可以多次赋值**。
- 通过 `load()` 加载并缓存的模块在执行 `freeze()` 后会变为不可变。
- 函数里写 `x = 1` 若外层已有 `x`，会创建**局部**绑定（没有 `global` 关键字可用）。

### 5.5 没有原生 I/O

脚本内不能 `open()`、不能自行连 Kafka/HTTP。请使用引擎提供的 builtin，例如：

- `resolve("$.global.path")` — 读流程上下文
- `kafka_receive(...)`、`http_call(...)` / 其它集成 builtin
- `log_info(...)` 等 — 写日志

### 5.6 错误处理

没有异常机制。推荐模式：

```python
def build():
    data = resolve("$.global.payload")
    if data == None:
        fail("payload is missing")
    if not data.get("id"):
        fail("payload.id is required")
    return {"id": data["id"]}

build()
```

`fail("msg")` 会中断脚本并带上错误信息。

### 5.7 递归

本运行时**未禁止**递归，但过深可能栈溢出；复杂逻辑优先用 `for` + `range()`。

---

## 6. 字符串拼接与格式化

本方言**未启用 f-string**，请使用下列方式（均已实测）。

### 6.1 拼接

| 需求 | 写法 |
|------|------|
| 连接两个字面量 | `"hello" + " " + "world"` |
| 连接非字符串 | `"id=" + str(42)` |
| 重复 | `"-" * 40` |
| 累加 | `s = "a"` 然后 `s += "b"` |
| 列表拼成一行 | `",".join(["a", "b", "c"])`（注意：`join` 写在**分隔符**上） |
| 多行文本 | `"line1\n" + "line2"`（无 Python 的三引号 `"""`） |

```python
# ❌ 隐式拼接（解析失败）
label = "err" "code"

# ❌ f-string（未开启）
msg = f"user={uid}"
```

### 6.2 格式化

| 方式 | 示例 | 结果 |
|------|------|------|
| `%` 元组 | `"%s=%d" % ("n", 7)` | `"n=7"` |
| `%` 单参数 | `"n=%d" % 7` | `"n=7"` |
| `%r` | `"%r" % [1, 2]` | `"[1, 2]"` |
| `.format()` | `"{} < {}".format(4, 5)` | `"4 < 5"` |
| 命名占位 | `"{name}={val}".format(name="k", val=9)` | `"k=9"` |
| `repr()` | `repr([1, 2])` | `"[1, 2]"` |

**推荐用于日志与错误：**

```python
log_info("partition=%s offset=%d" % (part, off))
fail("invalid status: %s" % status)
summary = "count={n} ok={ok}".format(n=len(items), ok=True)
```

**复杂 dict/list 的可读输出：**

- `json.encode(obj)`（引擎已扩展 Json 库）
- 或 `log_info("payload:", data)` — 引擎会把容器格式化为 JSON 风格字符串

---

## 7. 读取流程上下文

使用 `resolve`，路径与流程边界 `boundary.inputs` 映射一致：

```python
def build():
    user_id = resolve("$.global.user_id")
    items = resolve("$.global.items")
    return {"user_id": user_id, "n": len(items)}

build()
```

---

## 8. 加载模块 `load()`

```python
load("internal://lib/helpers.star", "double_int", "prefix_key")
load("user://<tenant>/path/to/script.star", "symbol_name")

def build():
    return {"v": double_int(21)}

build()
```

| 前缀 | 含义 |
|------|------|
| `internal://` | 包内 `starlib/internal/` 下的 `.star` 文件 |
| `user://<tenant>/...` | 用户库，路径须以 `.star` 结尾 |

---

## 9. 日志

```python
log_info("processing", item_id)
log_warn("retries high:", count)
log_error("failed:", err_msg)
log_debug("detail:", obj)
```

`log_*` 为无副作用记录；复杂对象会自动格式化为可读字符串。

---

## 10. 时间 builtin（默认 UTC）

Starlark 本身没有 `time` / `datetime` 模块，flow_engine 通过 Python builtin 暴露常用时间能力。

### 10.1 函数清单

| 函数 | 说明 |
|------|------|
| `time_now()` | 当前 UTC 时间，ISO8601 字符串（毫秒精度，`Z` 后缀） |
| `time_now_ts(unit="ms")` | 当前 UTC 时间戳（`unit` 仅支持 `s` / `ms`） |
| `time_format(ts, layout="%Y-%m-%d %H:%M:%S", tz="UTC", unit="ms")` | 时间戳转字符串 |
| `time_parse(text, layout="%Y-%m-%d %H:%M:%S", tz="UTC", unit="ms")` | 字符串转 UTC 时间戳 |
| `time_convert_tz(text, from_tz="UTC", to_tz="UTC", in_layout=..., out_layout=...)` | 时区转换 |
| `time_add(ts, days=0, hours=0, minutes=0, seconds=0, unit="ms")` | 时间戳偏移 |
| `time_diff(start_ts, end_ts, unit="ms", out="seconds")` | 差值计算（`out`: `ms/seconds/minutes/hours/days`） |

### 10.2 使用示例

```python
def build():
    base = time_parse("2026-05-28 10:00:00")  # 默认按 UTC 解析，返回 ms 时间戳
    local = time_convert_tz("2026-05-28 10:00:00", "UTC", "+09:00")
    plus_2h = time_add(base, hours=2)
    delta_min = time_diff(base, plus_2h, out="minutes")
    text = time_format(plus_2h, "%Y-%m-%dT%H:%M:%SZ", "UTC")
    return {"local": local, "delta_min": delta_min, "text": text}

build()
```

### 10.3 推荐实践

- 脚本内统一使用 UTC（默认值已是 `UTC`），避免跨环境歧义。
- 仅在展示层做本地化时区转换。
- 明确传入 `unit`（`s` 或 `ms`），不要依赖隐式猜测。
- 时区优先使用 IANA 名称（如 `Asia/Shanghai`）；若运行环境缺少时区库，可用 `+08:00` 这类偏移格式。

---

## 11. 流程控制 builtin（写在 `def` 内）

| 函数 | 作用 |
|------|------|
| `flow_continue()` | 跳过当前迭代，继续循环 |
| `flow_break()` | 跳出循环 |
| `flow_terminate()` | 终止流程 |
| `flow_jump("node_id")` | 跳转到指定目标节点（参数必须是节点逻辑 ID） |

与 `return` 一样，只能写在函数体内。调试时可能返回 `control_flow` 描述符。前端编辑器可按节点名称选择目标，但保存后仍写入逻辑 ID。

---

## 12. 完整任务脚本示例

```python
load("internal://lib/helpers.star", "normalize_id")

def build():
    raw = resolve("$.global.alarm")
    if raw == None:
        fail("alarm not found")

    aid = normalize_id(raw.get("id", ""))
    if aid == "":
        fail("alarm.id is empty")

    log_info("processing alarm:", aid)

    severity = raw.get("severity", "low")
    action = "escalate" if severity == "high" else "log"

    return {
        "alarm_id": aid,
        "severity": severity,
        "action": action,
    }

build()
```

---

## 13. 编写自查清单

在提交或发布脚本前，可逐项核对：

1. [ ] 是否把 `if` / `for` 写在了顶层？→ 移入 `def` 并 `build()` 调用。
2. [ ] 是否用了 `while`、`try`、`import`、`is`、f-string、`**`？
3. [ ] 是否写了 `"a" "b"` 或 `1 < x < 5`？
4. [ ] 字符串是否用了 `str()` / `%` / `.format()`？是否误用 `for c in 某字符串`？
5. [ ] 是否在 `for` 循环里修改了正在遍历的同一个 list？
6. [ ] `when` / `iterable` 是否只有**一行表达式**？
7. [ ] 任务脚本**最后一行**是否得到 `dict`？
8. [ ] 时间函数是否明确了 `unit` 与时区（默认 UTC，展示再本地化）？
9. [ ] 修改规则或示例后是否跑过 `pytest tests/test_starlark_dialect_syntax.py -q`？

---

## 14. 相关资源

| 资源 | 说明 |
|------|------|
| `.cursor/rules/starlark-scripting.mdc` | Cursor Agent 用精简规则 |
| `tests/test_starlark_dialect_syntax.py` | 方言语法回归测试 |
| `docs/starlark-integration-prompts.md` | 集成与 builtin 设计背景 |
| `examples/kafka_simple_alarms/` | Kafka 相关示例流程与脚本 |
