/** Data dictionary API (`dictionary.yaml`). */

export type DictDocumentResponse = {
  dict_dir: string;
  tree: Record<string, unknown>;
  yaml: string;
};

export type DictSubtreeResponse = {
  path: string;
  yaml: string;
};

const jsonHeaders = { "Content-Type": "application/json" };

export async function fetchDictDocument(): Promise<DictDocumentResponse> {
  const r = await fetch("/api/dict");
  if (!r.ok) throw new Error(`dict: ${r.status}`);
  return r.json() as Promise<DictDocumentResponse>;
}

export async function fetchDictSubtree(path: string): Promise<DictSubtreeResponse> {
  const q = new URLSearchParams();
  if (path) q.set("path", path);
  const r = await fetch(`/api/dict/subtree?${q.toString()}`);
  if (!r.ok) throw new Error(`dict subtree: ${r.status}`);
  return r.json() as Promise<DictSubtreeResponse>;
}

export async function saveDictSubtree(path: string, yaml: string): Promise<void> {
  const q = new URLSearchParams();
  if (path) q.set("path", path);
  const r = await fetch(`/api/dict/subtree?${q.toString()}`, {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify({ yaml }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `save subtree: ${r.status}`);
  }
}

export async function saveDictFull(yaml: string): Promise<void> {
  const r = await fetch("/api/dict", {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify({ content: yaml }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `save dict: ${r.status}`);
  }
}

export async function deleteDictSubtree(path: string): Promise<void> {
  const q = new URLSearchParams();
  if (path) q.set("path", path);
  const r = await fetch(`/api/dict/subtree?${q.toString()}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete subtree: ${r.status}`);
}
