/** REST client for flow draft and committed version APIs. */

const BASE = "";

export type FlowVersionMeta = {
  version: number;
  created_at: number;
  description: string | null;
  /** Snapshot display name at commit time; legacy field `flow_name` is migrated server-side. */
  display_name: string;
};

export type VersionListResponse = {
  flow_id: string;
  latest_version: number;
  has_draft: boolean;
  versions: FlowVersionMeta[];
};

const jsonHeaders = { "Content-Type": "application/json" };

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const text = await r.text().catch(() => `HTTP ${r.status}`);
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r;
}

export async function fetchVersionList(flowId: string): Promise<VersionListResponse> {
  const r = await checkOk(await fetch(`${BASE}/api/flows/${encodeURIComponent(flowId)}/versions`));
  return r.json() as Promise<VersionListResponse>;
}

export async function fetchVersion(flowId: string, versionNum: number): Promise<Record<string, unknown>> {
  const r = await checkOk(await fetch(`${BASE}/api/flows/${encodeURIComponent(flowId)}/versions/${versionNum}`));
  return r.json() as Promise<Record<string, unknown>>;
}

export async function fetchDraft(flowId: string): Promise<Record<string, unknown>> {
  const r = await checkOk(await fetch(`${BASE}/api/flows/${encodeURIComponent(flowId)}/draft`));
  return r.json() as Promise<Record<string, unknown>>;
}

export async function saveDraft(flowId: string, body: Record<string, unknown>): Promise<void> {
  await checkOk(
    await fetch(`${BASE}/api/flows/${encodeURIComponent(flowId)}/draft`, {
      method: "PUT",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  );
}

export async function commitVersion(
  flowId: string,
  opts: { description?: string; data?: Record<string, unknown> } = {},
): Promise<{ version: number }> {
  const r = await checkOk(
    await fetch(`${BASE}/api/flows/${encodeURIComponent(flowId)}/versions`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(opts),
    }),
  );
  return r.json() as Promise<{ version: number }>;
}
