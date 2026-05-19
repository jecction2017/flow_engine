import type { Boundary, FlowNode, LoopHooks, NodeHooks } from "@/types/flow";

function pushNonEmpty(parts: string[], value: string | null | undefined): void {
  if (typeof value === "string" && value.length > 0) {
    parts.push(value);
  }
}

function pushBoundary(parts: string[], boundary: Boundary | undefined): void {
  if (!boundary) return;
  for (const v of Object.values(boundary.inputs ?? {})) {
    pushNonEmpty(parts, v);
  }
  for (const v of Object.values(boundary.outputs ?? {})) {
    pushNonEmpty(parts, v);
  }
}

function pushHooks(parts: string[], hooks: NodeHooks | LoopHooks | null | undefined): void {
  if (!hooks) return;
  pushNonEmpty(parts, hooks.pre_exec);
  pushNonEmpty(parts, hooks.post_exec);
  if ("on_iteration_start" in hooks) {
    pushNonEmpty(parts, hooks.on_iteration_start);
    pushNonEmpty(parts, hooks.on_iteration_end);
  }
}

/** All user-editable Starlark / expression text on a node for topology search. */
export function collectNodeSearchText(node: FlowNode): string {
  const parts: string[] = [];
  pushNonEmpty(parts, node.name);
  pushNonEmpty(parts, node.description);
  pushNonEmpty(parts, node.condition);
  pushHooks(parts, node.hooks);
  if (node.on_error?.script) pushNonEmpty(parts, node.on_error.script);

  if (node.type === "task") {
    pushNonEmpty(parts, node.script);
    pushBoundary(parts, node.boundary);
  } else if (node.type === "loop") {
    pushNonEmpty(parts, node.iterable);
    if (node.iteration_collect) {
      pushNonEmpty(parts, node.iteration_collect.from_path);
      pushNonEmpty(parts, node.iteration_collect.append_to);
    }
  }

  return parts.join("\n");
}

export function nodeMatchesSearch(node: FlowNode, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return false;
  return collectNodeSearchText(node).toLowerCase().includes(q);
}
