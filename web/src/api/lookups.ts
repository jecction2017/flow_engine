/** Lookup tables API (`lookup/{namespace}.json`). */

export type LookupTable = {
  schema?: Record<string, unknown>;
  rows: Array<Record<string, unknown>>;
};

export type LookupListResponse = {
  lookup_dir: string;
  profile?: string;
  namespaces: string[];
};

export type LookupQueryResponse = {
  namespace: string;
  profile?: string;
  filter: Record<string, unknown> | string;
  schema?: Record<string, unknown>;
  rows: Array<Record<string, unknown>>;
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
};

const jsonHeaders = { "Content-Type": "application/json" };

export async function fetchLookupList(profile?: string): Promise<LookupListResponse> {
  const q = new URLSearchParams();
  if (profile) q.set("profile", profile);
  const r = await fetch(`/api/lookups?${q.toString()}`);
  if (!r.ok) throw new Error(`lookups: ${r.status}`);
  return r.json() as Promise<LookupListResponse>;
}

export async function fetchLookupTable(namespace: string, profile?: string): Promise<LookupTable> {
  const q = new URLSearchParams();
  if (profile) q.set("profile", profile);
  const r = await fetch(`/api/lookups/${encodeURIComponent(namespace)}?${q.toString()}`);
  if (!r.ok) throw new Error(`lookup ${namespace}: ${r.status}`);
  return r.json() as Promise<LookupTable>;
}

export async function saveLookupTable(namespace: string, table: LookupTable, profile?: string): Promise<void> {
  const q = new URLSearchParams();
  if (profile) q.set("profile", profile);
  const r = await fetch(`/api/lookups/${encodeURIComponent(namespace)}?${q.toString()}`, {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify(table),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `save lookup ${namespace}: ${r.status}`);
  }
}

export async function saveLookupSchema(namespace: string, schema: Record<string, unknown>, profile?: string): Promise<void> {
  const q = new URLSearchParams();
  if (profile) q.set("profile", profile);
  const r = await fetch(`/api/lookups/${encodeURIComponent(namespace)}/schema?${q.toString()}`, {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify({ schema }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `save lookup schema ${namespace}: ${r.status}`);
  }
}

export async function deleteLookupTable(namespace: string, profile?: string): Promise<void> {
  const q = new URLSearchParams();
  if (profile) q.set("profile", profile);
  const r = await fetch(`/api/lookups/${encodeURIComponent(namespace)}?${q.toString()}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete ${namespace}: ${r.status}`);
}

export async function importLookupFile(
  namespace: string,
  file: File,
  mode: "replace" | "append",
  format: "auto" | "json" | "csv" | "xlsx",
  profile?: string,
): Promise<{ imported: number; mode: string }> {
  const fd = new FormData();
  fd.set("file", file);
  fd.set("mode", mode);
  fd.set("format", format);
  if (profile) fd.set("profile", profile);
  const r = await fetch(`/api/lookups/${encodeURIComponent(namespace)}/import`, {
    method: "POST",
    body: fd,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `import: ${r.status}`);
  }
  return r.json() as Promise<{ imported: number; mode: string }>;
}

export async function queryLookupTable(
  namespace: string,
  options: {
    profile?: string;
    filter?: Record<string, unknown> | string;
    offset?: number;
    limit?: number;
    signal?: AbortSignal;
  } = {},
): Promise<LookupQueryResponse> {
  const q = new URLSearchParams();
  if (options.profile) q.set("profile", options.profile);
  const f = options.filter ?? "";
  q.set("filter", typeof f === "string" ? f : JSON.stringify(f));
  q.set("offset", String(options.offset ?? 0));
  q.set("limit", String(options.limit ?? 50));
  const r = await fetch(`/api/lookups/${encodeURIComponent(namespace)}/query?${q.toString()}`, {
    signal: options.signal,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `query lookup ${namespace}: ${r.status}`);
  }
  return r.json() as Promise<LookupQueryResponse>;
}

export async function deleteLookupRows(
  namespace: string,
  rows: Array<Record<string, unknown>>,
  profile?: string,
): Promise<{ ok: boolean; removed: number; remaining: number }> {
  const q = new URLSearchParams();
  if (profile) q.set("profile", profile);
  const r = await fetch(`/api/lookups/${encodeURIComponent(namespace)}/rows/delete?${q.toString()}`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ rows }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `delete lookup rows ${namespace}: ${r.status}`);
  }
  return r.json() as Promise<{ ok: boolean; removed: number; remaining: number }>;
}

export async function deleteLookupRowsByFilter(
  namespace: string,
  filter: Record<string, unknown> | string,
  profile?: string,
): Promise<{ ok: boolean; removed: number; remaining: number }> {
  const q = new URLSearchParams();
  if (profile) q.set("profile", profile);
  const r = await fetch(`/api/lookups/${encodeURIComponent(namespace)}/rows/delete_by_filter?${q.toString()}`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ filter }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `delete lookup rows by filter ${namespace}: ${r.status}`);
  }
  return r.json() as Promise<{ ok: boolean; removed: number; remaining: number }>;
}
