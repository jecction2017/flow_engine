/** REST client for `/api/test-plans` (测试方案：可维护、多次运行). */

import type { BatchResultSummary, ContextMapping, MockConfig } from "@/api/testBatches";

const jsonHeaders = { "Content-Type": "application/json" };

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const text = await r.text().catch(() => `HTTP ${r.status}`);
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r;
}

export type TestPlanSummary = {
  id: number;
  name: string;
  flow_code: string;
  version_channel: string;
  test_ns_code: string;
  profile_code: string;
  concurrency: number;
  updated_at: string | null;
  created_at: string | null;
};

export type TestPlanDetail = TestPlanSummary & {
  mock_config: Record<string, MockConfig>;
  context_mapping: ContextMapping;
  assertions: Array<Record<string, unknown>>;
};

export type CreateTestPlanBody = {
  name: string;
  flow_code: string;
  version_channel?: string;
  test_ns_code: string;
  profile_code: string;
  concurrency?: number;
  mock_config?: Record<string, MockConfig>;
  context_mapping?: ContextMapping;
  assertions?: Array<Record<string, unknown>>;
  /**
   * 计划级默认 CapabilityRule。批次创建时若未显式传入，继承此值。
   * 测试中心运行恒为 RunMode.DEBUG（副作用类 builtin 默认 SUPPRESS），
   * 此处规则用于 **白名单 / REDIRECT 沙箱**（与调试入口同语义）。
   */
  capability_policy?: Array<Record<string, unknown>>;
};

export type PatchTestPlanBody = Partial<CreateTestPlanBody>;

export async function listTestPlans(params: { flow_code?: string } = {}): Promise<{ plans: TestPlanSummary[] }> {
  const qs = new URLSearchParams();
  if (params.flow_code) qs.set("flow_code", params.flow_code);
  const q = qs.toString();
  const r = await checkOk(await fetch(`/api/test-plans${q ? `?${q}` : ""}`));
  return r.json() as Promise<{ plans: TestPlanSummary[] }>;
}

export async function createTestPlan(body: CreateTestPlanBody): Promise<TestPlanSummary> {
  const r = await checkOk(
    await fetch("/api/test-plans", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  );
  return r.json() as Promise<TestPlanSummary>;
}

export async function getTestPlan(planId: number): Promise<TestPlanDetail> {
  const r = await checkOk(await fetch(`/api/test-plans/${planId}`));
  return r.json() as Promise<TestPlanDetail>;
}

export async function patchTestPlan(planId: number, body: PatchTestPlanBody): Promise<TestPlanSummary> {
  const r = await checkOk(
    await fetch(`/api/test-plans/${planId}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  );
  return r.json() as Promise<TestPlanSummary>;
}

export async function deleteTestPlan(planId: number): Promise<{ ok: true }> {
  const r = await checkOk(await fetch(`/api/test-plans/${planId}`, { method: "DELETE" }));
  return r.json() as Promise<{ ok: true }>;
}

export async function runTestPlan(planId: number): Promise<{ batch_id: number; status: string; total_runs: number }> {
  const r = await checkOk(
    await fetch(`/api/test-plans/${planId}/run`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({}),
    }),
  );
  return r.json() as Promise<{ batch_id: number; status: string; total_runs: number }>;
}

export type TestPlanBatchItem = {
  plan_batch_no?: number;
  batch_id: number;
  status: string;
  flow_code: string;
  resolved_ver_no: number;
  test_ns_code: string;
  profile_code: string;
  total_runs: number;
  completed_runs: number;
  error_runs: number;
  started_at: string | null;
  finished_at: string | null;
  elapsed_ms: number | null;
  snapshot: { created_at?: string; version_channel?: string | null };
  result_summary?: BatchResultSummary;
  assertion_pass_rate?: number | null;
};

export async function listTestPlanBatches(
  planId: number,
  params: { status?: string; offset?: number; limit?: number } = {},
): Promise<{ plan_id: number; total: number; offset: number; limit: number; batches: TestPlanBatchItem[] }> {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.limit != null) qs.set("limit", String(params.limit));
  const q = qs.toString();
  const r = await checkOk(await fetch(`/api/test-plans/${planId}/batches${q ? `?${q}` : ""}`));
  return r.json() as Promise<{ plan_id: number; total: number; offset: number; limit: number; batches: TestPlanBatchItem[] }>;
}

export async function copyTestPlan(planId: number, body: { name?: string } = {}): Promise<TestPlanSummary> {
  const r = await checkOk(
    await fetch(`/api/test-plans/${planId}/copy`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  );
  return r.json() as Promise<TestPlanSummary>;
}

export async function compareTestPlanBatches(
  planId: number,
  leftBatchId: number,
  rightBatchId: number,
): Promise<{
  left_batch_id: number;
  right_batch_id: number;
  cases: Array<{
    case_key: string;
    left: { run_id: number; status: string; verdict?: string } | null;
    right: { run_id: number; status: string; verdict?: string } | null;
    changed: boolean;
  }>;
}> {
  const qs = new URLSearchParams({
    left: String(leftBatchId),
    right: String(rightBatchId),
  });
  const r = await checkOk(await fetch(`/api/test-plans/${planId}/batches/compare?${qs}`));
  return r.json() as Promise<{
    left_batch_id: number;
    right_batch_id: number;
    cases: Array<{
      case_key: string;
      left: { run_id: number; status: string; verdict?: string } | null;
      right: { run_id: number; status: string; verdict?: string } | null;
      changed: boolean;
    }>;
  }>;
}

