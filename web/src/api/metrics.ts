/** REST client for `/api/deploy-runs/{id}/metrics*` (aggregate counters).
 *
 * Metrics are always-on rollups: every span emission ticks an in-memory
 * 5-minute bucket; the bucket is UPSERTed to `fe_node_metric` on a
 * timer. They are the right answer for "what does the last hour look
 * like?" — Spans are the right answer for "what happened to alert X?".
 *
 * Only deploy runs (subscription / once / cron) write metrics. Test runs
 * deliberately skip the metric pipeline; their span counters alone are
 * enough for batch comparison.
 */

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const text = await r.text().catch(() => `HTTP ${r.status}`);
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r;
}

export type MetricBucket = {
  bucket_at: string;
  span_count: number;
  success_count: number;
  failed_count: number;
  skipped_count: number;
  avg_ms: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  max_ms: number | null;
  min_ms: number | null;
  success_rate: number | null;
};

/** `node_id` filter present → one node's buckets. Otherwise grouped. */
export type MetricBucketsResponse =
  | {
      deploy_run_id: number;
      node_id: string;
      buckets: MetricBucket[];
    }
  | {
      deploy_run_id: number;
      nodes: Array<{ node_id: string; buckets: MetricBucket[] }>;
    };

export type NodeMetricSummary = {
  node_id: string;
  window_minutes: number;
  span_count: number;
  success_count: number;
  failed_count: number;
  skipped_count: number;
  success_rate: number | null;
  avg_ms: number | null;
  throughput_per_s: number;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  max_ms: number | null;
};

/** Single-node response (filtered by `node_id`) is just one summary. */
export type MetricsSummaryResponse =
  | NodeMetricSummary
  | {
      deploy_run_id: number;
      window_minutes: number;
      nodes: NodeMetricSummary[];
    };

export type QueryMetricBucketsParams = {
  node_id?: string;
  /** ISO 8601, inclusive lower bound. */
  from?: string;
  /** ISO 8601, exclusive upper bound. */
  to?: string;
};

export async function queryMetricBuckets(
  deployRunId: number,
  params: QueryMetricBucketsParams = {},
): Promise<MetricBucketsResponse> {
  const qs = new URLSearchParams();
  if (params.node_id) qs.set("node_id", params.node_id);
  if (params.from) qs.set("from", params.from);
  if (params.to) qs.set("to", params.to);
  const q = qs.toString();
  const r = await checkOk(
    await fetch(`/api/deploy-runs/${deployRunId}/metrics${q ? `?${q}` : ""}`),
  );
  return r.json() as Promise<MetricBucketsResponse>;
}

export type QuerySummaryParams = {
  node_id?: string;
  window_minutes?: number;
};

export async function queryMetricsSummary(
  deployRunId: number,
  params: QuerySummaryParams = {},
): Promise<MetricsSummaryResponse> {
  const qs = new URLSearchParams();
  if (params.node_id) qs.set("node_id", params.node_id);
  if (params.window_minutes != null) {
    qs.set("window_minutes", String(params.window_minutes));
  }
  const q = qs.toString();
  const r = await checkOk(
    await fetch(
      `/api/deploy-runs/${deployRunId}/metrics/summary${q ? `?${q}` : ""}`,
    ),
  );
  return r.json() as Promise<MetricsSummaryResponse>;
}

/** Helper to handle the union response shape ergonomically. */
export function isMultiNodeSummary(
  resp: MetricsSummaryResponse,
): resp is { deploy_run_id: number; window_minutes: number; nodes: NodeMetricSummary[] } {
  return Array.isArray((resp as { nodes?: unknown }).nodes);
}

export function isMultiNodeBuckets(
  resp: MetricBucketsResponse,
): resp is { deploy_run_id: number; nodes: Array<{ node_id: string; buckets: MetricBucket[] }> } {
  return Array.isArray((resp as { nodes?: unknown }).nodes);
}
