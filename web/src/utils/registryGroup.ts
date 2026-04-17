/** Group registry python_functions by module (from id or category fallback). */

import type { RegistryPythonFn } from "@/api/starlark";

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
