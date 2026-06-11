# 术语表

本表汇总 flow_engine 界面与文档中的核心术语。按字母/拼音排序查阅。

| 术语 | 含义 | 常见界面位置 |
|------|------|----------------|
| **boundary（边界）** | 节点 `inputs` / `outputs` 映射：把上下文路径（如 `$.global.order`）绑定为脚本变量名 | Flow Studio → 节点编辑器 |
| **capability_policy / 能力策略** | 对副作用 builtin 的 allow / suppress / redirect 规则列表 | 环境配置、部署、试运行、测试方案 |
| **context_mapping（上下文映射）** | 测试方案中，把 lookup 行字段映射到 `global_ns` 路径的规则 | 测试中心 → 方案编辑 |
| **Deployment / 部署** | 流程指定版本 + Profile + 运行模式 + 调度方式的生产运行绑定 | 运行中心 → 部署管理 |
| **Draft / 草稿** | 流程未提交的编辑态，可随时修改 | Flow Studio 顶栏 |
| **Flow / 流程** | 一次业务编排的完整定义（节点树、策略、钩子、初始上下文等） | Flow Studio |
| **global_ns** | 运行结束时的全局命名空间；测试断言的对比对象 | 测试中心、运行详情 |
| **hooks（钩子）** | 流程级或节点级在特定时机执行的 Starlark 脚本 | Flow Studio → 流程元数据 / 节点编辑器 |
| **initial_context** | 流程级初始 JSON，试运行/部署时注入 `$.global.*` | Flow Studio → 流程元数据 |
| **Lookup** | 表格式配置或测试数据，脚本通过 `lookup_query` 查询 | Lookup Tab |
| **Mock / mock_config** | 测试时对指定节点替换真实执行的隔离配置 | 测试中心 → 方案编辑 |
| **Node id（节点逻辑 ID）** | 节点在流程内的唯一主键，须匹配 `^[A-Za-z][A-Za-z0-9_]*$`；跳转、指标、Mock 均以此为准 | 节点树、节点编辑器 |
| **Node name（节点展示名）** | 仅用于界面展示；**Task 节点必填且在流程内唯一**，Loop/Subflow 可留空（自动回落为 id） | 节点树 |
| **on_error** | 节点失败时的处置策略：retry / jump / continue / break / ignore / custom | 节点编辑器 |
| **Profile / 环境** | 一组配置的名称：数据字典覆盖、lookup 数据、各模式能力策略等 | 环境配置、试运行、部署 |
| **RunMode（运行模式）** | `debug` / `shadow` / `production`，影响默认能力策略与副作用行为 | 部署、能力策略 |
| **Span** | 单次运行的调用链路片段，含节点耗时与父子关系 | 运行中心 → 运行详情 |
| **Starlark** | 流程脚本语言（Python 风格子集，沙箱化） | 能力与脚本、节点编辑器 |
| **strategy_ref（执行策略引用）** | 节点引用的执行策略名，控制 sync/async/thread/process 等 | 节点编辑器、流程元数据 |
| **Trial run / 试运行** | Flow Studio 中单次调试执行，服务端固定 `RunMode.DEBUG` | Flow Studio → 试运行面板 |
| **Version / 版本** | 流程提交后产生的不可变版本号（V1、V2…）；**部署必须使用已提交版本** | Flow Studio 顶栏 |
| **Worker / 工作节点** | 拉取并执行部署的后台进程（`flow-worker start`） | 运行中心 → 工作节点 |
| **数据字典** | YAML 模块树配置（HTTP/Kafka/ES 连接、应用参数等） | 数据字典 Tab |
| **本次附加策略** | 仅当前一次试运行/调试/测试请求生效的临时 `capability_policy` | 试运行、节点调试、脚本调试折叠区 |
| **副作用 builtin** | `side_effects != none` 的内置函数（如 `http_call`、`kafka_send`），受能力策略约束 | 能力与脚本 → Python 内置 |

## 易混淆对照

| 概念 A | 概念 B | 区别 |
|--------|--------|------|
| 草稿 | 版本 | 草稿可改；版本提交后不可变，部署只能选版本 |
| 试运行 | 部署运行 | 试运行固定 debug 模式；部署才代表真实生产/影子行为 |
| 节点 id | 节点 name | id 参与引擎语义；name 仅供展示（Task 必填唯一） |
| Profile | 数据字典模块 | Profile 是环境名；数据字典是具体 YAML 配置内容 |
| Lookup 命名空间 | 测试 lookup 命名空间 | 测试方案绑定专用命名空间驱动用例行 |
| suppress | redirect | suppress 不执行并返回占位结果；redirect 改参数后仍执行 |

## 相关文档

- [核心概念](core-concepts.md)
- [界面与文档对照](ui-navigation.md)
