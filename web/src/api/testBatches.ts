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

export type ContextMapping =
  | { mode: "spread" }
  | { mode: "wrap"; wrap_key: string; wrap_as_list?: boolean }
  | {
      mode: "rules";
      rules: Array<{
        source: string;
        target: string;
      }>;
    };

export type CreateTestBatchBody = {
  flow_code: string;
  /**
   * 版本选择：
   * - 兼容旧接口：直接用 ver_no（必须 >=1）
   * - 新接口：用 version_channel（latest/draft/vN/N）
   */
  ver_no?: number;
  version_channel?: string;
  test_ns_code: string;
  profile_code: string;
  mock_config?: Record<string, MockConfig>;
  context_mapping?: ContextMapping;
  concurrency?: number;
  assertions?: Array<Record<string, unknown>>;
  /**
   * 批次级 CapabilityRule。优先级高于 plan 级、profile 级、系统默认。
   * 测试中心运行恒为 RunMode.DEBUG（副作用类 builtin 默认 SUPPRESS），
   * 此处规则用于 **白名单 / REDIRECT 沙箱**（与调试入口同语义）。
   */
  capability_policy?: Array<Record<string, unknown>>;
};

export type CreateTestBatchResponse = {
  batch_id: number;
  status: "running" | "completed";
  total_runs: number;
};

export type TestBatchStatus = "running" | "completed" | "failed" | string;

export type BatchResultSummary = {
  by_status: Record<string, number>;
  verdict_counts: { pass: number; fail: number; none: number };
  first_failures: Array<{
    run_id: number;
    case_index: number;
    case_key: string;
    status: string;
    verdict: string | null;
    error: string | null;
  }>;
};

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
  plan?: { id: number; name: string } | null;
  summary?: BatchResultSummary | null;
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
