/** Starlark registry + user script files under `/api/starlark`. */

export type RegistryPythonFn = {
  id: string;
  starlark_name: string;
  category: string;
  summary: string;
  signature: Array<{ name: string; type: string; required?: boolean }>;
  returns: string;
  side_effects?: string;
};

export type RegistryInternalModule = {
  uri: string;
  path: string;
  exports: string[];
  summary: string;
};

export type RegistryDoc = {
  version: string;
  python_functions: RegistryPythonFn[];
  internal_modules: RegistryInternalModule[];
};

export type UserScriptsResponse = {
  scripts: string[];
  root: string;
};

export type UserScriptFileResponse = {
  path: string;
  content: string;
};

const jsonHeaders = { "Content-Type": "application/json" };

function userScriptUrl(relPath: string): string {
  const parts = relPath.split("/").filter(Boolean);
  if (parts.length < 2) throw new Error("脚本路径需为 <租户>/<文件>.star");
  return `/api/starlark/user/${parts.map(encodeURIComponent).join("/")}`;
}

/** Registry `path` is like `internal/lib/foo.star`; API expects `lib/foo.star`. */
export function internalRelFromRegistryPath(registryPath: string): string {
  const s = registryPath.replace(/^\/+/, "");
  if (s.startsWith("internal/")) return s.slice("internal/".length);
  return s;
}

function internalScriptUrl(relUnderInternal: string): string {
  const parts = relUnderInternal.split("/").filter(Boolean);
  if (!parts.length) throw new Error("internal 路径无效");
  return `/api/starlark/internal/${parts.map(encodeURIComponent).join("/")}`;
}

export async function fetchStarlarkRegistry(): Promise<RegistryDoc> {
  const r = await fetch("/api/starlark/registry");
  if (!r.ok) throw new Error(`registry: ${r.status}`);
  return r.json() as Promise<RegistryDoc>;
}

export async function fetchUserScripts(): Promise<UserScriptsResponse> {
  const r = await fetch("/api/starlark/user/scripts");
  if (!r.ok) throw new Error(`user scripts: ${r.status}`);
  return r.json() as Promise<UserScriptsResponse>;
}

export async function getUserScript(relPath: string): Promise<UserScriptFileResponse> {
  const r = await fetch(userScriptUrl(relPath));
  if (!r.ok) throw new Error(`get ${relPath}: ${r.status}`);
  return r.json() as Promise<UserScriptFileResponse>;
}

export async function getInternalScript(relUnderInternal: string): Promise<UserScriptFileResponse> {
  const r = await fetch(internalScriptUrl(relUnderInternal));
  if (!r.ok) throw new Error(`get internal ${relUnderInternal}: ${r.status}`);
  return r.json() as Promise<UserScriptFileResponse>;
}

export async function putUserScript(relPath: string, content: string): Promise<void> {
  const r = await fetch(userScriptUrl(relPath), {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify({ content }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `put ${relPath}: ${r.status}`);
  }
}

export type DebugNodeResponse =
  | { ok: true; result: Record<string, unknown> }
  | { ok: false; error: string; traceback?: string };

export async function debugNode(
  script: string,
  initialContext: Record<string, unknown> = {},
  profile?: string,
): Promise<DebugNodeResponse> {
  const r = await fetch("/api/debug/node", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      script,
      initial_context: initialContext,
      profile: profile ?? null,
    }),
  });
  return r.json() as Promise<DebugNodeResponse>;
}
