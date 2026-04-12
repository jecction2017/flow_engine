import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type {
  ExecutionStrategy,
  FlowDocument,
  FlowNode,
  LoopNode,
  SubflowNode,
} from "@/types/flow";
import {
  createFlow as apiCreateFlow,
  deleteFlow as apiDeleteFlow,
  fetchFlowList,
  fetchFlowRaw,
  saveFlow as apiSaveFlow,
} from "@/api/flows";
import {
  defaultStrategies,
  emptyLoop,
  emptySubflow,
  emptyTask,
  nodeId,
} from "@/types/flow";

function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x)) as T;
}

const SAMPLE: FlowDocument = {
  name: "demo_flow",
  version: "1.0.0",
  strategies: {
    default_sync: { name: "default_sync", mode: "sync" },
    async_io: { name: "async_io", mode: "async", concurrency: 8, timeout: 120 },
    worker: { name: "worker", mode: "thread", concurrency: 4, timeout: 60 },
  },
  initial_context: { alert: { id: "ALT-1", severity: "HIGH" } },
  nodes: [
    {
      type: "task",
      name: "ingest",
      id: "ingest",
      strategy_ref: "default_sync",
      wait_before: false,
      script:
        '{"summary": {"id": resolve("$.global.alert.id"), "severity": resolve("$.global.alert.severity")}}\n',
      boundary: { inputs: {}, outputs: { summary: "$.global.summary" } },
    },
    {
      type: "task",
      name: "enrich_a",
      id: "enrich_a",
      strategy_ref: "async_io",
      wait_before: false,
      script: '{"row": {"k": "a"}}\n',
      boundary: { inputs: {}, outputs: { row: "$.global.row" } },
    },
    {
      type: "task",
      name: "enrich_b",
      id: "enrich_b",
      strategy_ref: "async_io",
      wait_before: true,
      script: '{"row": {"k": "b"}}\n',
      boundary: { inputs: {}, outputs: { row: "$.global.row" } },
    },
    {
      type: "task",
      name: "finalize",
      id: "finalize",
      strategy_ref: "worker",
      wait_before: true,
      script: '{"done": True}\n',
      boundary: { inputs: {}, outputs: { done: "$.global.done" } },
    },
  ],
};

function isNonSync(mode: string | undefined): boolean {
  return !!mode && mode !== "sync";
}

export const useFlowStudioStore = defineStore("flowStudio", () => {
  const doc = ref<FlowDocument>(clone(SAMPLE));
  const selection = ref<Selection>({ kind: "flow" });
  /** 当前绑定的服务端流程 id（对应 ``flows/{id}.yaml``） */
  const activeFlowId = ref<string | null>(null);
  const serverFlowsDir = ref<string | null>(null);
  const flowList = ref<{ id: string; name: string }[]>([]);
  const apiError = ref<string | null>(null);

  const strategiesList = computed(() =>
    Object.keys(doc.value.strategies).sort(),
  );

  function touch() {
    doc.value = clone(doc.value);
  }

  function select(sel: Selection) {
    selection.value = sel;
  }

  function ensureDefaultStrategies() {
    const d = defaultStrategies();
    for (const k of Object.keys(d)) {
      if (!doc.value.strategies[k]) doc.value.strategies[k] = d[k];
    }
  }

  function setFlowMeta(patch: Partial<Pick<FlowDocument, "name" | "version">>) {
    doc.value = { ...doc.value, ...patch };
  }

  function setInitialContextJson(text: string) {
    doc.value.initial_context = text.trim() ? (JSON.parse(text) as Record<string, unknown>) : null;
    touch();
  }

  function upsertStrategy(key: string, st: ExecutionStrategy) {
    doc.value.strategies[key] = { ...st, name: st.name || key };
    touch();
  }

  function removeStrategy(key: string) {
    if (key === "default_sync") return;
    const next = { ...doc.value.strategies };
    delete next[key];
    doc.value.strategies = next;
    for (const n of doc.value.nodes) rewriteStrategyRefs(n, key, "default_sync");
    touch();
    if (selection.value.kind === "strategy" && selection.value.key === key) {
      selection.value = { kind: "flow" };
    }
  }

  function rewriteStrategyRefs(n: FlowNode, from: string, to: string) {
    if (n.strategy_ref === from) n.strategy_ref = to;
    if (n.type === "loop" || n.type === "subflow") {
      for (const c of n.children) rewriteStrategyRefs(c, from, to);
    }
  }

  function getListRef(path: number[]): { list: FlowNode[]; index: number } | null {
    if (path.length === 0) return null;
    if (path.length === 1) return { list: doc.value.nodes, index: path[0] };
    let cur: FlowNode[] = doc.value.nodes;
    for (let i = 0; i < path.length - 1; i++) {
      const n = cur[path[i]];
      if (!n || (n.type !== "loop" && n.type !== "subflow")) return null;
      cur = n.children;
    }
    return { list: cur, index: path[path.length - 1] };
  }

  function getNode(path: number[]): FlowNode | null {
    const r = getListRef(path);
    if (!r) return null;
    return r.list[r.index] ?? null;
  }

  function replaceNode(path: number[], node: FlowNode) {
    const r = getListRef(path);
    if (!r) return;
    r.list[r.index] = node;
    touch();
  }

  function addRoot(kind: "task" | "loop" | "subflow") {
    const n =
      kind === "task"
        ? emptyTask(`task_${doc.value.nodes.length + 1}`)
        : kind === "loop"
          ? emptyLoop(`loop_${doc.value.nodes.length + 1}`)
          : emptySubflow(`subflow_${doc.value.nodes.length + 1}`);
    doc.value.nodes.push(n);
    touch();
    select({ kind: "node", path: [doc.value.nodes.length - 1] });
  }

  function addSibling(path: number[], kind: "task" | "loop" | "subflow") {
    const r = getListRef(path);
    if (!r) return;
    const insertAt = r.index + 1;
    const n =
      kind === "task"
        ? emptyTask(`task_${insertAt}`)
        : kind === "loop"
          ? emptyLoop(`loop_${insertAt}`)
          : emptySubflow(`subflow_${insertAt}`);
    if (path.length === 1) {
      doc.value.nodes.splice(insertAt, 0, n);
      touch();
      select({ kind: "node", path: [insertAt] });
      return;
    }
    const parentPath = path.slice(0, -1);
    const parent = getNode(parentPath) as LoopNode | SubflowNode | null;
    if (!parent) return;
    parent.children.splice(insertAt, 0, n);
    touch();
    select({ kind: "node", path: [...parentPath, insertAt] });
  }

  function addChild(path: number[], kind: "task" | "loop" | "subflow") {
    const p = getNode(path);
    if (!p || (p.type !== "loop" && p.type !== "subflow")) return;
    const n =
      kind === "task"
        ? emptyTask(`task_${p.children.length + 1}`)
        : kind === "loop"
          ? emptyLoop(`loop_${p.children.length + 1}`)
          : emptySubflow(`subflow_${p.children.length + 1}`);
    p.children.push(n);
    touch();
    select({ kind: "node", path: [...path, p.children.length - 1] });
  }

  function removeNode(path: number[]) {
    const r = getListRef(path);
    if (!r) return;
    r.list.splice(r.index, 1);
    touch();
    select({ kind: "flow" });
  }

  function exportJson(): string {
    return JSON.stringify(doc.value, null, 2);
  }

  function importJson(text: string) {
    const parsed = JSON.parse(text) as FlowDocument;
    doc.value = parsed;
    ensureDefaultStrategies();
    touch();
    select({ kind: "flow" });
    activeFlowId.value = null;
  }

  function loadDocument(data: FlowDocument, flowId: string | null = null) {
    doc.value = clone(data);
    ensureDefaultStrategies();
    touch();
    select({ kind: "flow" });
    activeFlowId.value = flowId;
  }

  async function refreshFlowList() {
    try {
      const res = await fetchFlowList();
      serverFlowsDir.value = res.flows_dir;
      flowList.value = res.flows.map((f) => ({ id: f.id, name: f.name }));
      apiError.value = null;
    } catch (e) {
      apiError.value = e instanceof Error ? e.message : String(e);
    }
  }

  async function loadFlowFromServer(flowId: string) {
    const raw = (await fetchFlowRaw(flowId)) as unknown as FlowDocument;
    loadDocument(raw, flowId);
  }

  async function saveFlowToServer() {
    const id = activeFlowId.value;
    if (!id) {
      throw new Error("未选择流程文件（请先打开或新建）");
    }
    await apiSaveFlow(id, doc.value);
    await refreshFlowList();
  }

  async function createFlowOnServer(id: string, name?: string) {
    await apiCreateFlow(id, name);
    await refreshFlowList();
    await loadFlowFromServer(id);
  }

  async function deleteFlowOnServer(flowId: string) {
    await apiDeleteFlow(flowId);
    await refreshFlowList();
    if (activeFlowId.value === flowId) {
      activeFlowId.value = null;
    }
  }

  function modeOf(ref: string): string {
    return doc.value.strategies[ref]?.mode ?? "sync";
  }

  /** 在 siblings[i] 与 siblings[i+1] 之间展示隐式并行提示 */
  function parallelEdgeAfter(siblings: FlowNode[], i: number): boolean {
    const a = siblings[i];
    const b = siblings[i + 1];
    if (!a || !b) return false;
    if (b.wait_before) return false;
    return isNonSync(modeOf(a.strategy_ref)) && isNonSync(modeOf(b.strategy_ref));
  }

  /** 合并连续的隐式并行边，得到若干 [start, end] 闭区间（每组至少 2 个节点） */
  function parallelGroupRanges(siblings: FlowNode[]): Array<{ start: number; end: number }> {
    const ranges: Array<{ start: number; end: number }> = [];
    const n = siblings.length;
    let i = 0;
    while (i < n) {
      if (i < n - 1 && parallelEdgeAfter(siblings, i)) {
        const start = i;
        let j = i;
        while (j < n - 1 && parallelEdgeAfter(siblings, j)) {
          j++;
        }
        ranges.push({ start, end: j });
        i = j + 1;
      } else {
        i++;
      }
    }
    return ranges;
  }

  /** 左侧连线轨道：首/中/末段，用于画竖线连接同一并行组 */
  function parallelRailRole(
    siblings: FlowNode[],
    index: number,
  ): "none" | "first" | "middle" | "last" {
    for (const r of parallelGroupRanges(siblings)) {
      if (index < r.start || index > r.end) continue;
      if (index === r.start) return "first";
      if (index === r.end) return "last";
      return "middle";
    }
    return "none";
  }

  return {
    doc,
    selection,
    strategiesList,
    select,
    touch,
    setFlowMeta,
    setInitialContextJson,
    upsertStrategy,
    removeStrategy,
    getNode,
    replaceNode,
    addRoot,
    addSibling,
    addChild,
    removeNode,
    exportJson,
    importJson,
    loadDocument,
    activeFlowId,
    serverFlowsDir,
    flowList,
    apiError,
    refreshFlowList,
    loadFlowFromServer,
    saveFlowToServer,
    createFlowOnServer,
    deleteFlowOnServer,
    parallelEdgeAfter,
    parallelGroupRanges,
    parallelRailRole,
    modeOf,
    nodeId,
    emptyTask,
    emptyLoop,
    emptySubflow,
    ensureDefaultStrategies,
  };
});
