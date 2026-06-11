# 核心概念

## 概述

flow_engine 把业务步骤编排成**可版本化的流程**，在指定**环境（Profile）**下试运行、测试或部署运行。以下概念贯穿所有界面，建议先建立统一理解。

---

## Flow（流程）

一次业务编排的完整定义，包含：

- **节点树**（task / loop / subflow）
- **执行策略**（sync、async、thread、process）
- **初始上下文**（`initial_context`）
- **流程级钩子**（`on_start` / `on_complete` / `on_failure`）

在 **Flow Studio** 中编辑。保存为**草稿**后可随时修改；**提交**后产生不可变**版本号**（V1、V2…）。**部署只能绑定已提交版本**，不能使用草稿。

---

## Node（节点）

流程中的执行单元，三类节点各司其职：

| 类型 | 作用 | 关键字段 |
|------|------|----------|
| **task** | 执行 Starlark 脚本，末行须返回 `dict` | `script`、`boundary`、`cache`、`capability_overrides` |
| **loop** | 对 `iterable` 表达式求值得到的集合迭代，可含子节点 | `alias`、`copy_item`、`iteration_isolation`、`iteration_collect` |
| **subflow** | 子流程容器，用于分组与作用域隔离 | `alias`、`children` |

### 节点 id 与 name（重要）

- **id**：流程内唯一逻辑主键，须匹配 `^[A-Za-z][A-Za-z0-9_]*$`（字母大小写均可开头）。跳转、Mock、指标、调试均以 id 为准。
- **name**：界面展示名。**Task 节点必填且在流程内唯一**；Loop/Subflow 可留空，自动回落为 id。

---

## Profile（环境）

一组配置的命名空间，通常对应 dev / staging / prod。每个 Profile 包含：

- **数据字典覆盖**（连接器地址、超时、鉴权等）
- **Lookup 表数据**（按 Profile 隔离）
- **系统能力策略**（`system_capability_policy`，按 debug / shadow / production 分别配置）

试运行、测试、部署时均需选择 Profile。

---

## Deployment（部署）

把某个流程的**指定版本**绑定到 Profile、运行模式、调度与 Worker 策略，由 **Worker** 拉取执行。

---

## RunMode（运行模式）

| 模式 | 典型场景 | 集成类 builtin 默认 |
|------|----------|----------------------|
| **debug** | 试运行、节点调试、测试中心（服务端强制） | 抑制 `integration` / `db_read` / `db_write` / `mq_publish` **类别** |
| **shadow** | 影子部署 | 同 debug 类别的系统默认抑制 |
| **production** | 生产部署 | 系统默认不抑制（空规则列表） |

抑制按 builtin 的 **`category`** 判断，不是简单按 `side_effects` 字段。`dictionary`、`lookup` 类（如 `dict_get`、`lookup_query`）在 debug 下**仍可执行**。

---

## 能力策略（Capability Policy）

控制副作用 builtin 是否执行。运行时合并为 **4 层**（高 → 低）：

1. **节点能力策略** — `capability_overrides`（随流程版本发布）
2. **运行附加策略** — 技术字段 `deployment_capability_policy`：试运行/调试/测试的 `capability_policy` 与部署的 `capability_policy` **同一优先级槽位**（入口名称不同，语义相同）
3. **环境系统能力策略** — Profile 的 `system_capability_policy`（对应当前 RunMode 段）
4. **运行模式内置默认** — `mode_context.system_default_policy(mode)`

匹配顺序：节点栈 → base_rules（2+3+4 拼接）→ 未命中则 **ALLOW**。

详见 [各层优先级](../capability-policy/layer-priority.md)。

---

## 上下文（Context）

- **initial_context**：流程启动时注入 `$.global.*`；试运行默认**覆盖**流程定义（`merge=false`），勾选 merge 才合并
- **context_mapping**：测试/订阅把输入行映射进 `global_ns`（`spread` / `wrap` / `rules` / `script`）
- **boundary**：节点 inputs/outputs 映射
- **global_ns**：运行结束时的全局命名空间，断言对比对象

---

## Lookup 与数据字典

| 概念 | 访问方式 |
|------|----------|
| 数据字典 | `dict_get("module.key", default)` |
| Lookup | `lookup_query(namespace, filter)` — 等值 AND 过滤，空 filter 最多 10_000 行 |

---

## 相关文档

- [术语表](glossary.md)
- [上下文映射](../test-center/context-mapping.md)
- [调用为何被抑制](../capability-policy/why-calls-are-suppressed.md)
