/** REST client for Python `/api` (Vite dev proxy → http://127.0.0.1:8000). */

import type { FlowDocument } from "@/types/flow";

export type FlowListItem = {
  id: string;
  name: string;
  path: string;
  updated_at: number | null;
};

export type FlowListResponse = {
  flows: FlowListItem[];
  flows_dir: string;
};

const jsonHeaders = { "Content-Type": "application/json" };

export async function fetchFlowList(): Promise<FlowListResponse> {
  const r = await fetch("/api/flows");
  if (!r.ok) throw new Error(`flows: ${r.status}`);
  return r.json() as Promise<FlowListResponse>;
}

export async function fetchFlowRaw(flowId: string): Promise<Record<string, unknown>> {
  const r = await fetch(`/api/flows/${encodeURIComponent(flowId)}`);
  if (!r.ok) throw new Error(`get ${flowId}: ${r.status}`);
  return r.json() as Promise<Record<string, unknown>>;
}

export async function saveFlow(flowId: string, body: FlowDocument): Promise<void> {
  const r = await fetch(`/api/flows/${encodeURIComponent(flowId)}`, {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `save ${flowId}: ${r.status}`);
  }
}

export async function createFlow(id: string, name?: string): Promise<void> {
  const r = await fetch("/api/flows", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ id, name: name ?? id }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `create: ${r.status}`);
  }
}

export async function deleteFlow(flowId: string): Promise<void> {
  const r = await fetch(`/api/flows/${encodeURIComponent(flowId)}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete ${flowId}: ${r.status}`);
}

export type RunFlowRequest = {
  initial_context?: Record<string, unknown> | null;
  merge?: boolean;
  timeout_sec?: number;
};

export type NodeRunTransition = {
  state: string;
  t_ms: number;
};

export type LogLevel = "debug" | "info" | "warn" | "error";

/**
 * Single log entry emitted by a Starlark `log` / `log_info` / `log_warn` /
 * `log_error` call inside a task script or lifecycle hook. `source` tags
 * the origin (task / pre_exec / post_exec / on_iteration_* / on_error /
 * on_start / on_complete / on_failure) so the UI can group / filter
 * entries; `attempt` is only present for retried task runs.
 */
export type LogEntry = {
  level: LogLevel | string;
  message: string;
  ts_ms: number;
  source: string;
  attempt?: number;
  truncated?: boolean;
};

export type NodeRunInfo = {
  node_id: string;
  order: number;
  first_seen_ms: number;
  started_ms: number | null;
  finished_ms: number | null;
  duration_ms: number | null;
  final_state: string;
  parent_id?: string | null;
  iterations?: number | null;
  execution_count?: number;
  transitions: NodeRunTransition[];
  logs?: LogEntry[];
};

export type RunFlowResponse = {
  ok: boolean;
  state: string;
  message: string | null;
  elapsed_ms: number;
  node_state: Record<string, string>;
  node_runs?: NodeRunInfo[];
  flow_logs?: LogEntry[];
  global_ns: Record<string, unknown>;
};

export async function runFlow(flowId: string, body: RunFlowRequest = {}): Promise<RunFlowResponse> {
  const r = await fetch(`/api/flows/${encodeURIComponent(flowId)}/run`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `run ${flowId}: ${r.status}`);
  }
  return r.json() as Promise<RunFlowResponse>;
}
