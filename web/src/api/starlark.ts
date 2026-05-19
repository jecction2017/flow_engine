/** Starlark registry + user script files under `/api/starlark`. */

import type { LogEntry } from "@/api/flows";

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
  /** path → description，与 scripts 同键 */
  descriptions?: Record<string, string>;
  root: string;
};

export type UserScriptFileResponse = {
  path: string;
  content: string;
  description: string;
  export_functions: string[];
};

export type PutUserScriptPayload = {
  content: string;
  description?: string;
  /** 省略时服务端从 content 自动提取 */
  export_functions?: string[];
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

export async function putUserScript(
  relPath: string,
  payload: PutUserScriptPayload,
): Promise<UserScriptFileResponse> {
  const r = await fetch(userScriptUrl(relPath), {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify({
      content: payload.content,
      description: payload.description ?? "",
      export_functions: payload.export_functions,
    }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `put ${relPath}: ${r.status}`);
  }
  return r.json() as Promise<UserScriptFileResponse>;
}

export async function deleteUserScript(relPath: string): Promise<void> {
  const r = await fetch(userScriptUrl(relPath), { method: "DELETE" });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `delete ${relPath}: ${r.status}`);
  }
}

export async function deleteUserModule(module: string): Promise<{ deleted: number }> {
  const r = await fetch(`/api/starlark/user/${encodeURIComponent(module)}`, { method: "DELETE" });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `delete module ${module}: ${r.status}`);
  }
  return r.json() as Promise<{ deleted: number }>;
}

export async function ensureUserModule(module: string): Promise<{ created: boolean }> {
  const r = await fetch(`/api/starlark/user/${encodeURIComponent(module)}/module`, { method: "PUT" });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `ensure module ${module}: ${r.status}`);
  }
  return r.json() as Promise<{ created: boolean }>;
}

export type DebugNodeResponse = {
  ok?: boolean;
  result?: unknown;
  error?: string;
  traceback?: string;
  logs?: LogEntry[];
};

/**
 * 节点 / 用户脚本调试入口 —— 服务端硬编码 RunMode.DEBUG，副作用类 builtin
 * 默认全部 SUPPRESS。``capabilityPolicy`` 仅作为 **白名单 / REDIRECT** 高级通道：
 * 例如 `{builtin_name: "http_simple_get", action: "allow"}` 显式放行某个 builtin。
 * 这里没有 ``runMode`` 选项是有意为之 —— 临时调试不应能切换到 production 模式。
 */
export type DebugNodeOptions = {
  capabilityPolicy?: Record<string, unknown>[];
};

export type DebugNodeParsed = {
  response: DebugNodeResponse;
  logs: LogEntry[];
  httpOk: boolean;
  rawText: string;
};

export async function debugNode(
  script: string,
  initialContext: Record<string, unknown> = {},
  profile?: string,
  options: DebugNodeOptions = {},
): Promise<DebugNodeParsed> {
  const r = await fetch("/api/debug/node", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      script,
      initial_context: initialContext,
      profile: profile ?? null,
      capability_policy: options.capabilityPolicy ?? [],
    }),
  });
  const rawText = await r.text();
  if (!r.ok) {
    return { response: { ok: false, error: rawText || `HTTP ${r.status}` }, logs: [], httpOk: false, rawText };
  }
  try {
    const parsed = JSON.parse(rawText) as DebugNodeResponse;
    const logs = Array.isArray(parsed.logs) ? parsed.logs : [];
    const { logs: _logs, ...rest } = parsed;
    void _logs;
    return { response: rest, logs, httpOk: true, rawText };
  } catch {
    return {
      response: { ok: true, result: rawText },
      logs: [],
      httpOk: true,
      rawText,
    };
  }
}
