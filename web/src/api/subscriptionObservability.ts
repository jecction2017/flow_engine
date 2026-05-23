/** Subscription deployment observability (message ledger + run aggregates). */

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const text = await r.text().catch(() => `HTTP ${r.status}`);
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r;
}

export type SubscriptionMessageRow = {
  id: number;
  deployment_id?: number;
  position_key: string;
  topic: string;
  partition: number;
  offset: number;
  status: string;
  deploy_run_id: number | null;
  error: string | null;
  created_at?: string | null;
  updated_at: string | null;
};

export type SubscriptionSummary = {
  deployment_id: number;
  consumer_id: string | null;
  messages: {
    total: number;
    by_status: { processing: number; completed: number; failed: number };
    last_updated_at: string | null;
  };
  runs: {
    total: number;
    by_status: Record<string, number>;
  };
  recent_failed_messages: SubscriptionMessageRow[];
};

export type SubscriptionMessagesListResponse = {
  deployment_id: number;
  total: number;
  offset: number;
  limit: number;
  messages: SubscriptionMessageRow[];
};

export async function getSubscriptionSummary(
  deploymentId: number,
): Promise<SubscriptionSummary> {
  const r = await checkOk(
    await fetch(`/api/deployments/${deploymentId}/subscription/summary`),
  );
  return r.json() as Promise<SubscriptionSummary>;
}

export type ListSubscriptionMessagesParams = {
  status?: string;
  offset?: number;
  limit?: number;
};

export type RecentFailedSubscriptionMessagesResponse = {
  since: string;
  offset: number;
  limit: number;
  total: number;
  messages: SubscriptionMessageRow[];
};

export async function listRecentFailedSubscriptionMessages(
  params: { hours?: number; offset?: number; limit?: number } = {},
): Promise<RecentFailedSubscriptionMessagesResponse> {
  const qs = new URLSearchParams();
  if (params.hours != null) qs.set("hours", String(params.hours));
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.limit != null) qs.set("limit", String(params.limit));
  const q = qs.toString();
  const r = await checkOk(
    await fetch(`/api/subscription/recent-failed-messages${q ? `?${q}` : ""}`),
  );
  return r.json() as Promise<RecentFailedSubscriptionMessagesResponse>;
}

export async function listSubscriptionMessages(
  deploymentId: number,
  params: ListSubscriptionMessagesParams = {},
): Promise<SubscriptionMessagesListResponse> {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.limit != null) qs.set("limit", String(params.limit));
  const q = qs.toString();
  const r = await checkOk(
    await fetch(
      `/api/deployments/${deploymentId}/subscription/messages${q ? `?${q}` : ""}`,
    ),
  );
  return r.json() as Promise<SubscriptionMessagesListResponse>;
}
