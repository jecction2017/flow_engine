/** Structured runtime failure (who / when / what / how) from API ``failure_detail``. */

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

export function hasFailureDetail(
  detail: FailureDetail | null | undefined,
): detail is FailureDetail {
  if (!detail || typeof detail !== "object") return false;
  return Boolean(
    detail.category ||
      detail.category_label ||
      detail.summary ||
      detail.node_id,
  );
}

export function formatFailureDetailRows(
  detail: FailureDetail,
): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  if (detail.category_label || detail.category) {
    rows.push({
      label: "分类",
      value: String(detail.category_label || detail.category),
    });
  }
  if (detail.occurred_at) {
    rows.push({ label: "时间", value: formatOccurredAt(detail.occurred_at) });
  }
  const who: string[] = [];
  if (detail.node_id) who.push(`节点ID: ${detail.node_id}`);
  if (detail.node_name && detail.node_name !== detail.node_id) {
    who.push(`显示名: ${detail.node_name}`);
  }
  if (who.length) rows.push({ label: "节点", value: who.join(" · ") });
  if (detail.phase_label || detail.phase) {
    rows.push({
      label: "阶段",
      value: String(detail.phase_label || detail.phase),
    });
  }
  if (detail.summary) rows.push({ label: "摘要", value: detail.summary });
  if (detail.exception_type) {
    let loc = "";
    if (detail.source_file && detail.line != null) {
      loc =
        detail.column != null
          ? ` (${detail.source_file}:${detail.line}:${detail.column})`
          : ` (${detail.source_file}:${detail.line})`;
    }
    const msg = detail.exception_message ? `: ${detail.exception_message}` : "";
    rows.push({ label: "异常", value: `${detail.exception_type}${loc}${msg}` });
  }
  const ctx = detail.context;
  if (ctx && typeof ctx === "object" && Object.keys(ctx).length > 0) {
    const lines = Object.entries(ctx)
      .filter(([, v]) => v != null)
      .map(([k, v]) =>
        Array.isArray(v) ? `${k}: ${v.map(String).join(", ")}` : `${k}: ${String(v)}`,
      );
    if (lines.length) rows.push({ label: "上下文", value: lines.join("\n") });
  }
  return rows;
}

export function formatOccurredAt(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

/** One-line preview under the card title (collapsed state). */
export function failurePreviewText(opts: {
  failureDetail?: FailureDetail | null;
  error?: string | null;
  maxLen?: number;
}): string {
  const maxLen = opts.maxLen ?? 96;
  const d = opts.failureDetail;
  if (hasFailureDetail(d)) {
    const s = (d.summary ?? d.exception_message ?? "").trim();
    return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s;
  }
  const err = (opts.error ?? "").trim();
  if (!err) return "";
  const summaryMatch = err.match(/【摘要】([^\n]+)/);
  if (summaryMatch) {
    const s = summaryMatch[1].trim();
    return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s;
  }
  const first = err.split(/\r?\n/)[0]?.trim() ?? "";
  return first.length > maxLen ? `${first.slice(0, maxLen)}…` : first;
}

export function failureDetailFromUnknown(
  raw: unknown,
): FailureDetail | null {
  if (!raw || typeof raw !== "object") return null;
  return hasFailureDetail(raw as FailureDetail) ? (raw as FailureDetail) : null;
}
