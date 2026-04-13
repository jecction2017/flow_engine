/** Lookup tables API (`lookup/{namespace}.json`). */

export type LookupTable = {
  fields: string[];
  rows: Array<Record<string, unknown>>;
};

export type LookupListResponse = {
  lookup_dir: string;
  namespaces: string[];
};

const jsonHeaders = { "Content-Type": "application/json" };

export async function fetchLookupList(): Promise<LookupListResponse> {
  const r = await fetch("/api/lookups");
  if (!r.ok) throw new Error(`lookups: ${r.status}`);
  return r.json() as Promise<LookupListResponse>;
}

export async function fetchLookupTable(namespace: string): Promise<LookupTable> {
  const r = await fetch(`/api/lookups/${encodeURIComponent(namespace)}`);
  if (!r.ok) throw new Error(`lookup ${namespace}: ${r.status}`);
  return r.json() as Promise<LookupTable>;
}

export async function saveLookupTable(namespace: string, table: LookupTable): Promise<void> {
  const r = await fetch(`/api/lookups/${encodeURIComponent(namespace)}`, {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify(table),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `save lookup ${namespace}: ${r.status}`);
  }
}

export async function deleteLookupTable(namespace: string): Promise<void> {
  const r = await fetch(`/api/lookups/${encodeURIComponent(namespace)}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete ${namespace}: ${r.status}`);
}

export async function importLookupFile(
  namespace: string,
  file: File,
  mode: "replace" | "append",
  format: "auto" | "json" | "csv" | "xlsx",
): Promise<{ imported: number; mode: string }> {
  const fd = new FormData();
  fd.set("file", file);
  fd.set("mode", mode);
  fd.set("format", format);
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
