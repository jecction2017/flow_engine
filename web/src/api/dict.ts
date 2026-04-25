/** Layered data dictionary API. */

export type DictLayer = "base" | "profile";

export type DictModuleInfo = {
  module_id: string;
  layer: DictLayer;
  path: string;
  profile?: string | null;
};

export type ResolvedModuleInfo = {
  module_id: string;
  base_path?: string | null;
  profile_path?: string | null;
  from_base: boolean;
  from_profile: boolean;
};

export type DictSummaryResponse = {
  dict_dir: string;
  profiles: string[];
  base_modules: DictModuleInfo[];
};

export type DictResolveResponse = {
  resolved_dictionary: Record<string, unknown>;
  resolved_profile: string;
  resolved_modules: ResolvedModuleInfo[];
  resolved_hash: string;
};

export type DictProfilesResponse = {
  profiles: string[];
};

export type DictModulesResponse = {
  layer: DictLayer;
  profile?: string | null;
  modules: DictModuleInfo[];
};

export type DictModuleResponse = {
  layer: DictLayer;
  profile?: string | null;
  module_id: string;
  yaml: string;
};

const jsonHeaders = { "Content-Type": "application/json" };

export async function fetchDictSummary(): Promise<DictSummaryResponse> {
  const r = await fetch("/api/dict");
  if (!r.ok) throw new Error(`dict: ${r.status}`);
  return r.json() as Promise<DictSummaryResponse>;
}

export async function fetchDictResolved(profile: string): Promise<DictResolveResponse> {
  const q = new URLSearchParams();
  q.set("profile", profile);
  const r = await fetch(`/api/dict/resolve?${q.toString()}`);
  if (!r.ok) throw new Error(`dict resolve: ${r.status}`);
  return r.json() as Promise<DictResolveResponse>;
}

export async function fetchDictProfiles(): Promise<DictProfilesResponse> {
  const r = await fetch("/api/dict/profiles");
  if (!r.ok) throw new Error(`dict profiles: ${r.status}`);
  return r.json() as Promise<DictProfilesResponse>;
}

export async function createDictProfile(profile: string): Promise<void> {
  const r = await fetch("/api/dict/profiles", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ profile }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `create profile: ${r.status}`);
  }
}

export async function fetchDictModules(layer: DictLayer, profile?: string): Promise<DictModulesResponse> {
  const q = new URLSearchParams();
  q.set("layer", layer);
  if (profile) q.set("profile", profile);
  const r = await fetch(`/api/dict/modules?${q.toString()}`);
  if (!r.ok) throw new Error(`dict modules: ${r.status}`);
  return r.json() as Promise<DictModulesResponse>;
}

export async function fetchDictModule(layer: DictLayer, moduleId: string, profile?: string): Promise<DictModuleResponse> {
  const q = new URLSearchParams();
  q.set("layer", layer);
  q.set("module_id", moduleId);
  if (profile) q.set("profile", profile);
  const r = await fetch(`/api/dict/module?${q.toString()}`);
  if (!r.ok) throw new Error(`dict module: ${r.status}`);
  return r.json() as Promise<DictModuleResponse>;
}

export async function saveDictModule(
  layer: DictLayer,
  moduleId: string,
  yaml: string,
  profile?: string,
): Promise<void> {
  const q = new URLSearchParams();
  q.set("layer", layer);
  q.set("module_id", moduleId);
  if (profile) q.set("profile", profile);
  const r = await fetch(`/api/dict/module?${q.toString()}`, {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify({ yaml }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `save module: ${r.status}`);
  }
}

export async function deleteDictModule(layer: DictLayer, moduleId: string, profile?: string): Promise<void> {
  const q = new URLSearchParams();
  q.set("layer", layer);
  q.set("module_id", moduleId);
  if (profile) q.set("profile", profile);
  const r = await fetch(`/api/dict/module?${q.toString()}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete module: ${r.status}`);
}
