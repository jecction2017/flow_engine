/** REST client for `/api/...spans` (execution trace records).
 *
 * A Span captures one execution unit: an entire flow run, a single
 * loop iteration, a subflow call, or a task. Spans form a tree via
 * `parent_span_id`, so the same client surface serves both
 * "list spans of a run" (deploy/test) and "drill into one span".
 */

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const text = await r.text().catch(() => `HTTP ${r.status}`);
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r;
}

export type SpanStatus = "success" | "failed" | "skipped" | "running" | string;

export type SpanNodeType =
  | "flow_root"
  | "task"
  | "loop_iter"
  | "subflow"
  | string;

/** Log entry attached to a span — shape mirrors backend `LogEntry`. */
export type SpanLogEntry = {
  level: string;
  msg: string;
  source: string;
  t_ms: number;
};

/** Direct-child summary projected onto the parent span. */
export type SpanChildSummary = {
  node_id: string;
  duration_ms: number | null;
  status: SpanStatus;
};

export type SpanSummary = {
  id: number;
  deploy_run_id: number | null;
  test_run_id: number | null;
  flow_code: string;
  node_id: string;
  node_type: SpanNodeType;
  span_seq: number;
  parent_span_id: number | null;
  scope_key: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  status: SpanStatus;
  error: string | null;
  sampled: boolean;
};

export type SpanDetail = SpanSummary & {
  child_spans: SpanChildSummary[] | null;
  logs: SpanLogEntry[] | null;
  attributes: Record<string, unknown> | null;
};

export type SpansListResponse = {
  total: number;
  offset: number;
  limit: number;
  /** Distinct node_ids present in the run — populates a filter dropdown. */
  node_ids: string[];
  items: SpanSummary[];
};

export type ListSpansParams = {
  node_id?: string;
  status?: SpanStatus | string;
  scope_key?: string;
  started_after?: string;
  started_before?: string;
  offset?: number;
  limit?: number;
};

function buildQuery(params: ListSpansParams): string {
  const qs = new URLSearchParams();
  if (params.node_id) qs.set("node_id", params.node_id);
  if (params.status) qs.set("status", String(params.status));
  if (params.scope_key) qs.set("scope_key", params.scope_key);
  if (params.started_after) qs.set("started_after", params.started_after);
  if (params.started_before) qs.set("started_before", params.started_before);
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.limit != null) qs.set("limit", String(params.limit));
  const q = qs.toString();
  return q ? `?${q}` : "";
}

export async function listDeployRunSpans(
  deployRunId: number,
  params: ListSpansParams = {},
): Promise<SpansListResponse> {
  const r = await checkOk(
    await fetch(`/api/deploy-runs/${deployRunId}/spans${buildQuery(params)}`),
  );
  return r.json() as Promise<SpansListResponse>;
}

export async function listTestRunSpans(
  testRunId: number,
  params: ListSpansParams = {},
): Promise<SpansListResponse> {
  const r = await checkOk(
    await fetch(`/api/test-runs/${testRunId}/spans${buildQuery(params)}`),
  );
  return r.json() as Promise<SpansListResponse>;
}

export async function getSpan(spanId: number): Promise<SpanDetail> {
  const r = await checkOk(await fetch(`/api/spans/${spanId}`));
  return r.json() as Promise<SpanDetail>;
}

export type SpanChildrenResponse = {
  parent_span_id: number;
  items: SpanSummary[];
};

export async function getSpanChildren(
  spanId: number,
  limit = 200,
): Promise<SpanChildrenResponse> {
  const r = await checkOk(
    await fetch(`/api/spans/${spanId}/children?limit=${limit}`),
  );
  return r.json() as Promise<SpanChildrenResponse>;
}
