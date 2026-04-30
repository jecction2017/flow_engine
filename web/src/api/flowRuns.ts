/** REST client for `/api/flow-runs` (run 历史 / 详情). */

import type { LogEntry, NodeRunInfo } from "@/api/flows";

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const text = await r.text().catch(() => `HTTP ${r.status}`);
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r;
}

export type FlowRunStatus =
  | "running"
  | "completed"
  | "failed"
  | "terminated"
  | string;

export type FlowRunSummary = {
  id: number;
  deployment_id: number | null;
  test_batch_id: number | null;
  flow_code: string;
  ver_no: number;
  mode: string;
  status: FlowRunStatus;
  worker_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  iteration_count: number | null;
  error: string | null;
};

export type FlowRunsListResponse = {
  total: number;
  offset: number;
  limit: number;
  runs: FlowRunSummary[];
};

/**
 * resident 流程 ``node_stats`` 的聚合形态（见 runner/persistence._aggregate_node_stats）；
 * 当前结构为 ``per_node[node_id] = { count, success, failed, avg_ms, p99_ms }``。
 */
export type NodeStatRecord = {
  count: number;
  success: number;
  failed: number;
  avg_ms: number;
  p99_ms: number;
};

export type NodeStats = {
  per_node: Record<string, NodeStatRecord>;
  last_updated_at: string;
};

export type FlowRunDetail = {
  id: number;
  deployment_id: number | null;
  test_batch_id: number | null;
  worker_id: string | null;
  flow_code: string;
  ver_no: number;
  mode: string;
  trigger_context: Record<string, unknown> | null;
  status: FlowRunStatus;
  started_at: string | null;
  finished_at: string | null;
  iteration_count: number | null;
  /** once / cron / test 流程：完整 NodeRunInfo[]；resident 流程为 null。 */
  node_runs: NodeRunInfo[] | null;
  /** resident 流程：聚合统计；其它为 null。 */
  node_stats: NodeStats | null;
  flow_logs: LogEntry[] | null;
  error: string | null;
};

export type ListFlowRunsParams = {
  deployment_id?: number;
  flow_code?: string;
  mode?: string;
  status?: string;
  offset?: number;
  limit?: number;
};

export async function listFlowRuns(
  params: ListFlowRunsParams = {},
): Promise<FlowRunsListResponse> {
  const qs = new URLSearchParams();
  if (params.deployment_id != null) qs.set("deployment_id", String(params.deployment_id));
  if (params.flow_code) qs.set("flow_code", params.flow_code);
  if (params.mode) qs.set("mode", params.mode);
  if (params.status) qs.set("status", params.status);
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.limit != null) qs.set("limit", String(params.limit));
  const q = qs.toString();
  const r = await checkOk(await fetch(`/api/flow-runs${q ? `?${q}` : ""}`));
  return r.json() as Promise<FlowRunsListResponse>;
}

export async function getFlowRun(runId: number): Promise<FlowRunDetail> {
  const r = await checkOk(await fetch(`/api/flow-runs/${runId}`));
  return r.json() as Promise<FlowRunDetail>;
}
