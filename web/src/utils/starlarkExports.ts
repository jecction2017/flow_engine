/** Top-level ``def`` names in Starlark source (export symbols). */

const DEF_RE = /^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/gm;

export function extractStarlarkExportFunctions(content: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const m of content.matchAll(DEF_RE)) {
    const name = m[1];
    if (!name || seen.has(name)) continue;
    seen.add(name);
    out.push(name);
  }
  return out;
}
