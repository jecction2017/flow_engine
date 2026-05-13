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
  /** Number of log entries stored on the span row (when provided by API). */
  log_count?: number;
};

export type SpanDetail = SpanSummary & {
  child_spans: SpanChildSummary[] | null;
  logs: SpanLogEntry[] | null;
  attributes: Record<string, unknown> | null;
};

/** Truncation flags surfaced by the backend when result-size caps kick in.
 *
 * The backend bounds (a) the filter-hit set before tree expansion and
 * (b) the spans returned in a single page after expansion. Either cap
 * exceeded raises a flag here so the UI can prompt for filter refinement
 * instead of silently dropping data. */
export type SpansTruncated = {
  /** Filter hits exceeded the matched-set cap (~10K). Some matches were
   *  not considered for tree expansion in this page. */
  matched: boolean;
  /** Returned forest exceeded the per-page span cap (~5K). Trailing root
   *  subtrees of this page were dropped; subsequent pages continue. */
  returned: boolean;
};

export type SpansListResponse = {
  /** Flat span rows. Invariant: every ``parent_span_id`` is either null
   *  or refers to another span in this same ``items`` array — the forest
   *  is always well-formed; the frontend never needs orphan fallback. */
  items: SpanSummary[];
  offset: number;
  limit: number;
  /** Count of root subtrees in the (filter-expanded) forest. This is the
   *  pagination basis: total pages = ceil(total_roots / limit). */
  total_roots: number;
  /** Pre-expansion filter-hit count. ``null`` when no filter was applied
   *  (in which case ``total_roots`` is the natural "how many things"). */
  total_matched: number | null;
  /** ``items.length`` — convenience for "spans on this page after
   *  ancestor / descendant expansion". */
  total_returned: number;
  /** Backwards-compatible alias: equals ``total_matched`` when filtering,
   *  else ``total_roots``. New code should prefer the explicit fields. */
  total: number;
  truncated: SpansTruncated;
  /** Distinct node_ids of the run — populates the filter dropdown. */
  node_ids: string[];
  /** Echo of the request flag, so the UI can keep its toggle in sync. */
  include_descendants: boolean;
};

export type ListSpansParams = {
  node_id?: string;
  node_id_contains?: string;
  status?: SpanStatus | string;
  scope_key?: string;
  started_after?: string;
  started_before?: string;
  duration_min_ms?: number;
  duration_max_ms?: number;
  log_level?: string;
  /** When true, matched parent spans also pull down their full subtree
   *  (in addition to the always-on ancestor chain). Useful for
   *  "filtered by parent node_id; show me everything under it". */
  include_descendants?: boolean;
  offset?: number;
  limit?: number;
};

function buildQuery(params: ListSpansParams): string {
  const qs = new URLSearchParams();
  if (params.node_id) qs.set("node_id", params.node_id);
  if (params.node_id_contains) qs.set("node_id_contains", params.node_id_contains);
  if (params.status) qs.set("status", String(params.status));
  if (params.scope_key) qs.set("scope_key", params.scope_key);
  if (params.started_after) qs.set("started_after", params.started_after);
  if (params.started_before) qs.set("started_before", params.started_before);
  if (params.duration_min_ms != null) qs.set("duration_min_ms", String(params.duration_min_ms));
  if (params.duration_max_ms != null) qs.set("duration_max_ms", String(params.duration_max_ms));
  if (params.log_level) qs.set("log_level", params.log_level);
  if (params.include_descendants) qs.set("include_descendants", "true");
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
