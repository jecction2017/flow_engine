/** REST client for Python `/api` (Vite dev proxy → http://127.0.0.1:8000). */

import type { FlowDocument } from "@/types/flow";

export type FlowListItem = {
  id: string;
  name: string;
  path: string;
  updated_at: number | null;
};

export type FlowListResponse = {
  flows: FlowListItem[];
  flows_dir: string;
};

const jsonHeaders = { "Content-Type": "application/json" };

export async function fetchFlowList(): Promise<FlowListResponse> {
  const r = await fetch("/api/flows");
  if (!r.ok) throw new Error(`flows: ${r.status}`);
  return r.json() as Promise<FlowListResponse>;
}

export async function fetchFlowRaw(flowId: string): Promise<Record<string, unknown>> {
  const r = await fetch(`/api/flows/${encodeURIComponent(flowId)}`);
  if (!r.ok) throw new Error(`get ${flowId}: ${r.status}`);
  return r.json() as Promise<Record<string, unknown>>;
}

export async function saveFlow(flowId: string, body: FlowDocument): Promise<void> {
  const r = await fetch(`/api/flows/${encodeURIComponent(flowId)}`, {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `save ${flowId}: ${r.status}`);
  }
}

export async function createFlow(id: string, name?: string): Promise<void> {
  const r = await fetch("/api/flows", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ id, name: name ?? id }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `create: ${r.status}`);
  }
}

export async function deleteFlow(flowId: string): Promise<void> {
  const r = await fetch(`/api/flows/${encodeURIComponent(flowId)}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete ${flowId}: ${r.status}`);
}
