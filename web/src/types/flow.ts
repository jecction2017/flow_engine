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

export interface TaskNode {
  type: "task";
  /** 逻辑主键：流程内唯一，字母开头 + 字母/数字/下划线。 */
  id: string;
  /** 展示名，仅可视化使用；留空时 UI 回落到 id。 */
  name: string;
  strategy_ref: string;
  wait_before: boolean;
  condition?: string | null;
  script: string;
  boundary: Boundary;
}

export type LoopCopyItem = "shared" | "shallow" | "deep";
export type LoopIterationIsolation = "shared" | "fork";

export interface IterationCollect {
  from_path: string;
  append_to: string;
}

export interface LoopNode {
  type: "loop";
  id: string;
  name: string;
  strategy_ref: string;
  wait_before: boolean;
  condition?: string | null;
  iterable: string;
  alias: string;
  children: FlowNode[];
  /** 迭代项绑定方式：shared=原对象引用；shallow=copy.copy；deep=copy.deepcopy。 */
  copy_item?: LoopCopyItem;
  /** 迭代上下文隔离：shared=共用父 ctx；fork=每次迭代独立深拷贝 global_ns。 */
  iteration_isolation?: LoopIterationIsolation;
  /** 每次迭代结束后把 ``from_path`` 的值追加到父 ctx 的 ``append_to`` list。 */
  iteration_collect?: IterationCollect | null;
}

export interface SubflowNode {
  type: "subflow";
  id: string;
  name: string;
  strategy_ref: string;
  wait_before: boolean;
  condition?: string | null;
  alias: string;
  children: FlowNode[];
}

export type FlowNode = TaskNode | LoopNode | SubflowNode;

export interface FlowDocument {
  /**
   * 展示名：可选，允许中文/空格。仅用于 UI 渲染；为空时统一回落到 flow_id
   * （详见 `flowDisplayName` 工具函数）。不参与任何业务逻辑 —— 流程的唯一逻辑
   * 主键是目录/URL 上的 flow_id。
   */
  display_name?: string | null;
  version: string;
  strategies: Record<string, ExecutionStrategy>;
  nodes: FlowNode[];
  initial_context?: Record<string, unknown> | null;
}

/**
 * UI 统一的流程显示名计算：优先取 document 的 display_name，其次 flow_id，
 * 最后 fallback 为 "—"，保证永远有值可渲染。
 */
export function flowDisplayName(
  doc: Pick<FlowDocument, "display_name"> | null | undefined,
  flowId?: string | null,
): string {
  const name = (doc?.display_name ?? "").trim();
  if (name) return name;
  const id = (flowId ?? "").trim();
  if (id) return id;
  return "—";
}

export type Selection =
  | { kind: "flow" }
  | { kind: "strategy"; key: string }
  | { kind: "node"; path: number[] };

// ---------------------------------------------------------------------------
// 节点 id / name 规则（与后端 `flow_engine.engine.models.BaseNode` 保持一致）
//   * id：逻辑主键，必填，字母开头 + 字母/数字/下划线；在一个流程内全局唯一。
//   *      所有业务逻辑（跳转、父子关系、调试面板、运行态指标等）都以 id 为准。
//   * name：仅作显示用途，允许中文 / 空格 / 特殊字符。不参与任何业务逻辑。
//   *      留空时 UI 自动回落到 id（与后端 model_validator 行为一致）。
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
 * 返回节点的展示名：优先使用 name；name 为空/空白时回落到 id。
 * 仅用于 UI 渲染，不参与业务逻辑。
 */
export function displayName(n: FlowNode): string {
  const nm = (n.name ?? "").trim();
  if (nm) return nm;
  return nodeId(n);
}

export function defaultStrategies(): Record<string, ExecutionStrategy> {
  return {
    default_sync: { name: "default_sync", mode: "sync" },
  };
}

export function emptyTask(id = "new_task", name?: string): TaskNode {
  return {
    type: "task",
    id,
    name: name ?? id,
    strategy_ref: "default_sync",
    wait_before: false,
    script: '{\n  "ok": True\n}\n',
    boundary: { inputs: {}, outputs: {} },
  };
}

export function emptyLoop(id = "new_loop", name?: string): LoopNode {
  return {
    type: "loop",
    id,
    name: name ?? id,
    strategy_ref: "default_sync",
    wait_before: false,
    iterable: "[]",
    alias: "it",
    children: [emptyTask("loop_body")],
  };
}

export function emptySubflow(id = "new_subflow", name?: string): SubflowNode {
  return {
    type: "subflow",
    id,
    name: name ?? id,
    strategy_ref: "default_sync",
    wait_before: false,
    alias: "sf",
    children: [emptyTask("step_1")],
  };
}
