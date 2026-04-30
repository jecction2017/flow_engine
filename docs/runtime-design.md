# Flow Engine Runtime Layer Design


| 项    | 内容                                                                  |
| ---- | ------------------------------------------------------------------- |
| 文档定位 | 运行调度层完整实现规范，供 coding agent 直接生成代码使用                                 |
| 覆盖范围 | 运行模式、Mock 系统、CapabilityPolicy、Worker、Coordinator、Scheduler、测试框架、API |
| 不覆盖  | 编排层（FlowRuntime 内部逻辑、节点模型、Starlark SDK）——已在 engine/ 实现              |
| 依赖文档 | `docs/design-principles.md`（架构准则）；现有 `engine/`、`db/`、`lookup/` 模块   |


---

## 1. 背景与设计目标

现有系统已完成**流程编排**（FlowRuntime、节点模型、Starlark 执行、数据字典、Lookup）。本层补充**流程运行调度**能力：

1. **运行模式隔离**：同一流程在 debug / shadow / production 三种模式下产生不同的副作用行为，无需修改流程 YAML。
2. **节点 Mock**：测试时按节点替换执行逻辑（自定义脚本 / 固定返回 / 录制回放 / 故障注入），隔离外部依赖。
3. **Worker 生命周期**：Worker 进程注册、心跳、按 Assignment 执行流程、崩溃重启。
4. **Coordinator 调度**：将 Deployment 分配给 Worker，处理死亡 Worker 的故障转移。
5. **Scheduler**：cron / once 调度触发，内嵌在 Coordinator 进程。
6. **测试框架**：以 lookup namespace 行作为测试集，批量在 debug 模式运行并持久化结果，不实现自动对比（用户自行分析）。

**核心约束**：现有 `engine/orchestrator.py`、`engine/models.py`、`starlark_sdk/` 逻辑不重写，只在明确标注的位置做最小侵入式改造。

---

## 2. 模块结构

```
src/flow_engine/
├── runner/                   # 运行调度层（全部新增，__init__.py 已存在为空包）
│   ├── models.py             # RunMode / RunOptions / MockConfig / CapabilityRule 等 Pydantic 模型
│   ├── mode_context.py       # CapabilityPolicy ContextVar + 三层合并逻辑
│   ├── persistence.py        # FlowRunResult → FeFlowRun 写库适配
│   ├── test_runner.py        # lookup namespace → 批量 debug 运行
│   ├── worker.py             # Worker 进程主逻辑
│   ├── coordinator.py        # Deployment→Worker 分配 + 故障转移
│   └── scheduler.py          # cron/once 触发（内嵌在 Coordinator 进程）
├── engine/
│   ├── models.py             # [改造] TaskNode 新增 capability_overrides 字段
│   ├── orchestrator.py       # [改造] FlowRuntime 接受 RunOptions；mock 拦截；node_capability_scope
│   └── starlark_glue.py      # [改造] process_starlark_task payload 增加 run_mode + effective_policy
├── starlark_sdk/
│   └── python_builtin_impl.py # [改造] 副作用 builtins 调用 check_capability
└── db/
    └── models.py             # [改造] 新增 5 张表
```

---

## 3. Pydantic 运行时模型（runner/models.py）

所有模型使用 Pydantic V2（`model_config = ConfigDict(extra="forbid")`）。

### 3.1 RunMode

```python
class RunMode(str, Enum):
    DEBUG      = "debug"       # 本地测试；所有写操作 suppress；保留完整 node_runs
    SHADOW     = "shadow"      # 灰度；写操作按 CapabilityPolicy；保留完整 node_runs
    PRODUCTION = "production"  # 正式线上；所有操作 allow
```

### 3.2 CapabilityAction

```python
class CapabilityAction(str, Enum):
    ALLOW    = "allow"
    SUPPRESS = "suppress"
    REDIRECT = "redirect"
```

### 3.3 CapabilityRule

```python
class CapabilityRule(BaseModel):
    builtin_category: str | None = None
    # 例：db_write / mq_publish / external_api_write / db_read / external_api_read
    # None = 匹配所有类别

    builtin_name: str | None = None
    # 具体 builtin 函数名，优先级高于 builtin_category
    # None = 不限定函数名

    action: CapabilityAction
    redirect_params: dict[str, Any] = Field(default_factory=dict)
    # redirect 时的目标参数，例如 {"profile_code": "shadow"}
    # builtin 从该 profile 取连接配置（shadow_db 地址、shadow_mq topic 等）

    # 匹配规则（按优先级）：
    # 1. builtin_name 不为 None 且匹配 → 命中
    # 2. builtin_category 不为 None 且匹配 → 命中
    # 3. 两者均为 None → 通配，命中所有
```

### 3.4 MockMode 与 FaultType

```python
class MockMode(str, Enum):
    SCRIPT        = "script"         # 用自定义 Starlark 脚本替换节点原始脚本
    FIXED         = "fixed"          # 直接返回预设 result dict
    RECORD_REPLAY = "record_replay"  # 从 lookup namespace 读取录制输出回放
    FAULT         = "fault"          # 注入故障（超时 / 异常 / 脏数据）

class FaultType(str, Enum):
    TIMEOUT    = "timeout"     # 等待 timeout_ms 后抛出 asyncio.TimeoutError
    EXCEPTION  = "exception"   # 直接抛出 RuntimeError(message)
    DIRTY_DATA = "dirty_data"  # 返回用户指定的脏数据 dict（不抛异常）
```

### 3.5 MockConfig

```python
class MockConfig(BaseModel):
    mode: MockMode

    # --- script 模式 ---
    script: str | None = None
    # 替代 Starlark 脚本，接受与原节点相同的 boundary inputs，
    # 可调用所有注册 builtins（lookup_query / dict_get 等），
    # 必须返回 dict（与原节点 result 格式一致）。
    # CapabilityPolicy 在 mock script 执行期间同样生效。

    # --- fixed 模式 ---
    result: dict[str, Any] | None = None
    # 直接返回该 dict，跳过脚本执行。

    # --- record_replay 模式 ---
    lookup_ns: str | None = None
    # 存储录制数据的 lookup namespace（必填）。
    # 每行格式：{"_key": "<key_str>", "<result_key>": <value>, ...}
    # 即在原始 result dict 基础上加 _key 字段。

    profile_code: str | None = None
    # lookup namespace 所属 env profile。
    # None = 使用 FeFlowDeployment.env_profile_code（或当前 test_batch.profile_code）。

    key_expr: str | None = None
    # 计算回放 key 的 Starlark 表达式，在 boundary inputs 绑定后执行，返回 str。
    # None = 默认：对所有 boundary input 值排序序列化后 sha256 取前 16 字节 hex。

    record_on_miss: bool = True
    # cache miss 时是否自动执行真实脚本并录制。
    # True（默认）：首次运行录制，后续回放。
    # False：cache miss 时抛出 MockCacheMissError。

    # --- fault 模式 ---
    fault_type: FaultType | None = None
    fault_params: dict[str, Any] = Field(default_factory=dict)
    # timeout:    {"timeout_ms": int}  — 默认 5000
    # exception:  {"message": str}    — 默认 "injected fault"
    # dirty_data: {"result": dict}     — 返回该 dict，不抛异常

    @model_validator(mode="after")
    def _validate_fields(self) -> "MockConfig":
        if self.mode == MockMode.SCRIPT and not self.script:
            raise ValueError("script mode requires script")
        if self.mode == MockMode.FIXED and self.result is None:
            raise ValueError("fixed mode requires result")
        if self.mode == MockMode.RECORD_REPLAY and not self.lookup_ns:
            raise ValueError("record_replay mode requires lookup_ns")
        if self.mode == MockMode.FAULT and not self.fault_type:
            raise ValueError("fault mode requires fault_type")
        return self
```

### 3.6 RunOptions

```python
class RunOptions(BaseModel):
    mode: RunMode = RunMode.PRODUCTION

    mock_overrides: dict[str, MockConfig] = Field(default_factory=dict)
    # key = node_id（与 TaskNode.id 一致）
    # 仅 TaskNode 支持 mock；LoopNode / SubflowNode 不支持（mock 其 children）

    deployment_capability_policy: list[CapabilityRule] = Field(default_factory=list)
    # Deployment 级 CapabilityPolicy，由 runner/worker.py 从 FeFlowDeployment 加载后注入。
    # test_runner 不传此字段（使用 RunMode 系统默认）。
```

---

## 4. CapabilityPolicy 系统（runner/mode_context.py）

### 4.1 三层覆盖结构

```
优先级（高 → 低）：
  Node 级覆盖    TaskNode.capability_overrides（YAML 字段）
  Deployment 级  RunOptions.deployment_capability_policy
  系统默认       _SYSTEM_DEFAULT_POLICY[RunMode]（hardcoded）
```

查找算法：从 Node 级开始，按序遍历规则列表，取第一条**命中**的规则的 action。命中条件：

1. 若规则的 `builtin_name` 不为 None，则须与传入 `builtin_name` 完全匹配。
2. 否则，若规则的 `builtin_category` 不为 None，则须与传入 `builtin_category` 完全匹配。
3. 否则（两者均为 None）通配，无条件命中。

三层均未命中 → 返回 `CapabilityAction.ALLOW`（最安全的兜底：不阻止未知 builtin）。

### 4.2 系统默认策略（hardcoded）

```python
_SYSTEM_DEFAULT_POLICY: dict[RunMode, list[CapabilityRule]] = {
    RunMode.DEBUG: [
        CapabilityRule(builtin_category="db_write",           action=CapabilityAction.SUPPRESS),
        CapabilityRule(builtin_category="mq_publish",         action=CapabilityAction.SUPPRESS),
        CapabilityRule(builtin_category="external_api_write", action=CapabilityAction.SUPPRESS),
    ],
    RunMode.SHADOW: [
        CapabilityRule(builtin_category="db_write",           action=CapabilityAction.SUPPRESS),
        CapabilityRule(builtin_category="mq_publish",         action=CapabilityAction.SUPPRESS),
        CapabilityRule(builtin_category="external_api_write", action=CapabilityAction.SUPPRESS),
    ],
    RunMode.PRODUCTION: [],  # 空列表 = 全部 allow（三层未命中 → ALLOW）
}
```

### 4.3 ContextVar 设计

```python
from contextvars import ContextVar
from dataclasses import dataclass, field

@dataclass
class _CapCtx:
    mode: RunMode
    base_rules: list[CapabilityRule]   # RunMode 默认 + Deployment 级合并后的基础规则
    node_rules: list[CapabilityRule]   # 当前节点的覆盖规则（进入节点时 push，离开时 pop）

_cap_ctx_var: ContextVar[_CapCtx] = ContextVar(
    "_cap_ctx",
    default=_CapCtx(mode=RunMode.PRODUCTION, base_rules=[], node_rules=[]),
)
```

### 4.4 公开 API

```python
@contextmanager
def run_mode_scope(mode: RunMode, deployment_rules: list[CapabilityRule]) -> Iterator[None]:
    """
    在 FlowRuntime.run() 入口处调用。
    合并 _SYSTEM_DEFAULT_POLICY[mode] + deployment_rules 为 base_rules，
    设置 ContextVar，退出时恢复。
    """

@contextmanager
def node_capability_scope(node_rules: list[CapabilityRule] | None) -> Iterator[None]:
    """
    在 _dispatch_member 进入 TaskNode 时调用（传 node.capability_overrides）。
    将 node_rules push 到 _CapCtx.node_rules，退出时 pop。
    node_rules 为 None 或空列表时，上下文不变（zero-cost）。
    """

def check_capability(builtin_category: str, builtin_name: str) -> tuple[CapabilityAction, dict[str, Any]]:
    """
    由 Python builtin 函数调用。
    按 node_rules → base_rules 顺序查找第一条命中的规则。
    返回 (action, redirect_params)。
    """

def get_run_mode() -> RunMode:
    """返回当前 RunMode，供 persistence / test_runner 使用。"""
```

### 4.5 在 Python builtin 中的使用模式

每个有副作用的 builtin 函数都应在执行前调用 `check_capability`，然后按三路分支执行：

```python
# 示例模式，每个副作用 builtin 都遵循此模式
def _some_write_builtin(arg1, arg2):
    action, redirect_params = check_capability("db_write", "some_write_builtin")
    if action == CapabilityAction.SUPPRESS:
        return {"suppressed": True, "builtin": "some_write_builtin"}
    if action == CapabilityAction.REDIRECT:
        profile_code = redirect_params.get("profile_code")
        # 用 profile_code 从 FeEnvProfile 取连接配置，替换原目标
        # ...（builtin 具体实现决定如何使用 redirect_params）
        pass
    # action == ALLOW：正常执行
    # ... 真实实现
```

`suppress` 返回的 dict 包含 `suppressed: True` 和 `builtin` 键，以便日志可观察。

---

## 5. Mock 系统（engine/orchestrator.py 改造）

### 5.1 拦截位置

mock 拦截在 `FlowRuntime._run_once()` 的**最开始**（pre_exec hook 之前）。
LoopNode、SubflowNode 不受 mock 影响。

### 5.2 各模式执行逻辑

**FIXED 模式**

```
直接 return mock_config.result
不执行 pre_exec / post_exec hook，不调用任何 builtin。
```

**SCRIPT 模式**

```
调用 run_task_script(mock_config.script, ctx, node.boundary.inputs)
与执行原始脚本完全相同的调用路径。
CapabilityPolicy 在 mock script 执行期间同样生效（因为 ContextVar 已设置）。
pre_exec hook：不执行（mock script 已替换了节点执行）。
返回 (result, logs)，将 logs 附加到 NodeRunInfo.logs。
```

**RECORD_REPLAY 模式**

```python
# 1. 计算 key
if mock_config.key_expr:
    key = eval_key_expr(mock_config.key_expr, ctx, node.boundary.inputs)
    # eval_key_expr: 绑定 boundary inputs 到临时 Starlark 模块，求值 key_expr，返回 str
else:
    key = _default_replay_key(ctx, node.boundary.inputs)
    # _default_replay_key: 将所有 boundary inputs 的值序列化排序后 sha256，取前 16 字节 hex

# 2. 查询 lookup namespace
profile = mock_config.profile_code or _resolve_current_profile()
cached_row = lookup_service.query_one(mock_config.lookup_ns, {"_key": key}, profile=profile)

# 3a. 命中：回放
if cached_row is not None:
    result = {k: v for k, v in cached_row.items() if k != "_key"}
    return result

# 3b. 未命中 + record_on_miss=True：录制
if mock_config.record_on_miss:
    result, logs = run_task_script(node.script, ctx, node.boundary.inputs)
    self._append_node_logs(nid, logs, attempt=attempt)
    record_row = {"_key": key, **result}
    lookup_service.append_rows(mock_config.lookup_ns, [record_row], profile=profile)
    return result

# 3c. 未命中 + record_on_miss=False：报错
raise MockCacheMissError(f"No recording for node {nid!r} key {key!r}")
```

注意：`lookup_service.append_rows` 是 Python 应用层调用（`from flow_engine.lookup.lookup_service import append_rows`），不经过 Starlark builtin，不受 CapabilityPolicy 管控。

**FAULT 模式**

```python
if mock_config.fault_type == FaultType.TIMEOUT:
    timeout_ms = mock_config.fault_params.get("timeout_ms", 5000)
    await asyncio.sleep(timeout_ms / 1000 + 1)  # 超过节点 strategy.timeout
    # orchestrator 的 _with_timeout 会截断并抛 asyncio.TimeoutError

elif mock_config.fault_type == FaultType.EXCEPTION:
    msg = mock_config.fault_params.get("message", "injected fault")
    raise RuntimeError(msg)

elif mock_config.fault_type == FaultType.DIRTY_DATA:
    return mock_config.fault_params.get("result", {})
```

---

## 6. 引擎层改造

### 6.1 engine/models.py

在 `TaskNode` 中新增一个可选字段，放在现有字段之后：

```python
from flow_engine.runner.models import CapabilityRule  # 延迟导入或 TYPE_CHECKING 守卫

class TaskNode(BaseNode):
    type: Literal["task"] = "task"
    script: str
    boundary: Boundary = Field(default_factory=Boundary)
    capability_overrides: list[CapabilityRule] | None = None
    # Node 级 CapabilityPolicy 覆盖，优先级最高。
    # None（默认）= 不覆盖，使用 Deployment 级或系统默认。
    # 现有 YAML 不含此字段，反序列化时保持 None，backward compatible。
```

**注意**：`engine/models.py` 使用 `extra="forbid"`。`CapabilityRule` 是 Pydantic 模型，可直接嵌套。为避免循环导入，在 `engine/models.py` 顶部使用 `from __future__ import annotations` 并在需要时延迟导入。

### 6.2 engine/orchestrator.py

#### 6.2.1 FlowRuntime.**init** 修改

```python
def __init__(
    self,
    flow: FlowDefinition,
    *,
    dictionary: dict[str, Any] | None = None,
    run_opts: RunOptions | None = None,   # 新增
) -> None:
    # ... 原有初始化代码 ...
    self._run_opts: RunOptions = run_opts or RunOptions()
```

#### 6.2.2 FlowRuntime.run() 修改

在 `run()` 方法中，用 `run_mode_scope` 包裹整个执行：

```python
async def run(self) -> FlowRunResult:
    install_signal_handlers()
    self._loop = asyncio.get_running_loop()
    self._cancel_dereg = asyncio_main_cancel(self._loop)
    self._t0 = time.monotonic()
    self.flow_state = FlowState.RUNNING
    try:
        with run_mode_scope(
            self._run_opts.mode,
            self._run_opts.deployment_capability_policy,
        ):
            with dictionary_scope(self.dictionary):
                return await self._run_scoped()
    finally:
        # ... 原有 finally 代码 ...
```

#### 6.2.3 FlowRuntime._dispatch_member() 修改

在 TaskNode 分支，用 `node_capability_scope` 包裹：

```python
if isinstance(m, TaskNode):
    with node_capability_scope(m.capability_overrides):
        if mode == StrategyMode.SYNC:
            self._mark(nid, NodeState.RUNNING)
            await self._execute_task_node(m, ctx, tracker, await_result=True)
        else:
            self._mark(nid, NodeState.DISPATCHED)
            await self._execute_task_node(m, ctx, tracker, await_result=False)
```

LoopNode 和 SubflowNode 不需要 `node_capability_scope`（mock 不适用于它们）。

#### 6.2.4 FlowRuntime._run_once() 修改

在方法最开始，紧接 `nid = self._nid(node)` 之后，在 `pre_exec` hook 之前插入：

```python
nid = self._nid(node)

# Mock 拦截（在 pre_exec 之前）
mock = self._run_opts.mock_overrides.get(nid) if self._run_opts else None
if mock is not None:
    return await self._execute_mock(node, ctx, st, mock, attempt=attempt)

# ... 原有 pre_exec + 执行逻辑 ...
```

新增私有方法 `_execute_mock`：

```python
async def _execute_mock(
    self,
    node: TaskNode,
    ctx: ContextStack,
    st: ExecutionStrategy,
    mock: MockConfig,
    *,
    attempt: int = 0,
) -> dict[str, Any]:
    nid = self._nid(node)
    if mock.mode == MockMode.FIXED:
        return dict(mock.result)

    elif mock.mode == MockMode.SCRIPT:
        result, logs = await asyncio.to_thread(
            run_task_script, mock.script, ctx, node.boundary.inputs
        )
        self._append_node_logs(nid, logs, attempt=attempt)
        return result

    elif mock.mode == MockMode.RECORD_REPLAY:
        return await self._execute_mock_record_replay(node, ctx, mock, attempt=attempt)

    elif mock.mode == MockMode.FAULT:
        await self._inject_fault(mock, st)
        return {}  # unreachable; fault always raises

    raise AssertionError(f"unknown mock mode: {mock.mode}")
```

`_execute_mock_record_replay` 按第 5.2 节 RECORD_REPLAY 逻辑实现。
`_inject_fault` 按第 5.2 节 FAULT 逻辑实现（TIMEOUT 使用 `await asyncio.sleep`，EXCEPTION 直接 `raise`，DIRTY_DATA 返回 dict）。

### 6.3 engine/starlark_glue.py

`process_starlark_task` payload 新增两个字段，并在函数体内恢复 CapabilityPolicy 上下文：

```python
def process_starlark_task(payload: dict[str, Any]) -> dict[str, Any]:
    from flow_engine.runner.mode_context import RunMode, run_mode_scope
    from flow_engine.runner.models import CapabilityRule

    run_mode = RunMode(payload.get("run_mode", RunMode.PRODUCTION.value))
    effective_policy = [
        CapabilityRule.model_validate(r)
        for r in payload.get("effective_policy", [])
    ]
    # effective_policy 是调用方（orchestrator）在进入节点后三层合并的最终结果，
    # 此处直接作为 deployment_rules 传入（node_rules 已合并进去），
    # 所以 run_mode_scope 的 deployment_rules 参数即 effective_policy，
    # node_capability_scope 不需要再调用。

    with run_mode_scope(run_mode, effective_policy):
        # ... 原有执行逻辑（不变）...
```

调用方（`FlowRuntime._run_once` PROCESS 分支）在构造 payload 时增加：

```python
payload = {
    "script": node.script,
    "inputs": node.boundary.inputs,
    "flat_inputs": _serialize_inputs(ctx, node.boundary.inputs),
    "dictionary": self.dictionary,
    "run_mode": self._run_opts.mode.value,                          # 新增
    "effective_policy": _serialize_effective_policy(),              # 新增
}
```

其中 `_serialize_effective_policy()` 读取当前 ContextVar（已包含 node 级覆盖），序列化为 `list[dict]`。

### 6.4 starlark_sdk/python_builtin_impl.py

**Builtin 类别标注约定**：在 `@register_builtin` 装饰器或函数文档中用 `category` 字段标明所属类别。当前已有的 builtin 均为只读或无副作用，暂时无需修改。未来新增副作用 builtin 须遵循以下模式：

```python
# 每个有副作用的 builtin 固定模式
from flow_engine.runner.mode_context import check_capability, CapabilityAction

@register_builtin(...)
def _db_upsert_impl(table: str, row: dict) -> dict:
    action, redirect_params = check_capability("db_write", "db_upsert")
    if action == CapabilityAction.SUPPRESS:
        return {"suppressed": True, "builtin": "db_upsert"}
    if action == CapabilityAction.REDIRECT:
        profile_code = redirect_params.get("profile_code")
        # 用 profile_code 替换连接目标后执行
        pass
    # ALLOW：正常执行
    ...
```

现有 6 个 builtin（`demo_echo`、`demo_add`、`http_simple_get`、`dict_get`、`lookup_query`、`user_script_list`）均为只读或无副作用，**不需要修改**。

---

## 7. 数据库模型（db/models.py）

遵循现有规范：`_AuditCols`、`_FE_TABLE_OPTS`（InnoDB / utf8mb4）、无外键约束、业务码作联表键、主键为 `BIGINT UNSIGNED AUTO_INCREMENT`。

### 7.1 FeFlowDeployment

```python
class FeFlowDeployment(_AuditCols, Base):
    __tablename__ = "fe_flow_deployment"
    __table_args__ = (
        Index("idx_fe_flow_deployment_status", "status"),
        Index("idx_fe_flow_deployment_flow_code", "flow_code"),
        {**_FE_TABLE_OPTS, "comment": "流程部署配置表"},
    )

    id:               Mapped[int]      # BIGINT UNSIGNED PK AUTO_INCREMENT
    flow_code:        Mapped[str]      # VARCHAR(128) NOT NULL
    ver_no:           Mapped[int]      # INT UNSIGNED NOT NULL
    mode:             Mapped[str]      # VARCHAR(16) NOT NULL  debug/shadow/production
    schedule_type:    Mapped[str]      # VARCHAR(16) NOT NULL  once/cron/resident
    schedule_config:  Mapped[dict]     # JSON NOT NULL  once:{} cron:{"cron_expr":"0 8 * * *"}
    worker_policy:    Mapped[dict]     # JSON NOT NULL
    # worker_policy 结构：
    # {
    #   "type": "multi_active" | "single_active",
    #   "min_workers": int,          -- 最少 Worker 数
    #   "max_restarts": int,         -- resident 崩溃最大重启次数，默认 5
    #   "restart_backoff_s": int     -- 重启退避基础秒数，默认 30，实际 = base * 2^(attempt-1)
    # }
    capability_policy: Mapped[dict]   # JSON NOT NULL DEFAULT '[]'  list[CapabilityRule]
    status:           Mapped[str]     # VARCHAR(16) NOT NULL  pending/running/stopping/stopped/failed
    env_profile_code: Mapped[str]     # VARCHAR(64) NOT NULL DEFAULT ''
```

### 7.2 FeWorker

```python
class FeWorker(_AuditCols, Base):
    __tablename__ = "fe_worker"
    __table_args__ = (
        UniqueConstraint("worker_id", name="uk_fe_worker_worker_id"),
        Index("idx_fe_worker_status_heartbeat", "status", "last_heartbeat"),
        {**_FE_TABLE_OPTS, "comment": "Worker 注册表"},
    )

    id:             Mapped[int]      # BIGINT UNSIGNED PK
    worker_id:      Mapped[str]      # VARCHAR(64) NOT NULL  UUID
    host:           Mapped[str]      # VARCHAR(255) NOT NULL
    pid:            Mapped[int]      # INT NOT NULL
    status:         Mapped[str]      # VARCHAR(16) NOT NULL  active/idle/dead
    last_heartbeat: Mapped[datetime] # DATETIME(3) NOT NULL
    capabilities:   Mapped[dict]     # JSON NOT NULL  {"max_concurrent_flows": int}
```

### 7.3 FeWorkerAssignment

```python
class FeWorkerAssignment(_AuditCols, Base):
    __tablename__ = "fe_worker_assignment"
    __table_args__ = (
        UniqueConstraint("deployment_id", "worker_id", name="uk_fe_worker_assignment_dep_worker"),
        Index("idx_fe_worker_assignment_worker_id", "worker_id"),
        {**_FE_TABLE_OPTS, "comment": "Worker 任务分配表"},
    )

    id:               Mapped[int]           # BIGINT UNSIGNED PK
    deployment_id:    Mapped[int]           # BIGINT UNSIGNED NOT NULL
    worker_id:        Mapped[str]           # VARCHAR(64) NOT NULL
    role:             Mapped[str]           # VARCHAR(16) NOT NULL  leader/standby/replica
    lease_expires_at: Mapped[datetime|None] # DATETIME(3) NULL  仅 leader 使用；replica/standby 为 NULL
```

### 7.4 FeFlowRun

```python
class FeFlowRun(_AuditCols, Base):
    __tablename__ = "fe_flow_run"
    __table_args__ = (
        Index("idx_fe_flow_run_deployment_id", "deployment_id"),
        Index("idx_fe_flow_run_test_batch_id", "test_batch_id"),
        Index("idx_fe_flow_run_flow_code_started_at", "flow_code", "started_at"),
        {**_FE_TABLE_OPTS, "comment": "流程运行记录表"},
    )

    id:               Mapped[int]       # BIGINT UNSIGNED PK
    deployment_id:    Mapped[int|None]  # BIGINT UNSIGNED NULL  生产运行关联
    test_batch_id:    Mapped[int|None]  # BIGINT UNSIGNED NULL  测试运行关联
    worker_id:        Mapped[str|None]  # VARCHAR(64) NULL
    flow_code:        Mapped[str]       # VARCHAR(128) NOT NULL
    ver_no:           Mapped[int]       # INT UNSIGNED NOT NULL
    mode:             Mapped[str]       # VARCHAR(16) NOT NULL
    trigger_context:  Mapped[dict|None] # JSON NULL  初始 context（test/once/cron 有值；resident 为 NULL）
    status:           Mapped[str]       # VARCHAR(16) NOT NULL  running/completed/failed/terminated
    started_at:       Mapped[datetime]  # DATETIME(3) NOT NULL
    finished_at:      Mapped[datetime|None] # DATETIME(3) NULL
    iteration_count:  Mapped[int|None]  # INT UNSIGNED NULL  resident 流程累计迭代次数
    node_runs:        Mapped[str|None]  # MEDIUMTEXT NULL  once/cron/test 存 JSON(list[NodeRunInfo.to_dict()])
    node_stats:       Mapped[str|None]  # MEDIUMTEXT NULL  resident 存聚合统计 JSON
    flow_logs:        Mapped[str|None]  # TEXT NULL  JSON(list[dict])
    error:            Mapped[str|None]  # TEXT NULL
    # node_runs 与 node_stats 互斥：schedule_type=resident 写 node_stats，其余写 node_runs
```

`node_stats` 结构（resident 流程）：

```json
{
  "per_node": {
    "<node_id>": {
      "count": 12500,
      "success": 12480,
      "failed": 20,
      "avg_ms": 42,
      "p99_ms": 310
    }
  },
  "last_updated_at": "2026-04-30T10:00:00Z"
}
```

### 7.5 FeFlowTestBatch

```python
class FeFlowTestBatch(_AuditCols, Base):
    __tablename__ = "fe_flow_test_batch"
    __table_args__ = (
        Index("idx_fe_flow_test_batch_flow_code", "flow_code"),
        {**_FE_TABLE_OPTS, "comment": "测试批次聚合表"},
    )

    id:             Mapped[int]       # BIGINT UNSIGNED PK
    flow_code:      Mapped[str]       # VARCHAR(128) NOT NULL
    ver_no:         Mapped[int]       # INT UNSIGNED NOT NULL
    test_ns_code:   Mapped[str]       # VARCHAR(64) NOT NULL  lookup namespace 编码
    profile_code:   Mapped[str]       # VARCHAR(64) NOT NULL  lookup namespace 所属 profile
    mock_config:    Mapped[str]       # MEDIUMTEXT NOT NULL  JSON(dict[node_id, MockConfig])
    status:         Mapped[str]       # VARCHAR(16) NOT NULL  pending/running/completed/failed
    started_at:     Mapped[datetime]  # DATETIME(3) NOT NULL
    finished_at:    Mapped[datetime|None] # DATETIME(3) NULL
    total_runs:     Mapped[int]       # INT UNSIGNED NOT NULL DEFAULT 0
    completed_runs: Mapped[int]       # INT UNSIGNED NOT NULL DEFAULT 0
    error_runs:     Mapped[int]       # INT UNSIGNED NOT NULL DEFAULT 0
```

---

## 8. Runner 层新增模块

### 8.1 runner/persistence.py

```python
def create_flow_run(
    *,
    deployment_id: int | None,
    test_batch_id: int | None,
    worker_id: str | None,
    flow_code: str,
    ver_no: int,
    mode: RunMode,
    trigger_context: dict[str, Any] | None,
) -> int:
    """插入 FeFlowRun(status=running)，返回 run_id。"""

def complete_flow_run(
    run_id: int,
    result: FlowRunResult,
    *,
    is_resident: bool,
) -> None:
    """
    is_resident=False：将 result.node_runs 序列化为 JSON 写入 node_runs 列。
    is_resident=True ：计算 node_stats 聚合并写入；不写 node_runs。
    两种情况均写 flow_logs 和 status=completed/failed/terminated。
    """

def fail_flow_run(run_id: int, error: str) -> None:
    """更新 status=failed, error=error, finished_at=now()。"""

def update_iteration_count(run_id: int, count: int) -> None:
    """resident 流程定期调用，更新 iteration_count。"""

def update_node_stats(run_id: int, stats: dict[str, Any]) -> None:
    """resident 流程定期调用，更新 node_stats JSON。"""
```

所有函数使用 `from flow_engine.db.session import get_session`（或项目现有 session 获取方式）执行写操作，遵循项目现有 DB 访问模式。

### 8.2 runner/test_runner.py

```python
async def run_test_batch(
    flow_code: str,
    ver_no: int,
    test_ns_code: str,
    profile_code: str,
    mock_config: dict[str, MockConfig],
    *,
    concurrency: int = 4,
) -> int:
    """
    触发一次测试批次，返回 batch_id。

    执行逻辑：
    1. 从 lookup_service.lookup_query_page(test_ns_code, profile=profile_code) 读取所有行，
       每行即为一个测试用例的 initial_context dict。
    2. 在 DB 创建 FeFlowTestBatch(status=running, total_runs=len(rows))。
    3. 用 asyncio.Semaphore(concurrency) 并发运行每行：
       a. 加载流程定义：从 FeFlowVersion 读取 ver_no 对应版本，用 load_flow_from_dict 解析。
       b. run_opts = RunOptions(mode=RunMode.DEBUG, mock_overrides=mock_config)
       c. runtime = FlowRuntime(flow, run_opts=run_opts)
       d. runtime.ctx.global_ns.update(row)   # 注入测试输入
       e. run_id = persistence.create_flow_run(test_batch_id=batch_id, ...)
       f. result = await runtime.run()
       g. persistence.complete_flow_run(run_id, result, is_resident=False)
       h. 更新 FeFlowTestBatch.completed_runs / error_runs
    4. 最终更新 FeFlowTestBatch.status=completed（或 failed）。
    5. 返回 batch_id。
    """
```

### 8.3 runner/worker.py

Worker 以独立进程方式运行（`flow-worker start`，CLI 在 `__main__.py` 或新增 `runner/__main__.py` 中提供）。

**状态机**

```
INIT → REGISTERING → ACTIVE（心跳循环 + 分配轮询）→ STOPPING → STOPPED
                      ↓
                   运行 Deployment（每个 Assignment 一个 asyncio.Task）
```

**关键方法签名**

```python
class Worker:
    def __init__(self) -> None:
        self.worker_id: str = str(uuid.uuid4())
        self._assignments: dict[int, asyncio.Task] = {}  # deployment_id → Task

    async def start(self) -> None:
        """注册 FeWorker，启动 _heartbeat_loop 和 _poll_assignments 两个后台任务。"""

    async def stop(self) -> None:
        """
        停止所有 assignment Task（cancel + await），更新 FeWorker.status=dead。
        """

    async def _heartbeat_loop(self) -> None:
        """每 10s 更新 FeWorker.last_heartbeat。"""

    async def _poll_assignments(self) -> None:
        """
        每 2s 查询 FeWorkerAssignment WHERE worker_id=self.worker_id AND deleted_at IS NULL。
        新增的 assignment → _start_assignment(assignment)。
        已消失的 assignment → 取消对应 Task。
        """

    async def _start_assignment(self, assignment: FeWorkerAssignment) -> None:
        """
        读取 FeFlowDeployment，根据 schedule_type 创建对应 Task：
          resident → _run_resident(deployment)
          once/cron → _run_once_flow(deployment)
        """

    async def _run_resident(self, deployment: FeFlowDeployment) -> None:
        """
        resident 流程生命周期，带重启 backoff：

        restart_count = 0
        max_restarts = worker_policy["max_restarts"]  默认 5
        backoff_base = worker_policy["restart_backoff_s"]  默认 30

        while True:
            try:
                flow = load_flow(deployment)
                run_opts = RunOptions(
                    mode=RunMode(deployment.mode),
                    deployment_capability_policy=parse_rules(deployment.capability_policy),
                )
                runtime = FlowRuntime(flow, run_opts=run_opts)
                run_id = persistence.create_flow_run(deployment_id=deployment.id, ...)
                result = await runtime.run()
                persistence.complete_flow_run(run_id, result, is_resident=True)
                break  # 正常退出（对 resident 几乎不发生）
            except asyncio.CancelledError:
                persistence.fail_flow_run(run_id, "cancelled")
                raise  # 让 Task 正常退出
            except Exception as e:
                persistence.fail_flow_run(run_id, str(e))
                restart_count += 1
                if restart_count > max_restarts:
                    # 更新 deployment.status = failed
                    break
                delay = backoff_base * (2 ** (restart_count - 1))
                await asyncio.sleep(delay)
        """

    async def _run_once_flow(self, deployment: FeFlowDeployment) -> None:
        """
        运行一次，结束后将 deployment.status 更新为 stopped（或 failed）。
        """
```

**resident 流程迭代统计更新**：在 `_run_resident` 的运行循环中，每 1000 次迭代（或每 60s，取先到者）调用 `persistence.update_iteration_count` 和 `persistence.update_node_stats`。实现方式：在 `FlowRuntime` 的 `on_complete` / `on_iteration_end` hook 或通过 Worker 后台 Task 轮询读取当前 `result.node_runs` 长度。推荐后者（不侵入引擎 hook）。

### 8.4 runner/coordinator.py

Coordinator 以独立进程运行（`flow-coordinator start`），内嵌 Scheduler（见 8.5）。

```python
class Coordinator:
    async def run(self) -> None:
        """主循环，每 5s 执行一轮：
        1. _assign_pending_deployments()
        2. _check_dead_workers()
        Scheduler.tick() 在同一事件循环内每 30s 触发一次（见 8.5）。
        """

    async def _assign_pending_deployments(self) -> None:
        """
        查询 FeFlowDeployment WHERE status=pending AND deleted_at IS NULL。
        对每个 deployment：
          1. 查询 eligible workers：FeWorker WHERE status=active
             AND last_heartbeat > NOW() - 30s AND deleted_at IS NULL
          2. 按 worker_policy.type 创建 FeWorkerAssignment：
             multi_active：为每个 worker（最多 min_workers 个）各插入一行 role=replica
             single_active：选择 1 个 worker 插入 role=leader（lease_expires_at=now+60s），
                            其余插入 role=standby（lease_expires_at=NULL）
          3. INSERT IGNORE（UK uk_fe_worker_assignment_dep_worker 防重）
          4. 更新 deployment.status = running
        """

    async def _check_dead_workers(self) -> None:
        """
        查询 FeWorker WHERE last_heartbeat < NOW() - 30s AND status=active。
        对每个死亡 worker：
          1. 更新 FeWorker.status = dead
          2. 查询该 worker 的所有 active FeWorkerAssignment
          3. 对每个 assignment：
             role=leader（single_active）：
               查找同 deployment_id 的 standby assignment
               若有 standby：UPDATE standby.role=leader, lease_expires_at=now+60s
               若无 standby：将 deployment 重新入队（status=pending，让 Coordinator 重新分配）
             role=replica（multi_active）：
               查找其他可用 active worker，为其创建新 assignment（INSERT IGNORE）
          4. 软删除或标记死亡 worker 的 assignment（DELETE 或 deleted_at=NOW()）
        """
```

### 8.5 runner/scheduler.py

Scheduler 内嵌在 Coordinator 进程，作为一个定时回调存在，**不是独立进程**。

```python
class Scheduler:
    async def tick(self) -> None:
        """
        每 30s 调用一次（由 Coordinator.run() 的事件循环驱动）。

        逻辑：
        1. 查询 FeFlowDeployment WHERE schedule_type='cron' AND status IN ('running','stopped')
        2. 对每个 deployment：
           a. 读取 schedule_config["cron_expr"]
           b. 查询该 deployment 最近一次 FeFlowRun.started_at
           c. 计算 next_run_time = croniter(cron_expr, last_run).get_next(datetime)
           d. 若 next_run_time <= now：
              克隆一条 FeFlowDeployment（schedule_type='once', status='pending',
              parent_deployment_id=deployment.id），让 Coordinator 下一轮分配
        3. 查询 FeFlowDeployment WHERE schedule_type='once' AND status='pending'
           且 created_at < NOW() - 1min（超时保护，防止 Coordinator 遗漏）→ 无需重复触发
        """
```

cron 表达式解析使用 `croniter` 库（需在 `pyproject.toml` 或 `requirements.txt` 中添加依赖）。

---

## 9. HTTP API 新增端点（api/http_api.py）

遵循现有 FastAPI 路由风格（router、Pydantic request/response schema、现有 auth 中间件）。

### 9.1 部署管理

```
POST   /deployments
  Request:  {flow_code, ver_no, mode, schedule_type, schedule_config, worker_policy,
             capability_policy, env_profile_code}
  Response: {id, flow_code, ver_no, mode, status, created_at}

GET    /deployments
  Query:    flow_code?, status?, mode?
  Response: list[{id, flow_code, ver_no, mode, schedule_type, status, created_at}]

GET    /deployments/{id}
  Response: 完整 FeFlowDeployment 字段 + 当前 assignments 列表

PATCH  /deployments/{id}
  Request:  {status: "stopping" | "pending"}   # stopping=停止；pending=重新触发
  Response: {id, status}

DELETE /deployments/{id}
  软删除（updated_at + deleted_at）
```

### 9.2 Worker 状态

```
GET    /workers
  Response: list[{worker_id, host, pid, status, last_heartbeat, assigned_deployments: list[int]}]
```

### 9.3 测试批次

```
POST   /test-batches
  Request:  {flow_code, ver_no, test_ns_code, profile_code, mock_config, concurrency?}
  mock_config: dict[node_id, {mode, ...MockConfig 字段...}]
  Response: {batch_id, status, total_runs}
  异步执行：立即返回 batch_id，后台运行

GET    /test-batches/{id}
  Response: {id, flow_code, ver_no, test_ns_code, status, total_runs, completed_runs, error_runs,
             started_at, finished_at?}

GET    /test-batches/{id}/runs
  Query:    status?, offset?, limit?
  Response: {runs: list[{run_id, status, started_at, finished_at, error?}], total}

GET    /test-batches/{id}/runs/{run_id}
  Response: {run_id, status, flow_code, ver_no, trigger_context, node_runs, flow_logs, error,
             started_at, finished_at}
```

### 9.4 运行历史

```
GET    /flow-runs
  Query:    deployment_id?, flow_code?, mode?, status?, started_after?, started_before?,
            offset?, limit?  （limit 默认 50，最大 200）
  Response: {runs: list[{id, flow_code, ver_no, mode, status, started_at, finished_at,
                         iteration_count?, error?}], total}

GET    /flow-runs/{id}
  Response: 完整 FeFlowRun 字段
  注：node_runs 为 JSON 列表（once/cron/test）；node_stats 为聚合 JSON（resident）；两者互斥
```

---

## 10. 实现顺序与验收标准


| 步骤  | 交付物                                   | 验收标准                                                                   |
| --- | ------------------------------------- | ---------------------------------------------------------------------- |
| 1   | `runner/models.py`                    | Pydantic 模型全部可实例化；MockConfig validator 对非法输入抛 ValueError               |
| 2   | `runner/mode_context.py`              | `check_capability` 单测：三层 override 优先级正确；并发 asyncio 任务隔离                |
| 3   | `db/models.py` + `flow-db apply`      | 5 张新表在 MySQL 创建成功；`flow-db apply` 幂等                                   |
| 4   | `engine/models.py`                    | `TaskNode` 含 `capability_overrides` 字段；现有 YAML 解析无回归                   |
| 5   | `engine/orchestrator.py`              | FlowRuntime 单测：4 种 mock 模式各自行为；node_capability_scope push/pop 正确       |
| 6   | `engine/starlark_glue.py`             | process 模式 suppressed builtin 返回 `{"suppressed": True}`                |
| 7   | `starlark_sdk/python_builtin_impl.py` | 集成测试：debug 模式下副作用 builtin 返回 suppressed dict                           |
| 8   | `runner/persistence.py`               | once/cron 运行写 node_runs；resident 运行写 node_stats；DB 行可读取                |
| 9   | `runner/test_runner.py`               | 端到端：构造 lookup ns → run_test_batch → FeFlowTestBatch + N 条 FeFlowRun 写库 |
| 10  | `runner/worker.py`                    | Worker 注册→心跳→once 部署运行→FeFlowRun 写库；resident 崩溃重启 backoff 正确           |
| 11  | `runner/coordinator.py`               | pending deployment → Worker assignment；死亡 Worker 单活转移 / 多活重分配          |
| 12  | `runner/scheduler.py`                 | cron 表达式到时触发 once deployment                                           |
| 13  | `api/http_api.py`                     | 所有端点 OpenAPI schema 正确；POST /test-batches 异步返回 batch_id                |


---

## 11. 约束与不变量（Invariants）

1. `FeFlowRun.node_runs` 和 `FeFlowRun.node_stats` 同一行不能同时非 NULL。
2. `FeWorkerAssignment` 中同一 `deployment_id` 最多有一行 `role=leader`。
3. `FlowRuntime.run_opts.mock_overrides` 的 key 必须是流程内存在的 `TaskNode.id`，否则 mock 静默无效（不报错，因为 `dict.get` 返回 None）。
4. `MockConfig.mode=SCRIPT` 的 `script` 字段接受的 Starlark 脚本，其执行受当前 `CapabilityPolicy` 管控，与原节点脚本行为一致。
5. `record_replay` 录制的 lookup namespace 行中 `_key` 为保留字段，不应与节点 result 的业务字段重名。建议 result 中避免使用 `_key` 作为输出 key。
6. `Coordinator` 进程单实例运行；多实例时依赖 `FeWorkerAssignment` UK 约束防止重复分配，但 `deployment.status` 更新可能产生重复写，需应用层幂等处理（UPDATE WHERE status='pending'）。
7. Worker 进程的 asyncio 事件循环**不阻塞**：`FlowRuntime.run()` 已是 async；DB 操作需使用 `asyncio.to_thread(sync_db_op)` 包裹同步 SQLAlchemy 调用。
8. `CapabilityPolicy` 的 `redirect` action 目前由具体 builtin 负责解释 `redirect_params`，引擎层不做统一处理。新增 builtin 须在文档中声明支持的 `redirect_params` key。

