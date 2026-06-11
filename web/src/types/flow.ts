/** Mirrors `flow_engine` YAML/JSON shape (subset for UI). */

export type StrategyMode = "sync" | "async" | "thread" | "process";

export interface ExecutionStrategy {
  name: string;
  mode: StrategyMode;
  concurrency?: number;
  timeout?: number | null;
  retry_count?: number;
}

export interface Boundary {
  inputs: Record<string, string>;
  outputs: Record<string, string>;
}

export interface TaskCacheConfig {
  cache_key?: string | null;
  ttl?: number | null;
  max_entries?: number | null;
  threshold_ms?: number;
}

/**
 * Capability action — 与后端 ``CapabilityAction`` 枚举一致：
 *   - allow:    放行
 *   - suppress: 抑制（按 spec.suppress_result 返回，不真正执行副作用）
 *   - redirect: 改写参数（具体 builtin 自行解释 redirect_params）
 */
export type CapabilityAction = "allow" | "suppress" | "redirect";

/**
 * 单条 CapabilityRule — 与后端 ``CapabilityRule`` Pydantic 模型一致。
 * 命中规则：``builtin_name`` > ``builtin_category`` > 通配（两者均空）。
 */
export interface CapabilityRule {
  builtin_category?: string | null;
  builtin_name?: string | null;
  action: CapabilityAction;
  redirect_params?: Record<string, unknown>;
}

/** 与后端 ``OnErrorAction`` 一致。 */
export type OnErrorAction = "retry" | "jump" | "continue" | "break" | "ignore" | "custom";

/** 节点失败时的处理策略 — 与后端 ``OnErrorConfig`` 一致。 */
export interface OnErrorConfig {
  action: OnErrorAction;
  target?: string | null;
  script?: string | null;
}

/** 流程级生命周期钩子 — 与后端 ``FlowHooks`` 一致。 */
export interface FlowHooks {
  on_start?: string | null;
  on_complete?: string | null;
  on_failure?: string | null;
}

/** Task / Subflow 执行钩子 — 与后端 ``NodeHooks`` 一致。 */
export interface NodeHooks {
  pre_exec?: string | null;
  post_exec?: string | null;
}

/** Loop 执行钩子 — 与后端 ``LoopHooks`` 一致。 */
export interface LoopHooks extends NodeHooks {
  on_iteration_start?: string | null;
  on_iteration_end?: string | null;
}

/** 从 hooks 对象中剔除空 slot，全空则返回 null。 */
export function normalizeHooks<T extends Record<string, string | null | undefined>>(
  hooks: T | null | undefined,
  keys: readonly (keyof T)[],
): T | null {
  if (!hooks) return null;
  const out = { ...hooks } as T;
  let any = false;
  for (const k of keys) {
    const v = out[k];
    if (typeof v === "string" && v.trim()) {
      any = true;
    } else {
      delete out[k];
    }
  }
  return any ? out : null;
}

export interface TaskNode {
  type: "task";
  /**
   * 引擎用稳定逻辑主键（字母开头 + 字母/数字/下划线），流程内唯一。
   * Studio 对 Task 自动生成并持久化，不向用户展示。
   */
  id: string;
  /**
   * 用户可见的节点名称：必填、去空白后在全流程节点（含 Loop / Subflow）中唯一。
   * Studio 树与编排页仅展示此名称；引擎内部 id 由系统自动分配。
   */
  name: string;
  strategy_ref: string;
  wait_before: boolean;
  condition?: string | null;
  /** 可选说明；不参与执行，仅文档与协作。 */
  description?: string | null;
  script: string;
  boundary: Boundary;
  /**
   * 节点级 CapabilityRule 覆盖。优先级高于 deployment_capability_policy
   * 与系统默认；null / undefined / [] = 无覆盖。
   */
  capability_overrides?: CapabilityRule[] | null;
  cache?: TaskCacheConfig | null;
  hooks?: NodeHooks | null;
  on_error?: OnErrorConfig | null;
}

export type LoopCopyItem = "shared" | "shallow" | "deep";
export type LoopIterationIsolation = "shared" | "fork";

export interface IterationCollect {
  from_path: string;
  append_to: string;
}

export interface LoopNode {
  type: "loop";
  /**
   * 引擎用稳定逻辑主键；Studio 自动生成并持久化，不向用户展示。
   */
  id: string;
  /** 用户可见的节点名称：必填、trim 后在全流程节点中唯一。 */
  name: string;
  strategy_ref: string;
  wait_before: boolean;
  condition?: string | null;
  /** 可选说明；不参与执行，仅文档与协作。 */
  description?: string | null;
  iterable: string;
  alias: string;
  children: FlowNode[];
  /** 迭代项绑定方式：shared=原对象引用；shallow=copy.copy；deep=copy.deepcopy。 */
  copy_item?: LoopCopyItem;
  /** 迭代上下文隔离：shared=共用父 ctx；fork=每次迭代独立深拷贝 global_ns。 */
  iteration_isolation?: LoopIterationIsolation;
  /** 每次迭代结束后把 ``from_path`` 的值追加到父 ctx 的 ``append_to`` list。 */
  iteration_collect?: IterationCollect | null;
  hooks?: LoopHooks | null;
  on_error?: OnErrorConfig | null;
}

export interface SubflowNode {
  type: "subflow";
  /**
   * 引擎用稳定逻辑主键；Studio 自动生成并持久化，不向用户展示。
   */
  id: string;
  /** 用户可见的节点名称：必填、trim 后在全流程节点中唯一。 */
  name: string;
  strategy_ref: string;
  wait_before: boolean;
  condition?: string | null;
  /** 可选说明；不参与执行，仅文档与协作。 */
  description?: string | null;
  alias: string;
  children: FlowNode[];
  hooks?: NodeHooks | null;
  on_error?: OnErrorConfig | null;
}

export type FlowNode = TaskNode | LoopNode | SubflowNode;

export interface FlowDocument {
  /**
   * 流程名称（可选，YAML display_name）；为空时界面显示「未命名流程」，
   * 不向用户展示 flow_id（详见 `flowDisplayName`）。存储主键仍为 flow_id。
   */
  display_name?: string | null;
  /**
   * 文档级语义版本（如 ``1.0.0``），与 ``fe_flow_version.ver_no`` 自增版本无关；
   * Studio 顶部草稿/Vn 选择器对应后者，本字段不在界面手工编辑。
   */
  version: string;
  strategies: Record<string, ExecutionStrategy>;
  nodes: FlowNode[];
  hooks?: FlowHooks | null;
  initial_context?: Record<string, unknown> | null;
}

/**
 * UI 流程展示名：仅用文档中的 display_name；不向用户暴露 flow_id。
 * （flow_id 仍作为 API/存储主键，由下拉框 value 等内部使用。）
 */
export function flowDisplayName(
  doc: Pick<FlowDocument, "display_name"> | null | undefined,
  _flowId?: string | null,
): string {
  const name = (doc?.display_name ?? "").trim();
  if (name) return name;
  return "未命名流程";
}

/**
 * 流程列表项在下拉框中的展示：有 display_name 用名称；否则用 flow_id，
 * 避免多条未命名流程在列表中无法区分（与旧版 `id` fallback 行为一致）。
 */
export function flowListItemLabel(item: { id: string; display_name?: string | null }): string {
  const n = (item.display_name ?? "").trim();
  if (n) return n;
  return item.id;
}

/** Resolve flow_code (storage id) to UI label from a flow list snapshot. */
export function flowCodeDisplayLabel(
  flowCode: string,
  items: readonly { id: string; display_name?: string | null }[],
): string {
  if (!flowCode) return "";
  const hit = items.find((x) => x.id === flowCode);
  return hit ? flowListItemLabel(hit) : "未知流程";
}

/**
 * 与已有流程的 ``display_name``（trim 后大小写不敏感）去重。
 * 冲突时依次使用 ``{base} copy``、``{base} copy 2``、``{base} copy 3``…（即 copyn）。
 * 源名为空时以 ``导入的流程`` 为基底再 uniquify。
 */
export function allocateUniqueFlowDisplayName(
  existingDisplayNames: readonly string[],
  sourceName: string | null | undefined,
): string {
  const norm = (s: string) => s.trim().toLowerCase();
  const used = new Set(
    existingDisplayNames
      .filter((x): x is string => typeof x === "string")
      .map((n) => norm(n))
      .filter((n) => n.length > 0),
  );
  let base = (sourceName ?? "").trim();
  if (!base) base = "导入的流程";
  if (!used.has(norm(base))) return base;
  let n = 1;
  while (true) {
    const candidate = n === 1 ? `${base} copy` : n === 2 ? `${base} copy 2` : `${base} copy ${n}`;
    if (!used.has(norm(candidate))) return candidate;
    n += 1;
  }
}

export type Selection =
  | { kind: "flow" }
  | { kind: "strategy"; key: string }
  | { kind: "node"; path: number[] };

// ---------------------------------------------------------------------------
// 节点 id / name（与后端 `flow_engine.engine.models` 对齐）
//   * id：引擎逻辑主键，字母开头 + 字母/数字/下划线，流程内全局唯一。
//        Studio 自动生成并持久化，不向用户展示。
//   * name：用户可见主标识，必填，trim 后全流程节点（Task / Loop / Subflow）唯一。
// ---------------------------------------------------------------------------

/** id 格式：字母开头，字母/数字/下划线。 */
export const NODE_ID_PATTERN = /^[A-Za-z][A-Za-z0-9_]*$/;

/** 返回 id 格式校验是否通过（空字符串视为不通过）。 */
export function isValidNodeId(id: string): boolean {
  return NODE_ID_PATTERN.test(id);
}

/**
 * 将任意字符串粗略清洗为合法 id，失败时返回空串。
 * 主要用于历史 YAML（id 可能是中文或空）迁移到严格格式时的默认种子。
 */
export function sanitizeToNodeId(raw: string): string {
  const cleaned = (raw || "")
    .replace(/[^A-Za-z0-9_]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
  if (!cleaned) return "";
  if (!/^[A-Za-z]/.test(cleaned)) return `n_${cleaned}`;
  return cleaned;
}

/**
 * 返回节点的逻辑主键（id）。
 * 约定 id 必填且合法，此处仅作安全兜底：仍为空时返回空串，由调用方负责处理。
 * 注意：任何业务逻辑（选中、跳转、调试、计数）都应使用本函数，不要读 `.name`。
 */
export function nodeId(n: FlowNode): string {
  return (n.id ?? "").trim();
}

/**
 * 返回节点的展示名：仅用 name，不向用户暴露 id；空则占位「（未命名）」。
 */
export function displayName(n: FlowNode): string {
  const nm = (n.name ?? "").trim();
  return nm || "（未命名）";
}

/**
 * 在已占用的节点展示名集合中，为 ``preferred`` 分配一个不重复的名称
 * （trim 后比较；若冲突则追加 ``_2``、``_3``…）。
 */
export function allocateUniqueNodeDisplayName(used: Set<string>, preferred: string): string {
  const base = (preferred ?? "").trim() || "新任务";
  if (!used.has(base)) return base;
  let i = 2;
  while (used.has(`${base}_${i}`)) i += 1;
  return `${base}_${i}`;
}

export function defaultStrategies(): Record<string, ExecutionStrategy> {
  return {
    default_sync: { name: "default_sync", mode: "sync" },
  };
}

/** 新建流程时的空白文档（尚未写库）；与后端 POST /api/flows 的默认结构一致。 */
export function emptyFlowDocument(): FlowDocument {
  return {
    display_name: "",
    version: "1.0.0",
    strategies: defaultStrategies(),
    nodes: [],
    initial_context: {},
  };
}

export function emptyTask(id: string, name: string): TaskNode {
  return {
    type: "task",
    id,
    name,
    strategy_ref: "default_sync",
    wait_before: false,
    script: '{\n  "ok": True\n}\n',
    boundary: { inputs: {}, outputs: {} },
  };
}

export function emptyLoop(id: string, name: string, innerDefaultTaskName: string): LoopNode {
  const innerId = `${id}_body`;
  return {
    type: "loop",
    id,
    name,
    strategy_ref: "default_sync",
    wait_before: false,
    iterable: "[]",
    alias: "it",
    children: [emptyTask(innerId, innerDefaultTaskName)],
  };
}

export function emptySubflow(id: string, name: string, innerDefaultTaskName: string): SubflowNode {
  const innerId = `${id}_step`;
  return {
    type: "subflow",
    id,
    name,
    strategy_ref: "default_sync",
    wait_before: false,
    alias: "sf",
    children: [emptyTask(innerId, innerDefaultTaskName)],
  };
}
