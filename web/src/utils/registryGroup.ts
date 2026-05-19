/** Group registry entries by module (from id or path fallback). */

import type { RegistryInternalModule, RegistryPythonFn } from "@/api/starlark";

const PYTHON_ID_RE = /^python:\/\/([^/]+)\//i;

export function pythonModuleKey(fn: RegistryPythonFn): string {
  const m = fn.id.match(PYTHON_ID_RE);
  if (m?.[1]) return m[1].toLowerCase();
  return (fn.category || "other").toLowerCase();
}

export type PythonModuleGroup = {
  module: string;
  functions: RegistryPythonFn[];
};

export function groupPythonFunctionsByModule(functions: RegistryPythonFn[]): PythonModuleGroup[] {
  const map = new Map<string, RegistryPythonFn[]>();
  for (const f of functions) {
    const key = pythonModuleKey(f);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(f);
  }
  const out: PythonModuleGroup[] = [];
  for (const [module, fns] of map) {
    fns.sort((a, b) => a.starlark_name.localeCompare(b.starlark_name));
    out.push({ module, functions: fns });
  }
  out.sort((a, b) => a.module.localeCompare(b.module));
  return out;
}

/** Filter groups by query (module name, function name, summary). */
export function filterPythonModuleGroups(groups: PythonModuleGroup[], query: string): PythonModuleGroup[] {
  const q = query.trim().toLowerCase();
  if (!q) return groups;
  return groups
    .map((g) => {
      const modMatch = g.module.includes(q);
      const fns = g.functions.filter(
        (f) =>
          modMatch ||
          f.starlark_name.toLowerCase().includes(q) ||
          f.summary.toLowerCase().includes(q) ||
          f.id.toLowerCase().includes(q),
      );
      return { module: g.module, functions: fns };
    })
    .filter((g) => g.functions.length > 0);
}

export function formatPythonExampleCall(fn: RegistryPythonFn): string {
  const args = fn.signature.map((p) => {
    if (p.required) return p.name;
    return `${p.name}=...`;
  });
  return `${fn.starlark_name}(${args.join(", ")})`;
}

const INTERNAL_ID_RE = /^internal:\/\/([^/]+)\//i;

export function internalModuleKey(m: RegistryInternalModule): string {
  const m1 = m.uri.match(INTERNAL_ID_RE);
  if (m1?.[1]) return m1[1].toLowerCase();
  const m2 = m.path.replace(/^\/+/, "").match(/^internal\/([^/]+)\//i);
  return m2?.[1]?.toLowerCase() ?? "other";
}

export function internalScriptName(m: RegistryInternalModule): string {
  const m1 = m.uri.match(/^internal:\/\/[^/]+\/(.+)$/i);
  if (m1?.[1]) return m1[1];
  const parts = m.path.replace(/^\/+/, "").split("/");
  return parts[parts.length - 1] ?? m.uri;
}

export type InternalModuleGroup = {
  module: string;
  scripts: RegistryInternalModule[];
};

export function groupInternalModulesByModule(modules: RegistryInternalModule[]): InternalModuleGroup[] {
  const map = new Map<string, RegistryInternalModule[]>();
  for (const m of modules) {
    const key = internalModuleKey(m);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(m);
  }
  const out: InternalModuleGroup[] = [];
  for (const [module, scripts] of map) {
    scripts.sort((a, b) => internalScriptName(a).localeCompare(internalScriptName(b)));
    out.push({ module, scripts });
  }
  out.sort((a, b) => a.module.localeCompare(b.module));
  return out;
}

/** Filter internal groups by module, script name, summary, exports, uri. */
export function filterInternalModuleGroups(
  groups: InternalModuleGroup[],
  query: string,
): InternalModuleGroup[] {
  const q = query.trim().toLowerCase();
  if (!q) return groups;
  return groups
    .map((g) => {
      const modMatch = g.module.includes(q);
      const scripts = g.scripts.filter(
        (s) =>
          modMatch ||
          internalScriptName(s).toLowerCase().includes(q) ||
          s.summary.toLowerCase().includes(q) ||
          s.uri.toLowerCase().includes(q) ||
          s.exports.some((ex) => ex.toLowerCase().includes(q)),
      );
      return { module: g.module, scripts };
    })
    .filter((g) => g.scripts.length > 0);
}

const USER_PATH_RE = /^([^/]+)\/(.+)$/;

export function userScriptModuleKey(path: string): string {
  const m = path.match(USER_PATH_RE);
  return m?.[1] ?? "";
}

export function userScriptFileName(path: string): string {
  const m = path.match(USER_PATH_RE);
  return m?.[2] ?? path;
}

/** 空模块占位脚本，仅用于持久化模块名，不在列表中展示。 */
export const USER_MODULE_PLACEHOLDER_FILE = "module__.star";

export function isUserModulePlaceholderPath(path: string): boolean {
  return userScriptFileName(path) === USER_MODULE_PLACEHOLDER_FILE;
}

export type UserScriptGroup = {
  module: string;
  scripts: string[];
};

export function groupUserScriptsByModule(paths: string[], extraModules: Iterable<string> = []): UserScriptGroup[] {
  const map = new Map<string, Set<string>>();
  for (const mod of extraModules) {
    const key = mod.trim().toLowerCase();
    if (key) map.set(key, new Set());
  }
  for (const p of paths) {
    const mod = userScriptModuleKey(p);
    if (!mod) continue;
    const key = mod.toLowerCase();
    if (!map.has(key)) map.set(key, new Set());
    if (!isUserModulePlaceholderPath(p)) {
      map.get(key)!.add(p);
    }
  }
  const out: UserScriptGroup[] = [];
  for (const [module, scriptSet] of map) {
    const scripts = [...scriptSet].sort((a, b) => userScriptFileName(a).localeCompare(userScriptFileName(b)));
    out.push({ module, scripts });
  }
  out.sort((a, b) => a.module.localeCompare(b.module));
  return out;
}

/** Filter user script groups by module, file name, or description. */
export function filterUserScriptGroups(
  groups: UserScriptGroup[],
  query: string,
  descriptions: Record<string, string> = {},
): UserScriptGroup[] {
  const q = query.trim().toLowerCase();
  if (!q) return groups;
  return groups
    .map((g) => {
      const modMatch = g.module.includes(q);
      const scripts = g.scripts.filter((p) => {
        if (modMatch) return true;
        if (userScriptFileName(p).toLowerCase().includes(q) || p.toLowerCase().includes(q)) return true;
        return (descriptions[p] ?? "").toLowerCase().includes(q);
      });
      return { module: g.module, scripts };
    })
    .filter((g) => g.scripts.length > 0);
}
