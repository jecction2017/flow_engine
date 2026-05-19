/** Jump target candidates for on_error.action=jump — mirrors compiler ``_jump_allowed``. */

import type { FlowDocument, FlowNode } from "@/types/flow";
import { displayName, nodeId } from "@/types/flow";

type ParentMap = Map<string, string | null>;

function walkNodes(nodes: FlowNode[], out: FlowNode[]): void {
  for (const n of nodes) {
    out.push(n);
    if (n.type === "loop" || n.type === "subflow") {
      walkNodes(n.children, out);
    }
  }
}

function allNodeIds(nodes: FlowNode[]): string[] {
  const flat: FlowNode[] = [];
  walkNodes(nodes, flat);
  return flat.map((n) => nodeId(n));
}

function buildParentMap(nodes: FlowNode[]): ParentMap {
  const parent: ParentMap = new Map();

  function rec(members: FlowNode[], p: string | null): void {
    for (const m of members) {
      parent.set(nodeId(m), p);
      if (m.type === "loop" || m.type === "subflow") {
        rec(m.children, nodeId(m));
      }
    }
  }

  rec(nodes, null);
  return parent;
}

function scopeListFor(nodes: FlowNode[], nodeIdStr: string): string[] | null {
  function findList(members: FlowNode[]): string[] | null {
    const ids = members.map((x) => nodeId(x));
    if (ids.includes(nodeIdStr)) return ids;
    for (const m of members) {
      if (m.type === "loop" || m.type === "subflow") {
        const got = findList(m.children);
        if (got) return got;
      }
    }
    return null;
  }

  return findList(nodes);
}

function isAncestor(ancestor: string, node: string, parent: ParentMap): boolean {
  let cur = parent.get(node) ?? null;
  while (cur != null) {
    if (cur === ancestor) return true;
    cur = parent.get(cur) ?? null;
  }
  return false;
}

function jumpAllowed(
  doc: FlowDocument,
  src: string,
  target: string,
  parent: ParentMap,
): boolean {
  if (src === target) return false;
  const ids = new Set(allNodeIds(doc.nodes));
  if (!ids.has(target)) return false;
  const sibs = new Set(scopeListFor(doc.nodes, src) ?? []);
  if (sibs.has(target) && target !== src) return true;
  if (isAncestor(target, src, parent)) return true;
  return false;
}

export type JumpTargetOption = { id: string; label: string };

/**
 * Returns node ids that ``on_error.action=jump`` may target from ``sourceNodeId``.
 */
export function listJumpTargets(doc: FlowDocument, sourceNodeId: string): JumpTargetOption[] {
  const parent = buildParentMap(doc.nodes);
  const flat: FlowNode[] = [];
  walkNodes(doc.nodes, flat);
  const out: JumpTargetOption[] = [];
  for (const n of flat) {
    const id = nodeId(n);
    if (id === sourceNodeId) continue;
    if (!jumpAllowed(doc, sourceNodeId, id, parent)) continue;
    out.push({ id, label: displayName(n) });
  }
  return out;
}
