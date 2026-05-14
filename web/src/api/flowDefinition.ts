/** Validate a flow definition JSON (no persistence). Mirrors ``POST /api/flow-definition/validate``. */

import type { FlowDocument } from "@/types/flow";

const jsonHeaders = { "Content-Type": "application/json" };

export async function validateFlowDefinition(
  body: Record<string, unknown>,
): Promise<FlowDocument> {
  const r = await fetch("/api/flow-definition/validate", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = `校验失败 (${r.status})`;
    try {
      const j = (await r.json()) as { detail?: unknown };
      const d = j?.detail;
      if (typeof d === "string") msg = d;
      else if (Array.isArray(d) && d.length && typeof d[0] === "object" && d[0] !== null && "msg" in d[0]) {
        msg = String((d[0] as { msg?: string }).msg ?? msg);
      }
    } catch {
      const t = await r.text().catch(() => "");
      if (t) msg = t;
    }
    throw new Error(msg);
  }
  const out = (await r.json()) as { ok?: boolean; definition?: unknown };
  if (!out.definition || typeof out.definition !== "object") {
    throw new Error("校验响应无效");
  }
  return out.definition as FlowDocument;
}
