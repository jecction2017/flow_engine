/** REST client for `/api/deployments` (runner deployment管理). */

const jsonHeaders = { "Content-Type": "application/json" };

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const text = await r.text().catch(() => `HTTP ${r.status}`);
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r;
}

export type RunMode = "debug" | "shadow" | "production";
export type ScheduleType = "once" | "cron" | "resident";
export type DeploymentStatus =
  | "pending"
  | "running"
  | "stopping"
  | "stopped"
  | "failed"
  | string;

export type CapabilityAction = "allow" | "suppress" | "redirect";

export type CapabilityRule = {
  builtin_category?: string | null;
  builtin_name?: string | null;
  action: CapabilityAction;
  redirect_params?: Record<string, unknown>;
};

export type WorkerPolicy = {
  type?: string;
  min_workers?: number;
  max_restarts?: number;
  restart_backoff_s?: number;
  [k: string]: unknown;
};

export type ScheduleConfig = {
  cron_expr?: string;
  [k: string]: unknown;
};

export type Deployment = {
  id: number;
  flow_code: string;
  ver_no: number;
  mode: RunMode | string;
  schedule_type: ScheduleType | string;
  schedule_config: ScheduleConfig;
  worker_policy: WorkerPolicy;
  capability_policy: CapabilityRule[];
  status: DeploymentStatus;
  env_profile_code: string;
  parent_deployment_id: number | null;
  created_at: string | null;
  updated_at: string | null;
};

export type Assignment = {
  id: number;
  worker_id: string;
  role: string;
  lease_expires_at: string | null;
};

export type DeploymentDetail = Deployment & { assignments: Assignment[] };

export type CreateDeploymentBody = {
  flow_code: string;
  ver_no: number;
  mode: RunMode;
  schedule_type: ScheduleType;
  schedule_config?: ScheduleConfig;
  worker_policy?: WorkerPolicy;
  capability_policy?: CapabilityRule[];
  env_profile_code?: string;
};

export type ListDeploymentsParams = {
  flow_code?: string;
  status?: string;
  mode?: string;
};

export async function listDeployments(
  params: ListDeploymentsParams = {},
): Promise<{ deployments: Deployment[] }> {
  const qs = new URLSearchParams();
  if (params.flow_code) qs.set("flow_code", params.flow_code);
  if (params.status) qs.set("status", params.status);
  if (params.mode) qs.set("mode", params.mode);
  const q = qs.toString();
  const r = await checkOk(await fetch(`/api/deployments${q ? `?${q}` : ""}`));
  return r.json() as Promise<{ deployments: Deployment[] }>;
}

export async function getDeployment(id: number): Promise<DeploymentDetail> {
  const r = await checkOk(await fetch(`/api/deployments/${id}`));
  return r.json() as Promise<DeploymentDetail>;
}

export async function createDeployment(
  body: CreateDeploymentBody,
): Promise<Deployment> {
  const r = await checkOk(
    await fetch("/api/deployments", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  );
  return r.json() as Promise<Deployment>;
}

export async function patchDeployment(
  id: number,
  status: "stopping" | "pending",
): Promise<{ id: number; status: string }> {
  const r = await checkOk(
    await fetch(`/api/deployments/${id}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify({ status }),
    }),
  );
  return r.json() as Promise<{ id: number; status: string }>;
}

export async function deleteDeployment(id: number): Promise<void> {
  await checkOk(await fetch(`/api/deployments/${id}`, { method: "DELETE" }));
}
