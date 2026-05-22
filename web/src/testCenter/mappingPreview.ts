import type { ContextMapping } from "@/api/testBatches";

function setDotted(root: Record<string, unknown>, path: string, value: unknown): void {
  const parts = path
    .split(".")
    .map((p) => p.trim())
    .filter(Boolean);
  if (parts.length === 0) throw new Error("target 路径不能为空");
  let cur: Record<string, unknown> = root;
  for (let i = 0; i < parts.length - 1; i++) {
    const p = parts[i]!;
    const nxt = cur[p];
    if (nxt == null || typeof nxt !== "object" || Array.isArray(nxt)) {
      const fresh: Record<string, unknown> = {};
      cur[p] = fresh;
      cur = fresh;
    } else {
      cur = nxt as Record<string, unknown>;
    }
  }
  cur[parts[parts.length - 1]!] = value;
}

/** 与后端 ``apply_lookup_row_to_context`` 语义对齐的纯预览（不落库）。 */
export function previewContextMapping(
  row: Record<string, unknown>,
  mapping: ContextMapping,
): Record<string, unknown> {
  if (mapping.mode === "script") {
    throw new Error("script");
  }
  if (mapping.mode === "spread") {
    return { ...row };
  }
  if (mapping.mode === "wrap") {
    const key = mapping.wrap_key.trim() || "input";
    if (mapping.wrap_as_list) return { [key]: [{ ...row }] };
    return { [key]: { ...row } };
  }
  const out: Record<string, unknown> = {};
  for (const r of mapping.rules) {
    if (!r.source || !r.target) continue;
    if (!Object.prototype.hasOwnProperty.call(row, r.source)) continue;
    setDotted(out, r.target, row[r.source]);
  }
  return out;
}
