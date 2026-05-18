import type { CapabilityRule } from "@/types/flow";

/** Per-script debug session persisted in browser localStorage (not written to server). */
export type UserScriptDebugSession = {
  ctxText: string;
  profile: string;
  capabilityPolicy: CapabilityRule[];
};

const STORAGE_KEY = "flowEngine:userScriptDebug:v1";

function readAll(): Record<string, UserScriptDebugSession> {
  if (typeof window === "undefined" || !window.localStorage) return {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const out: Record<string, UserScriptDebugSession> = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (!v || typeof v !== "object" || Array.isArray(v)) continue;
      const row = v as Record<string, unknown>;
      out[k] = {
        ctxText: typeof row.ctxText === "string" ? row.ctxText : "{}",
        profile: typeof row.profile === "string" ? row.profile : "default",
        capabilityPolicy: Array.isArray(row.capabilityPolicy)
          ? (row.capabilityPolicy as CapabilityRule[])
          : [],
      };
    }
    return out;
  } catch {
    return {};
  }
}

function writeAll(data: Record<string, UserScriptDebugSession>): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    if (Object.keys(data).length === 0) {
      window.localStorage.removeItem(STORAGE_KEY);
    } else {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    }
  } catch {
    // storage full / denied — ignore
  }
}

export function readUserScriptDebugSession(scriptPath: string): UserScriptDebugSession | null {
  const key = scriptPath.trim();
  if (!key) return null;
  return readAll()[key] ?? null;
}

export function writeUserScriptDebugSession(
  scriptPath: string,
  session: UserScriptDebugSession,
): void {
  const key = scriptPath.trim();
  if (!key) return;
  const all = readAll();
  all[key] = session;
  writeAll(all);
}
