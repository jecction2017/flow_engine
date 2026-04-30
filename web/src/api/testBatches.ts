/** REST client for `/api/test-batches` (lookup-namespace 驱动批量测试). */

import type { FlowRunDetail, FlowRunsListResponse } from "@/api/flowRuns";

const jsonHeaders = { "Content-Type": "application/json" };

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const text = await r.text().catch(() => `HTTP ${r.status}`);
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r;
}

export type MockMode = "script" | "fixed" | "record_replay" | "fault";
export type FaultType = "timeout" | "exception" | "dirty_data";

export type MockConfig = {
  mode: MockMode;
  // script
  script?: string | null;
  // fixed
  result?: Record<string, unknown> | null;
  // record_replay
  lookup_ns?: string | null;
  profile_code?: string | null;
  key_expr?: string | null;
  record_on_miss?: boolean;
  // fault
  fault_type?: FaultType | null;
  fault_params?: Record<string, unknown>;
};

export type CreateTestBatchBody = {
  flow_code: string;
  ver_no: number;
  test_ns_code: string;
  profile_code: string;
  mock_config?: Record<string, MockConfig>;
  concurrency?: number;
};

export type CreateTestBatchResponse = {
  batch_id: number;
  status: "running" | "completed";
  total_runs: number;
};

export type TestBatchStatus = "running" | "completed" | "failed" | string;

export type TestBatchDetail = {
  id: number;
  flow_code: string;
  ver_no: number;
  test_ns_code: string;
  profile_code: string;
  status: TestBatchStatus;
  total_runs: number;
  completed_runs: number;
  error_runs: number;
  started_at: string | null;
  finished_at: string | null;
};

export async function createTestBatch(
  body: CreateTestBatchBody,
): Promise<CreateTestBatchResponse> {
  const r = await checkOk(
    await fetch("/api/test-batches", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  );
  return r.json() as Promise<CreateTestBatchResponse>;
}

export async function getTestBatch(batchId: number): Promise<TestBatchDetail> {
  const r = await checkOk(await fetch(`/api/test-batches/${batchId}`));
  return r.json() as Promise<TestBatchDetail>;
}

export async function listBatchRuns(
  batchId: number,
  params: { status?: string; offset?: number; limit?: number } = {},
): Promise<FlowRunsListResponse> {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.limit != null) qs.set("limit", String(params.limit));
  const q = qs.toString();
  const r = await checkOk(
    await fetch(`/api/test-batches/${batchId}/runs${q ? `?${q}` : ""}`),
  );
  return r.json() as Promise<FlowRunsListResponse>;
}

export async function getBatchRun(
  batchId: number,
  runId: number,
): Promise<FlowRunDetail> {
  const r = await checkOk(
    await fetch(`/api/test-batches/${batchId}/runs/${runId}`),
  );
  return r.json() as Promise<FlowRunDetail>;
}
