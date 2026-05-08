/** REST client for `/api/deploy-runs` (deploy executions/instances). */

import type { FlowRunDetail, FlowRunsListResponse } from "@/api/flowRuns";

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const text = await r.text().catch(() => `HTTP ${r.status}`);
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r;
}

export type ListDeployRunsParams = {
  deployment_id?: number;
  flow_code?: string;
  mode?: string;
  status?: string;
  worker_id?: string;
  offset?: number;
  limit?: number;
};

export async function listDeployRuns(params: ListDeployRunsParams = {}): Promise<FlowRunsListResponse> {
  const qs = new URLSearchParams();
  if (params.deployment_id != null) qs.set("deployment_id", String(params.deployment_id));
  if (params.flow_code) qs.set("flow_code", params.flow_code);
  if (params.mode) qs.set("mode", params.mode);
  if (params.status) qs.set("status", params.status);
  if (params.worker_id) qs.set("worker_id", params.worker_id);
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.limit != null) qs.set("limit", String(params.limit));
  const q = qs.toString();
  const r = await checkOk(await fetch(`/api/deploy-runs${q ? `?${q}` : ""}`));
  return r.json() as Promise<FlowRunsListResponse>;
}

export async function getDeployRun(runId: number): Promise<FlowRunDetail> {
  const r = await checkOk(await fetch(`/api/deploy-runs/${runId}`));
  return r.json() as Promise<FlowRunDetail>;
}

