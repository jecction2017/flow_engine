/** REST client for run-detail entry points (deploy / test).
 *
 * The flow engine has split detail into two cheap dimensions:
 *
 *   * `FlowRunDetail` keeps lifecycle metadata + rollup counters only
 *     (`span_count` / `sampled_span_count`); per-execution trace lives
 *     in `fe_run_span` and is queried via the dedicated spans API
 *     (see `@/api/spans`).
 *   * `FlowRunSummary` is the list-row projection used by deploy runs
 *     / test batch runs / overview.
 *
 * Per-node detail lives in spans; flow-level hook logs are on the run row
 * as ``flow_logs`` (on_start / on_complete / on_failure).
 */
import type { LogEntry } from "@/api/flows";

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

/** Structured runtime failure (who / when / what / how). */
export type FailureDetail = {
  category?: string;
  category_label?: string;
  occurred_at?: string;
  summary?: string;
  node_id?: string | null;
  node_name?: string | null;
  phase?: string | null;
  phase_label?: string | null;
  exception_type?: string | null;
  exception_message?: string | null;
  source_file?: string | null;
  line?: number | null;
  column?: number | null;
  detail?: string | null;
  script_excerpt?: string | null;
  context?: Record<string, unknown>;
  cause_chain?: string[];
};

export type RunEvaluation = {
  verdict?: string;
  flow_state?: string;
  rules?: Array<{ id: string; pass: boolean; message: string }>;
  reason?: string;
  message?: string;
};

export type FlowRunSummary = {
  id: number;
  deployment_id: number | null;
  test_batch_id: number | null;
  /** run origin (derived server-side). */
  source?: "deployment" | "test_batch" | "adhoc" | string;
  flow_code: string;
  ver_no: number;
  mode: string;
  status: FlowRunStatus;
  worker_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  failure_detail?: FailureDetail | null;
  /** 部署运行：累计触发的 Span 总数（采样前）。仅 deploy_runs 提供。 */
  span_count?: number | null;
  /** 部署运行：实际写库的 Span 数量（即被采样的样本）。仅 deploy_runs 提供。 */
  sampled_span_count?: number | null;
  /** 调度类型：subscription / once / cron / test，影响详情页布局。 */
  schedule_type?: string | null;
  trigger_type?: string | null;
  /** 测试批次专用列。 */
  case_index?: number | null;
  case_key?: string | null;
  verdict?: string | null;
  batch_run_no?: number;
};

export type FlowRunsListResponse = {
  total: number;
  offset: number;
  limit: number;
  runs: FlowRunSummary[];
};

/**
 * Lifecycle + rollup view of one run.
 *
 * Detailed execution trace is NOT in here — query
 *   `/api/deploy-runs/{id}/spans` or `/api/test-runs/{id}/spans`
 * to enumerate spans, then `/api/spans/{span_id}` for a specific
 * sample's children / logs / attributes.
 */
export type FlowRunDetail = {
  id: number;
  deployment_id: number | null;
  test_batch_id: number | null;
  source?: "deployment" | "test_batch" | "adhoc" | string;
  worker_id: string | null;
  flow_code: string;
  ver_no: number;
  mode: string;
  schedule_type?: string | null;
  trigger_type?: string | null;
  trigger_context: Record<string, unknown> | null;
  status: FlowRunStatus;
  started_at: string | null;
  finished_at: string | null;
  /** 部署运行：累计触发的 Span 总数（含未采样）。 */
  span_count?: number | null;
  /** 部署运行：实际写库的 Span 数量。 */
  sampled_span_count?: number | null;
  /** 测试运行/test_batch 子运行：case 标识。 */
  case_index?: number | null;
  case_key?: string | null;
  error: string | null;
  /** Structured failure report; mirrors ``error`` with who/when/what/how fields. */
  failure_detail?: FailureDetail | null;
  evaluation?: RunEvaluation | null;
  /** 流程级钩子日志（部署/测试运行持久化）。 */
  flow_logs?: LogEntry[] | null;
  /** 运行结束时的全局上下文（已剔除 dictionary），与试运行 global_ns 对齐。 */
  global_ns?: Record<string, unknown> | null;
};

export type ListFlowRunsParams = {
  deployment_id?: number;
  source?: string;
  flow_code?: string;
  mode?: string;
  status?: string;
  offset?: number;
  limit?: number;
};

export async function listFlowRuns(
  params: ListFlowRunsParams = {},
): Promise<FlowRunsListResponse> {
  void params;
  throw new Error(
    "Deprecated: /api/flow-runs has been removed. Use /api/deploy-runs (Run Center) or /api/test-batches/{id}/runs (Test Center).",
  );
}

export async function getFlowRun(runId: number): Promise<FlowRunDetail> {
  void runId;
  throw new Error(
    "Deprecated: /api/flow-runs/{id} has been removed. Use /api/deploy-runs/{id} (Run Center) or /api/test-batches/{batch}/runs/{id} (Test Center).",
  );
}

// Re-export for legacy imports.
export { checkOk as _checkOk };
