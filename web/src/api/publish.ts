/** REST client for versioning, publish, and instance management APIs. */

const BASE = "";

export type PublishStatus = "unpublished" | "publishing" | "running" | "stopped" | "failed";

export type ChannelState = {
  version: number | null;
  status: PublishStatus;
  published_at: number | null;
  stopped_at: number | null;
};

export type FlowPublishState = {
  flow_id: string;
  production: ChannelState;
  gray: ChannelState;
};

export type FlowInstance = {
  instance_id: string;
  flow_id: string;
  version: number;
  channel: string;
  started_at: number;
  last_heartbeat: number;
  status: "running" | "stopped" | "failed";
  pid: number | null;
  host: string | null;
};

export type FlowVersionMeta = {
  version: number;
  created_at: number;
  description: string | null;
  flow_name: string;
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

// ---------------------------------------------------------------------------
// Version management
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Publish management
// ---------------------------------------------------------------------------

export async function fetchPublishState(flowId: string): Promise<FlowPublishState> {
  const r = await checkOk(await fetch(`${BASE}/api/flows/${encodeURIComponent(flowId)}/publish`));
  return r.json() as Promise<FlowPublishState>;
}

export async function publishVersion(
  flowId: string,
  version: number,
  channel: "production" | "gray",
): Promise<void> {
  await checkOk(
    await fetch(`${BASE}/api/flows/${encodeURIComponent(flowId)}/publish`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ version, channel }),
    }),
  );
}

export async function stopPublish(flowId: string, channel: "production" | "gray"): Promise<void> {
  await checkOk(
    await fetch(`${BASE}/api/flows/${encodeURIComponent(flowId)}/publish/${channel}`, {
      method: "DELETE",
    }),
  );
}

// ---------------------------------------------------------------------------
// Instance management
// ---------------------------------------------------------------------------

export async function fetchInstances(flowId: string): Promise<FlowInstance[]> {
  const r = await checkOk(await fetch(`${BASE}/api/flows/${encodeURIComponent(flowId)}/instances`));
  const data = (await r.json()) as { instances: FlowInstance[] };
  return data.instances;
}

// ---------------------------------------------------------------------------
// SSE helper
// ---------------------------------------------------------------------------

export type SseEvent = {
  type: string;
  flow_id: string;
  data?: Record<string, unknown>;
  publish?: FlowPublishState;
  instances?: FlowInstance[];
  ts: number;
};

export function openEventStream(
  flowId: string,
  onEvent: (e: SseEvent) => void,
): () => void {
  const es = new EventSource(`${BASE}/api/flows/${encodeURIComponent(flowId)}/events`);
  es.onmessage = (ev) => {
    try {
      const parsed = JSON.parse(ev.data as string) as SseEvent;
      onEvent(parsed);
    } catch {
      // ignore malformed events
    }
  };
  return () => es.close();
}
