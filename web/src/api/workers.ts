/** REST client for `/api/workers` (runner worker 状态). */

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const text = await r.text().catch(() => `HTTP ${r.status}`);
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r;
}

export type WorkerStatus = "active" | "idle" | "dead" | string;

export type Worker = {
  worker_id: string;
  host: string | null;
  pid: number | null;
  status: WorkerStatus;
  last_heartbeat: string | null;
  capabilities: Record<string, unknown> | null;
  assigned_deployments: number[];
};

export async function listWorkers(): Promise<{ workers: Worker[] }> {
  const r = await checkOk(await fetch("/api/workers"));
  return r.json() as Promise<{ workers: Worker[] }>;
}
