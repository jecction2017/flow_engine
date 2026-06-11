/** REST client for `/api/guide` (Markdown help under docs/guide). */

export type GuideTreeDocNode = {
  kind: "doc";
  name: string;
  title: string;
  path: string;
  order?: number;
};

export type GuideTreeDirNode = {
  kind: "dir";
  name: string;
  title: string;
  path: string;
  order?: number;
  children: GuideTreeNode[];
};

export type GuideTreeNode = GuideTreeDocNode | GuideTreeDirNode;

export type GuideTreeResponse = {
  root: string;
  children: GuideTreeNode[];
};

export type GuideDocResponse = {
  path: string;
  title: string;
  content: string;
};

export type GuideSearchHit = {
  path: string;
  title: string;
  breadcrumb: string;
  snippet: string;
};

export type GuideSearchResponse = {
  query: string;
  results: GuideSearchHit[];
};

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(text || `guide: ${r.status}`);
  }
  return r;
}

export async function fetchGuideTree(): Promise<GuideTreeResponse> {
  const r = await checkOk(await fetch("/api/guide/tree"));
  return r.json() as Promise<GuideTreeResponse>;
}

export async function fetchGuideDoc(path: string): Promise<GuideDocResponse> {
  const q = new URLSearchParams({ path });
  const r = await checkOk(await fetch(`/api/guide/doc?${q}`));
  return r.json() as Promise<GuideDocResponse>;
}

export async function searchGuideDocs(query: string, limit = 30): Promise<GuideSearchResponse> {
  const q = new URLSearchParams({ q: query, limit: String(limit) });
  const r = await checkOk(await fetch(`/api/guide/search?${q}`));
  return r.json() as Promise<GuideSearchResponse>;
}
