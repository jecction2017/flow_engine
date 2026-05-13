import type { FlowDocument } from "@/types/flow";

/**
 * 为 ``$.`` 上下文路径编辑器生成补全候选：
 * - 固定根：``$.global``、``$.item``
 * - 从 ``initial_context`` 顶层键递归展开到 ``$.global.a.b…``
 * - 合并 ``extraPaths`` 中已出现的合法 ``$.`` 路径（含当前映射里手写的路径）
 */
export function collectContextPathSuggestions(
  doc: Pick<FlowDocument, "initial_context">,
  extraPaths: readonly string[],
): string[] {
  const out = new Set<string>(["$.global", "$.item"]);

  function walk(node: unknown, path: string): void {
    if (node !== null && typeof node === "object" && !Array.isArray(node)) {
      out.add(path);
      for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
        walk(v, `${path}.${k}`);
      }
    }
  }

  const ctx = doc.initial_context;
  if (ctx && typeof ctx === "object" && !Array.isArray(ctx)) {
    walk(ctx, "$.global");
  }

  for (const raw of extraPaths) {
    const t = raw.trim();
    if (t.startsWith("$.")) out.add(t);
  }

  return [...out].sort((a, b) => a.localeCompare(b));
}
