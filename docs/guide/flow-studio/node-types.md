# 节点类型

## 概述

流程由三类节点组成，在 Flow Studio 左侧节点树中添加。所有节点均有 **id**（逻辑主键）与 **name**（展示名）；Task 的 name 必填且流程内唯一。

---

## task（任务节点）

执行 Starlark 脚本的核心节点。

### 基本要求

- 脚本**最后一行表达式**必须是 `dict`（作为节点输出写入上下文）
- 可通过 `boundary` 声明 inputs/outputs 映射
- 可配置 `cache`（结果缓存）、`capability_overrides`（节点级能力策略）、`on_error`（容错）

### 示例脚本

```python
order = resolve("$.global.order")
{"status": "processed", "order_id": order.get("id")}
```

### 常见配置项

| 字段 | 说明 |
|------|------|
| `script` | Starlark 脚本正文 |
| `boundary.inputs` | 上下文路径 → Starlark 变量名 |
| `boundary.outputs` | Starlark 变量名 → 上下文路径 |
| `condition` | 单行表达式，为 false 时跳过本节点 |
| `strategy_ref` | 引用的执行策略名 |
| `cache` | `cache_key`、`ttl`、`threshold_ms` 等 |
| `capability_overrides` | 仅本节点生效的能力规则 |

---

## loop（循环节点）

对 `iterable` 表达式求值得到的集合进行迭代，子节点在每次迭代中执行。

### 关键字段

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `iterable` | 单行表达式，求值结果须可迭代 | 必填 |
| `alias` | 当前迭代项在上下文中的变量名 | 必填 |
| `copy_item` | 迭代项复制策略：`shared` / `shallow` / `deep` | `shared` |
| `iteration_isolation` | 上下文隔离：`shared` / `fork` | `shared` |
| `iteration_collect` | 从每次迭代收集结果到父上下文列表 | 无 |

### copy_item 说明

| 值 | 行为 |
|----|------|
| `shared` | 迭代项按引用绑定；循环体内的修改对后续迭代可见 |
| `shallow` | 每次迭代 `copy.copy()`，仅顶层隔离 |
| `deep` | 每次迭代 `copy.deepcopy()`，完全隔离 |

### iteration_isolation 说明

| 值 | 行为 |
|----|------|
| `shared` | 迭代体直接修改父级 `$.global`（传统行为） |
| `fork` | 每次迭代获得独立的 ContextStack 深拷贝；迭代内写入不泄漏到父级或兄弟迭代 |

使用 `fork` 时，若需汇总各迭代结果，配置 `iteration_collect`：

```yaml
iteration_collect:
  from_path: "$.global.result"    # 从迭代上下文读取
  append_to: "$.global.results"   # 追加到父上下文列表
```

### 循环控制

脚本内可调用：

- `flow_continue()` — 跳过当前迭代，进入下一项
- `flow_break()` — 结束整个循环

### iterable 示例

```python
# 从上下文取列表
resolve("$.global.items")

# 过滤后迭代
[x for x in resolve("$.global.items") if x.get("enabled")]
```

---

## subflow（子流程节点）

子流程容器，用于逻辑分组与作用域隔离。

### 特点

- 通过 `alias` 为子树提供命名空间前缀
- 可包含 task、loop、其它 subflow 作为子节点
- 本身不执行脚本，仅组织子节点执行顺序
- 适合把一组相关步骤封装为可复用的结构单元

### 与 loop 的区别

| | loop | subflow |
|---|------|---------|
| 驱动方式 | `iterable` 驱动多次迭代 | 单次执行子节点序列 |
| 典型用途 | 批量处理列表 | 分组、命名空间隔离 |

---

## 节点通用字段

三类节点均支持：

| 字段 | 说明 |
|------|------|
| `id` | 逻辑主键，流程内唯一，字母开头 |
| `name` | 展示名（Task 必填唯一） |
| `strategy_ref` | 执行策略引用 |
| `wait_before` | 为 true 时在此节点前形成同步屏障 |
| `condition` | 单行表达式，false 时跳过 |
| `description` | 说明文字，不参与执行 |
| `on_error` | 失败处置策略 |
| `hooks` | 前置/后置钩子脚本 |

---

## 添加节点

1. 在左侧节点树选中父节点（根流程、loop 或 subflow）
2. 点击 **+** 选择 task / loop / subflow
3. 填写 id（须匹配 `^[A-Za-z][A-Za-z0-9_]*$`）与 name（Task 的 name 必填）
4. 在中间编辑器配置脚本或其它字段
5. 保存草稿

---

## 常见问题

**Q: 报错 "Task node 'name' is required"**  
A: Task 节点必须填写非空且流程内唯一的展示名。

**Q: `flow_jump` 跳转无效**  
A: 跳转目标必须是节点的 **id**（逻辑 ID），不是 name。

**Q: 循环内修改了列表，后续迭代也变了**  
A: 默认 `copy_item=shared`。若需隔离，改为 `shallow` 或 `deep`，并视情况配合 `iteration_isolation=fork`。

---

## 相关文档

- [执行策略](execution-strategies.md)
- [边界与上下文](boundaries-and-context.md)
- [钩子、容错与缓存](hooks-on-error-and-cache.md)
- [读懂流程拓扑](read-flow-topology.md)
