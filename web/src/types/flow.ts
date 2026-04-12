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
  name: string;
  id?: string | null;
  strategy_ref: string;
  wait_before: boolean;
  condition?: string | null;
  script: string;
  boundary: Boundary;
}

export interface LoopNode {
  type: "loop";
  name: string;
  id?: string | null;
  strategy_ref: string;
  wait_before: boolean;
  condition?: string | null;
  iterable: string;
  alias: string;
  children: FlowNode[];
}

export interface SubflowNode {
  type: "subflow";
  name: string;
  id?: string | null;
  strategy_ref: string;
  wait_before: boolean;
  condition?: string | null;
  alias: string;
  children: FlowNode[];
}

export type FlowNode = TaskNode | LoopNode | SubflowNode;

export interface FlowDocument {
  name: string;
  version: string;
  strategies: Record<string, ExecutionStrategy>;
  nodes: FlowNode[];
  initial_context?: Record<string, unknown> | null;
}

export type Selection =
  | { kind: "flow" }
  | { kind: "strategy"; key: string }
  | { kind: "node"; path: number[] };

export function nodeId(n: FlowNode): string {
  return (n.id || n.name).trim();
}

export function defaultStrategies(): Record<string, ExecutionStrategy> {
  return {
    default_sync: { name: "default_sync", mode: "sync" },
  };
}

export function emptyTask(name = "new_task"): TaskNode {
  return {
    type: "task",
    name,
    strategy_ref: "default_sync",
    wait_before: false,
    script: '{\n  "ok": True\n}\n',
    boundary: { inputs: {}, outputs: {} },
  };
}

export function emptyLoop(name = "new_loop"): LoopNode {
  return {
    type: "loop",
    name,
    strategy_ref: "default_sync",
    wait_before: false,
    iterable: "[]",
    alias: "it",
    children: [emptyTask("loop_body")],
  };
}

export function emptySubflow(name = "new_subflow"): SubflowNode {
  return {
    type: "subflow",
    name,
    strategy_ref: "default_sync",
    wait_before: false,
    alias: "sf",
    children: [emptyTask("step_1")],
  };
}
