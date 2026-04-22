import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";
import type {
  ExecutionStrategy,
  FlowDocument,
  FlowNode,
  LoopNode,
  Selection,
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
  NODE_ID_PATTERN,
  defaultStrategies,
  displayName,
  emptyLoop,
  emptySubflow,
  emptyTask,
  isValidNodeId,
  nodeId,
} from "@/types/flow";

function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x)) as T;
}

// ---------------------------------------------------------------------------
// 节点调试上下文 —— localStorage 持久化（按 flowId 分桶，不写入 YAML）
// ---------------------------------------------------------------------------

const DEBUG_CTX_STORAGE_PREFIX = "flowEngine:debugCtx:";

function debugCtxStorageKey(flowId: string | null): string {
  return `${DEBUG_CTX_STORAGE_PREFIX}${flowId ?? "_local"}`;
}

function readPersistedDebugContexts(flowId: string | null): Record<string, string> {
  if (typeof window === "undefined" || !window.localStorage) return {};
  try {
    const raw = window.localStorage.getItem(debugCtxStorageKey(flowId));
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof v === "string") out[k] = v;
    }
    return out;
  } catch {
    return {};
  }
}

function writePersistedDebugContexts(
  flowId: string | null,
  data: Record<string, string>,
): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    const key = debugCtxStorageKey(flowId);
    if (Object.keys(data).length === 0) {
      window.localStorage.removeItem(key);
    } else {
      window.localStorage.setItem(key, JSON.stringify(data));
    }
  } catch {
    // storage full / denied / private mode — 忽略即可
  }
}

const SAMPLE: FlowDocument = {
  display_name: "demo_flow",
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
  const nodeDrafts = ref<Record<string, FlowNode>>({});
  const dirtyNodePaths = ref<Set<string>>(new Set());
  /** 当前绑定的服务端流程 id（对应 ``data/flows/{id}.yaml``） */
  const activeFlowId = ref<string | null>(null);
  /**
   * 每个节点独立、可完全自定义的调试上下文（原始 JSON 文本，按节点 id/path 隔离）。
   * 初始化时优先从 ``localStorage`` 恢复，避免每次调试都重复造数据。
   */
  const nodeDebugContexts = ref<Record<string, string>>(
    readPersistedDebugContexts(activeFlowId.value),
  );
  const serverFlowsDir = ref<string | null>(null);
  // 列表项里保留 display_name 字段（可能为空串，UI 会回落到 id）。
  const flowList = ref<{ id: string; display_name: string }[]>([]);
  const apiError = ref<string | null>(null);

  const strategiesList = computed(() =>
    Object.keys(doc.value.strategies).sort(),
  );

  const searchQuery = ref("");

  function touch() {
    doc.value = clone(doc.value);
  }

  function pathKey(path: number[]): string {
    return path.join("/");
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

  function setFlowMeta(patch: Partial<Pick<FlowDocument, "display_name" | "version">>) {
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

  /**
   * 读穿：优先返回节点的草稿（未保存修改），没有草稿时退化为 doc 中已提交的版本。
   * 供「调试面板」等需要看到未保存改动的只读消费者使用，不会创建新的草稿条目。
   */
  function viewNode(path: number[]): FlowNode | null {
    const key = pathKey(path);
    const draft = nodeDrafts.value[key];
    if (draft) return draft;
    return getNode(path);
  }

  function replaceNode(path: number[], node: FlowNode) {
    const r = getListRef(path);
    if (!r) return;
    r.list[r.index] = node;
    touch();
  }

  function editableNode(path: number[]): FlowNode | null {
    const key = pathKey(path);
    const cached = nodeDrafts.value[key];
    if (cached) return cached;
    const base = getNode(path);
    if (!base) return null;
    const draft = clone(base);
    nodeDrafts.value = { ...nodeDrafts.value, [key]: draft };
    return draft;
  }

  function updateNodeDraft(path: number[], node: FlowNode) {
    const key = pathKey(path);
    nodeDrafts.value = { ...nodeDrafts.value, [key]: clone(node) };
    dirtyNodePaths.value.add(key);
  }

  function isNodeDirty(path: number[]): boolean {
    return dirtyNodePaths.value.has(pathKey(path));
  }

  function clearNodeDraft(path: number[]) {
    const key = pathKey(path);
    const next = { ...nodeDrafts.value };
    delete next[key];
    nodeDrafts.value = next;
    dirtyNodePaths.value.delete(key);
  }

  function clearAllNodeDrafts() {
    nodeDrafts.value = {};
    dirtyNodePaths.value = new Set();
  }

  /**
   * 为「节点调试上下文」生成稳定的 key：使用节点 id（逻辑主键）；
   * 对于尚未填写 id 的草稿（正常 UI 流程不会发生），退化到 path 保证 DOM 可用。
   */
  function debugContextKey(path: number[]): string {
    const n = getNode(path);
    if (n) {
      const id = nodeId(n);
      if (id) return `nid:${id}`;
    }
    return `p:${pathKey(path)}`;
  }

  function getDebugContextText(path: number[]): string | undefined {
    return nodeDebugContexts.value[debugContextKey(path)];
  }

  function setDebugContextText(path: number[], text: string) {
    nodeDebugContexts.value = {
      ...nodeDebugContexts.value,
      [debugContextKey(path)]: text,
    };
  }

  function clearDebugContext(path: number[]) {
    const key = debugContextKey(path);
    if (!(key in nodeDebugContexts.value)) return;
    const next = { ...nodeDebugContexts.value };
    delete next[key];
    nodeDebugContexts.value = next;
  }

  function clearAllDebugContexts() {
    nodeDebugContexts.value = {};
  }

  /**
   * 递归遍历整棵流程树（含容器子节点），收集所有节点 id（空 id 跳过）。
   *
   * 注意：**必须合并草稿**。如果某节点存在未提交的编辑（`nodeDrafts`），
   * 以草稿里的 id 为准，而不是 doc 里已提交的旧 id。理由：
   * 1. 同一会话里用户可能在多个节点之间来回改 id，只用已提交数据会漏掉
   *    「A 草稿改成 X、B 也输入 X」这类跨节点撞键。
   * 2. 当前节点自己改了新 id 后，如果再改回原值，也不能把 doc 里那份
   *    旧 id 当成「别人家的 id」误判冲突。
   *
   * 树结构（父子关系 / 同级顺序）始终以 doc 为准——结构性变更
   * （add/remove/move）都会先 `clearAllNodeDrafts()`，保证 draft 不会
   * 出现在 doc 结构之外的位置。
   */
  function collectAllNodeIds(): Set<string> {
    const out = new Set<string>();
    const walk = (ns: FlowNode[], prefix: number[]) => {
      ns.forEach((n, i) => {
        const p = [...prefix, i];
        const live = nodeDrafts.value[pathKey(p)] ?? n;
        const id = nodeId(live);
        if (id) out.add(id);
        if (n.type === "loop" || n.type === "subflow") walk(n.children, p);
      });
    };
    walk(doc.value.nodes, []);
    return out;
  }

  /** 基于 prefix 生成全局唯一且符合 id 规则的 id，如 ``task_1``、``task_2``…… */
  function allocateNodeId(prefix: "task" | "loop" | "subflow"): string {
    const existing = collectAllNodeIds();
    let i = 1;
    while (existing.has(`${prefix}_${i}`)) i++;
    const candidate = `${prefix}_${i}`;
    return NODE_ID_PATTERN.test(candidate) ? candidate : `${prefix}_${Date.now()}`;
  }

  function makeFreshNode(kind: "task" | "loop" | "subflow"): FlowNode {
    const id = allocateNodeId(kind);
    if (kind === "task") return emptyTask(id);
    if (kind === "loop") return emptyLoop(id);
    return emptySubflow(id);
  }

  /** 任何一次变更（编辑/重置/清空/切换流程）都会异步落到 ``localStorage``。 */
  watch(
    nodeDebugContexts,
    (v) => {
      writePersistedDebugContexts(activeFlowId.value, v);
    },
    { deep: true },
  );

  function flushNodeDraftsToDocument() {
    const keys = Object.keys(nodeDrafts.value);
    // Apply shallower paths first, then deeper paths.
    // If a parent and its child both have drafts, this order ensures the child
    // draft is applied last and won't be overwritten by an older parent snapshot.
    keys.sort((a, b) => a.split("/").length - b.split("/").length);
    for (const key of keys) {
      const node = nodeDrafts.value[key];
      if (!node) continue;
      const path = key.split("/").filter(Boolean).map((x) => Number(x));
      if (path.some((n) => Number.isNaN(n))) continue;
      replaceNode(path, clone(node));
    }
    clearAllNodeDrafts();
  }

  function addRoot(kind: "task" | "loop" | "subflow") {
    clearAllNodeDrafts();
    const n = makeFreshNode(kind);
    doc.value.nodes.push(n);
    touch();
    select({ kind: "node", path: [doc.value.nodes.length - 1] });
  }

  function addSibling(path: number[], kind: "task" | "loop" | "subflow") {
    clearAllNodeDrafts();
    const r = getListRef(path);
    if (!r) return;
    const insertAt = r.index + 1;
    const n = makeFreshNode(kind);
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
    clearAllNodeDrafts();
    const p = getNode(path);
    if (!p || (p.type !== "loop" && p.type !== "subflow")) return;
    const n = makeFreshNode(kind);
    p.children.push(n);
    touch();
    select({ kind: "node", path: [...path, p.children.length - 1] });
  }

  function removeNode(path: number[]) {
    clearAllNodeDrafts();
    const r = getListRef(path);
    if (!r) return;
    r.list.splice(r.index, 1);
    touch();
    select({ kind: "flow" });
  }

  function copyNode(path: number[]) {
    clearAllNodeDrafts();
    const r = getListRef(path);
    if (!r) return;
    
    // Create deep copy of the node
    const nodeCopy = clone(r.list[r.index]);
    
    // Allocate new IDs for the copied node and all its children
    const assignNewIds = (n: FlowNode) => {
      const newId = allocateNodeId(n.type);
      if (n.id !== undefined) {
        n.id = newId;
      }
      
      // Update name to indicate it's a copy
      if (n.name) {
        n.name = `${n.name}_copy`;
      }
      
      if (n.type === "loop" || n.type === "subflow") {
        for (const c of n.children) {
          assignNewIds(c);
        }
      }
    };
    
    assignNewIds(nodeCopy);
    
    // Insert after the original node
    r.list.splice(r.index + 1, 0, nodeCopy);
    touch();
    
    // Create new path for selection (same prefix, index + 1)
    const newPath = [...path];
    newPath[newPath.length - 1] = r.index + 1;
    select({ kind: "node", path: newPath });
  }

  function moveNodeUp(path: number[]) {
    const r = getListRef(path);
    if (!r || r.index === 0) return; // Already at top
    
    clearAllNodeDrafts();
    const temp = r.list[r.index];
    r.list[r.index] = r.list[r.index - 1];
    r.list[r.index - 1] = temp;
    touch();
    
    // Update selection path
    const newPath = [...path];
    newPath[newPath.length - 1] = r.index - 1;
    select({ kind: "node", path: newPath });
  }

  function moveNodeDown(path: number[]) {
    const r = getListRef(path);
    if (!r || r.index === r.list.length - 1) return; // Already at bottom
    
    clearAllNodeDrafts();
    const temp = r.list[r.index];
    r.list[r.index] = r.list[r.index + 1];
    r.list[r.index + 1] = temp;
    touch();
    
    // Update selection path
    const newPath = [...path];
    newPath[newPath.length - 1] = r.index + 1;
    select({ kind: "node", path: newPath });
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
    clearAllNodeDrafts();
    // 导入来历不明的 JSON，丢弃本地 ``_local`` 桶的旧调试数据。
    nodeDebugContexts.value = {};
  }

  function loadDocument(data: FlowDocument, flowId: string | null = null) {
    doc.value = clone(data);
    ensureDefaultStrategies();
    touch();
    select({ kind: "flow" });
    activeFlowId.value = flowId;
    clearAllNodeDrafts();
    // 切换流程时加载该流程对应的调试上下文，保留上次编辑内容。
    nodeDebugContexts.value = readPersistedDebugContexts(flowId);
  }

  async function refreshFlowList() {
    try {
      const res = await fetchFlowList();
      serverFlowsDir.value = res.flows_dir;
      flowList.value = res.flows.map((f) => ({
        id: f.id,
        display_name: f.display_name ?? "",
      }));
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
    viewNode,
    replaceNode,
    editableNode,
    updateNodeDraft,
    collectAllNodeIds,
    allocateNodeId,
    isValidNodeId,
    NODE_ID_PATTERN,
    isNodeDirty,
    clearNodeDraft,
    clearAllNodeDrafts,
    flushNodeDraftsToDocument,
    getDebugContextText,
    setDebugContextText,
    clearDebugContext,
    clearAllDebugContexts,
    addRoot,
    addSibling,
    addChild,
    removeNode,
    copyNode,
    moveNodeUp,
    moveNodeDown,
    exportJson,
    importJson,
    loadDocument,
    activeFlowId,
    serverFlowsDir,
    flowList,
    apiError,
    searchQuery,
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
    displayName,
    emptyTask,
    emptyLoop,
    emptySubflow,
    ensureDefaultStrategies,
  };
});
