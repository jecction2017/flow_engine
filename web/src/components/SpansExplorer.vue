<template>
  <div class="spans-explorer">
    <div class="se-toolbar">
      <div class="se-toolbar-grid">
        <label class="ctl">
          <span>节点</span>
          <select v-model="filters.node_id" class="inp">
            <option value="">全部</option>
            <option v-for="nid in nodeOptions" :key="nid" :value="nid">{{ nid }}</option>
          </select>
        </label>
        <label class="ctl">
          <span>状态</span>
          <select v-model="filters.status" class="inp">
            <option value="">全部</option>
            <option value="success">success</option>
            <option value="failed">failed</option>
            <option value="skipped">skipped</option>
            <option value="running">running</option>
          </select>
        </label>
        <label class="ctl se-span-2">
          <span>业务键 scope_key</span>
          <input
            v-model.trim="filters.scope_key"
            class="inp mono"
            placeholder="精确匹配，回车搜索"
            @keyup.enter="reload"
          />
        </label>
        <div class="se-panel se-span-3">
          <div class="se-panel-hd">开始时间（UTC 写入）</div>
          <div class="se-panel-bd se-time-pair">
            <label class="ctl-inline">
              <span class="sub">≥</span>
              <input v-model="filters.started_after" class="inp mono" type="datetime-local" step="1" />
            </label>
            <label class="ctl-inline">
              <span class="sub">&lt;</span>
              <input v-model="filters.started_before" class="inp mono" type="datetime-local" step="1" />
            </label>
          </div>
        </div>
        <div class="se-panel se-span-2">
          <div class="se-panel-hd">耗时（毫秒）</div>
          <div class="se-panel-bd se-dur-pair">
            <label class="ctl-inline">
              <span class="sub">≥</span>
              <input
                v-model.number="filters.duration_min_ms"
                class="inp mono"
                type="number"
                min="0"
                step="1"
                placeholder="—"
              />
            </label>
            <label class="ctl-inline">
              <span class="sub">≤</span>
              <input
                v-model.number="filters.duration_max_ms"
                class="inp mono"
                type="number"
                min="0"
                step="1"
                placeholder="—"
              />
            </label>
          </div>
        </div>
        <div class="se-panel se-span-3">
          <div class="se-panel-hd">日志级别（与试运行一致）</div>
          <div class="se-panel-bd se-lvl-row">
            <button
              v-for="lvl in LOG_LEVELS"
              :key="lvl"
              type="button"
              class="se-chip-btn"
              :class="[`lvl-${lvl}`, { active: filters.log_level === lvl }]"
              @click="toggleLogLevel(lvl)"
            >
              {{ lvl }}
            </button>
            <button v-if="filters.log_level" type="button" class="link tiny" @click="clearLogLevel">清除</button>
          </div>
        </div>
      </div>
      <div class="se-toolbar-actions">
        <button type="button" class="btn ghost small" :disabled="loading" @click="reload">
          {{ loading ? "查询中…" : "搜索" }}
        </button>
        <button v-if="hasFilters" type="button" class="link small" @click="resetFilters">重置</button>
        <span class="sep" />
        <button type="button" class="link small" @click="expandTree">全部展开</button>
        <span class="sep">·</span>
        <button type="button" class="link small" @click="collapseTree">全部折叠</button>
        <span class="spacer" />
        <span class="muted small">本页 {{ items.length }} / 命中 {{ resp?.total ?? 0 }} 条</span>
        <button type="button" class="btn small ghost" :disabled="!hasNext || loading" @click="loadMore">
          {{ loading && appendMode ? "加载中…" : "加载更多" }}
        </button>
      </div>
    </div>

    <p v-if="filterBanner" class="trace-filter-banner">
      当前为筛选或分页结果：仅展示本页已加载的 Span；父子关系在缺少上层节点时可能在顶层并列显示。
      <button v-if="hasFilters" type="button" class="link small" @click="resetFilters">重置筛选</button>
    </p>

    <p v-if="error" class="err">{{ error }}</p>

    <div v-if="loading && !appendMode" class="muted center tree-state">加载中…</div>
    <div v-else-if="!items.length" class="muted center tree-state">没有匹配的 Span</div>
    <ExecutionLinkTree
      v-else
      ref="linkRef"
      :rows="linkRows"
      :timeline-min-ms="timeline.min"
      :timeline-max-ms="timeline.max"
      :collapsed="collapsedSpanKeys"
      :secondary-open-key="openDetailKey"
      :detail-on-row-click="true"
      :log-button="false"
      :highlight-node-id="activeHighlightNodeId"
      @toggle-collapsed="onToggleCollapsed"
      @row-click="onRowClick"
    >
      <template #secondary="{ row }">
        <div class="rt-inline-detail" @click.stop>
          <p v-if="detailErr" class="inline-err">{{ detailErr }}</p>
          <div v-else-if="detailLoading" class="muted small pad">加载详情…</div>
          <SpanInlineDetail v-else-if="detail && row.spanId != null && detail.id === row.spanId" :span="detail" />
        </div>
      </template>
    </ExecutionLinkTree>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import {
  getSpan,
  listDeployRunSpans,
  listTestRunSpans,
  type ListSpansParams,
  type SpanDetail,
  type SpanSummary,
  type SpansListResponse,
} from "@/api/spans";
import ExecutionLinkTree, { type ExecutionLinkRow } from "@/components/ExecutionLinkTree.vue";
import SpanInlineDetail from "@/components/SpanInlineDetail.vue";

const LOG_LEVELS = ["debug", "info", "warn", "error"] as const;

type SpanTreeRow = SpanSummary & {
  depth: number;
  hasChildren: boolean;
  isLast: boolean;
  guides: boolean[];
};

const props = defineProps<{
  deployRunId?: number;
  testRunId?: number;
  pageSize?: number;
  initialNodeId?: string | null;
}>();

const pageSize = computed(() => props.pageSize ?? 500);

const filters = reactive({
  node_id: "",
  status: "",
  scope_key: "",
  started_after: "",
  started_before: "",
  duration_min_ms: null as number | null,
  duration_max_ms: null as number | null,
  log_level: "" as "" | (typeof LOG_LEVELS)[number],
});

const loading = ref(false);
const error = ref("");
const resp = ref<SpansListResponse | null>(null);
const appendMode = ref(false);
const loadedItems = ref<SpanSummary[]>([]);
const linkRef = ref<InstanceType<typeof ExecutionLinkTree> | null>(null);

const collapsedSpanKeys = reactive(new Set<string>());
const openDetailKey = ref<string | null>(null);
const detail = ref<SpanDetail | null>(null);
const detailLoading = ref(false);
const detailErr = ref("");

const items = computed(() => loadedItems.value);
const nodeOptions = computed(() => resp.value?.node_ids ?? []);

const hasNext = computed(() => {
  if (!resp.value) return false;
  return loadedItems.value.length < resp.value.total;
});

const hasFilters = computed(() => {
  if (filters.node_id) return true;
  if (filters.status) return true;
  if (filters.scope_key) return true;
  if (filters.started_after.trim()) return true;
  if (filters.started_before.trim()) return true;
  if (filters.duration_min_ms != null && Number.isFinite(filters.duration_min_ms)) return true;
  if (filters.duration_max_ms != null && Number.isFinite(filters.duration_max_ms)) return true;
  if (filters.log_level) return true;
  return false;
});

function toggleLogLevel(lvl: (typeof LOG_LEVELS)[number]): void {
  filters.log_level = filters.log_level === lvl ? "" : lvl;
}

function clearLogLevel(): void {
  filters.log_level = "";
}

const filterBanner = computed(() => hasFilters.value || (resp.value != null && items.value.length < resp.value.total));

const activeHighlightNodeId = computed(() => filters.node_id || props.initialNodeId || null);

const timeline = computed(() => {
  const spans = items.value;
  let min = Infinity;
  let max = -Infinity;
  for (const s of spans) {
    const st = s.started_at ? Date.parse(s.started_at) : NaN;
    if (!Number.isFinite(st)) continue;
    const fin = s.finished_at ? Date.parse(s.finished_at) : NaN;
    const dur = s.duration_ms ?? 0;
    const end = Number.isFinite(fin) ? fin : st + Math.max(dur, 1);
    min = Math.min(min, st);
    max = Math.max(max, end);
  }
  if (!Number.isFinite(min)) return { min: 0, max: 1 };
  if (max <= min) return { min, max: min + 1 };
  return { min, max };
});

const flatSpanRows = computed<SpanTreeRow[]>(() => {
  const list = items.value;
  if (list.length === 0) return [];
  const idSet = new Set(list.map((r) => r.id));
  const childrenByParent = new Map<number | null, SpanSummary[]>();
  for (const r of list) {
    const pid = r.parent_span_id != null && idSet.has(r.parent_span_id) ? r.parent_span_id : null;
    if (!childrenByParent.has(pid)) childrenByParent.set(pid, []);
    childrenByParent.get(pid)!.push(r);
  }
  for (const arr of childrenByParent.values()) {
    arr.sort((a, b) => a.span_seq - b.span_seq || a.id - b.id);
  }
  const out: SpanTreeRow[] = [];
  const walk = (nodes: SpanSummary[], depth: number, ancestorGuides: boolean[]) => {
    nodes.forEach((node, idx) => {
      const isLast = idx === nodes.length - 1;
      const childList = childrenByParent.get(node.id) ?? [];
      out.push({
        ...node,
        depth,
        hasChildren: childList.length > 0,
        isLast,
        guides: [...ancestorGuides],
      });
      if (childList.length > 0 && !collapsedSpanKeys.has(String(node.id))) {
        walk(childList, depth + 1, [...ancestorGuides, !isLast]);
      }
    });
  };
  walk(childrenByParent.get(null) ?? [], 0, []);
  return out;
});

function formatDur(ms: number | null): string {
  if (ms == null) return "-";
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatSpanStarted(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function spanTone(st: string): string {
  if (st === "success") return "ok";
  if (st === "failed") return "bad";
  if (st === "skipped") return "skipped";
  if (st === "running") return "running";
  return "info";
}

const linkRows = computed<ExecutionLinkRow[]>(() => {
  const t = timeline.value;
  return flatSpanRows.value.map((r) => {
    const st0 = r.started_at ? Date.parse(r.started_at) : NaN;
    const en0 = r.finished_at ? Date.parse(r.finished_at) : NaN;
    const st = Number.isFinite(st0) ? st0 : t.min;
    const en = Number.isFinite(en0) ? en0 : st + Math.max(r.duration_ms ?? 1, 1);
    return {
      key: String(r.id),
      orderDisplay: String(r.span_seq),
      depth: r.depth,
      hasChildren: r.hasChildren,
      isLast: r.isLast,
      guides: r.guides,
      nodeId: r.node_id,
      nodeType: String(r.node_type),
      scopeKey: r.scope_key || "",
      startedDisplay: formatSpanStarted(r.started_at),
      startedTitle: r.started_at ?? undefined,
      durationMs: r.duration_ms,
      durationDisplay: formatDur(r.duration_ms),
      statusLabel: r.status,
      statusTone: spanTone(String(r.status)),
      logCount: r.log_count ?? 0,
      barStartMs: st,
      barEndMs: Math.max(en, st + 1),
      spanId: r.id,
    };
  });
});

function listParams(append: boolean): ListSpansParams {
  const p: ListSpansParams = {
    offset: append ? loadedItems.value.length : 0,
    limit: pageSize.value,
  };
  if (filters.node_id) p.node_id = filters.node_id;
  if (filters.status) p.status = filters.status;
  if (filters.scope_key) p.scope_key = filters.scope_key;
  if (filters.started_after.trim()) p.started_after = localDateTimeToIso(filters.started_after.trim());
  if (filters.started_before.trim()) p.started_before = localDateTimeToIso(filters.started_before.trim());
  if (filters.duration_min_ms != null && Number.isFinite(filters.duration_min_ms)) {
    p.duration_min_ms = Math.max(0, Math.floor(filters.duration_min_ms));
  }
  if (filters.duration_max_ms != null && Number.isFinite(filters.duration_max_ms)) {
    p.duration_max_ms = Math.max(0, Math.floor(filters.duration_max_ms));
  }
  if (filters.log_level) p.log_level = filters.log_level;
  return p;
}

/** datetime-local → ISO string for API */
function localDateTimeToIso(v: string): string {
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  return d.toISOString();
}

async function fetchPage(append: boolean): Promise<void> {
  loading.value = true;
  appendMode.value = append;
  error.value = "";
  try {
    let nextResp: SpansListResponse;
    const params = listParams(append);
    if (props.deployRunId != null) {
      nextResp = await listDeployRunSpans(props.deployRunId, params);
    } else if (props.testRunId != null) {
      nextResp = await listTestRunSpans(props.testRunId, params);
    } else {
      throw new Error("SpansExplorer 必须提供 deployRunId 或 testRunId");
    }
    resp.value = nextResp;
    loadedItems.value = append ? mergeItems(loadedItems.value, nextResp.items) : nextResp.items;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
    appendMode.value = false;
  }
}

async function reload(): Promise<void> {
  openDetailKey.value = null;
  detail.value = null;
  detailErr.value = "";
  await fetchPage(false);
}

function loadMore(): void {
  if (!hasNext.value || loading.value) return;
  void fetchPage(true);
}

function mergeItems(prev: SpanSummary[], next: SpanSummary[]): SpanSummary[] {
  const seen = new Set(prev.map((s) => s.id));
  const merged = [...prev];
  for (const s of next) {
    if (!seen.has(s.id)) merged.push(s);
  }
  return merged.sort((a, b) => a.span_seq - b.span_seq || a.id - b.id);
}

function resetFilters(): void {
  filters.node_id = "";
  filters.status = "";
  filters.scope_key = "";
  filters.started_after = "";
  filters.started_before = "";
  filters.duration_min_ms = null;
  filters.duration_max_ms = null;
  filters.log_level = "";
  void reload();
}

function expandTree(): void {
  collapsedSpanKeys.clear();
}

function collapseTree(): void {
  const list = items.value;
  const idSet = new Set(list.map((s) => s.id));
  for (const r of list) {
    const hasKids = list.some((c) => c.parent_span_id === r.id && idSet.has(c.id));
    if (hasKids) collapsedSpanKeys.add(String(r.id));
  }
}

function onToggleCollapsed(key: string): void {
  if (collapsedSpanKeys.has(key)) collapsedSpanKeys.delete(key);
  else collapsedSpanKeys.add(key);
}

function expandAncestors(spanId: number): void {
  const byId = new Map(items.value.map((s) => [s.id, s]));
  let cur = byId.get(spanId);
  while (cur?.parent_span_id != null) {
    collapsedSpanKeys.delete(String(cur.parent_span_id));
    cur = byId.get(cur.parent_span_id);
  }
}

function closeDetail(): void {
  openDetailKey.value = null;
  detail.value = null;
  detailErr.value = "";
}

function onRowClick(row: ExecutionLinkRow): void {
  if (row.spanId == null) return;
  if (openDetailKey.value === row.key) {
    closeDetail();
    return;
  }
  expandAncestors(row.spanId);
  openDetailKey.value = row.key;
}

async function loadDetail(spanId: number): Promise<void> {
  detailLoading.value = true;
  detailErr.value = "";
  detail.value = null;
  try {
    detail.value = await getSpan(spanId);
  } catch (e) {
    detailErr.value = e instanceof Error ? e.message : String(e);
  } finally {
    detailLoading.value = false;
  }
}

watch(openDetailKey, (key) => {
  if (key == null) {
    detail.value = null;
    detailErr.value = "";
    detailLoading.value = false;
    return;
  }
  const id = Number(key);
  if (!Number.isFinite(id)) return;
  void loadDetail(id);
});

watch(
  () => [activeHighlightNodeId.value, items.value.length] as const,
  () => {
    const nid = activeHighlightNodeId.value?.trim();
    if (!nid || items.value.length === 0) return;
    const match = items.value.find((s) => s.node_id === nid);
    if (!match) return;
    expandAncestors(match.id);
    requestAnimationFrame(() => {
      const esc =
        typeof CSS !== "undefined" && typeof CSS.escape === "function"
          ? CSS.escape(nid)
          : nid.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
      const root = linkRef.value?.rootElRef;
      const el = root?.querySelector(`[data-node-id="${esc}"]`);
      if (el instanceof HTMLElement) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  },
  { flush: "post" },
);

watch(
  () =>
    [props.deployRunId, props.testRunId, filters.node_id, filters.status, filters.log_level] as const,
  (now, prev) => {
    const switched = prev != null && (now[0] !== prev[0] || now[1] !== prev[1]);
    if (switched) {
      resp.value = null;
      loadedItems.value = [];
      collapsedSpanKeys.clear();
      closeDetail();
    }
    void reload();
  },
  { immediate: true },
);

watch(
  () => props.initialNodeId,
  (nodeId) => {
    const next = nodeId?.trim() ?? "";
    if (next && next !== filters.node_id) {
      filters.node_id = next;
    }
  },
  { immediate: true },
);

</script>

<style scoped>
.spans-explorer {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.se-toolbar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 8px 12px;
  border: 1px solid color-mix(in srgb, var(--border) 80%, #94a3b8);
  border-radius: 10px;
  background: linear-gradient(180deg, #f8fafc 0%, #fff 48%);
}

.se-toolbar-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px 12px;
  align-items: end;
}

@media (max-width: 1100px) {
  .se-toolbar-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.se-span-2 {
  grid-column: span 2;
}

.se-span-3 {
  grid-column: span 3;
}

@media (max-width: 1100px) {
  .se-span-2,
  .se-span-3 {
    grid-column: span 2;
  }
}

.se-toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding-top: 4px;
  border-top: 1px dashed color-mix(in srgb, var(--border) 70%, transparent);
}

.ctl {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11px;
  font-weight: 600;
  color: #475569;
  min-width: 0;
}

.ctl .inp {
  font-size: 12px;
  padding: 5px 8px;
  border: 1px solid color-mix(in srgb, #64748b 28%, var(--border));
  border-radius: 8px;
  background: #fff;
  color: #0f172a;
}

.ctl .inp:focus {
  outline: none;
  border-color: color-mix(in srgb, var(--accent, #2563eb) 55%, var(--border));
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent, #2563eb) 18%, transparent);
}

.se-panel {
  min-width: 0;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, #64748b 18%, var(--border));
  background: #fff;
  overflow: hidden;
}

.se-panel-hd {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: #64748b;
  padding: 5px 8px;
  background: color-mix(in srgb, #f1f5f9 88%, #fff);
  border-bottom: 1px solid color-mix(in srgb, var(--border) 75%, transparent);
}

.se-panel-bd {
  padding: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.se-time-pair,
.se-dur-pair {
  gap: 10px;
}

.ctl-inline {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--muted);
  flex: 1 1 140px;
  min-width: 0;
}

.ctl-inline .sub {
  flex: 0 0 auto;
  width: 1.25rem;
  font-weight: 700;
  color: #64748b;
  text-align: center;
}

.ctl-inline .inp {
  flex: 1 1 auto;
  min-width: 0;
}

.se-lvl-row {
  gap: 5px;
  align-items: center;
}

.se-chip-btn {
  text-transform: uppercase;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  border-radius: 999px;
  padding: 2px 9px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
  cursor: pointer;
}

.se-chip-btn.active.lvl-info {
  background: color-mix(in srgb, #3b82f6 18%, transparent);
  color: #1d4ed8;
  border-color: color-mix(in srgb, #3b82f6 35%, transparent);
}

.se-chip-btn.active.lvl-warn {
  background: color-mix(in srgb, #f59e0b 22%, transparent);
  color: #92400e;
  border-color: color-mix(in srgb, #f59e0b 40%, transparent);
}

.se-chip-btn.active.lvl-error {
  background: color-mix(in srgb, #ef4444 20%, transparent);
  color: #b91c1c;
  border-color: color-mix(in srgb, #ef4444 35%, transparent);
}

.se-chip-btn.active.lvl-debug {
  background: color-mix(in srgb, #94a3b8 22%, transparent);
  color: #475569;
  border-color: color-mix(in srgb, #94a3b8 40%, transparent);
}

.link.tiny {
  font-size: 10px;
  margin-left: 4px;
}

.spacer {
  flex: 1 1 auto;
}

.sep {
  color: var(--muted);
  font-size: 11px;
}

.tree-state {
  padding: 18px 12px;
  border: 1px dashed var(--border);
  border-radius: 10px;
  background: #fbfdff;
}

.trace-filter-banner {
  margin: 0;
  padding: 6px 10px;
  font-size: 11px;
  color: var(--muted);
  background: color-mix(in srgb, #f59e0b 12%, transparent);
  border: 1px dashed var(--border);
  border-radius: 8px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.muted {
  color: var(--muted);
}

.center {
  text-align: center;
}

.link {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  padding: 0;
  font-size: 11px;
}

.link:hover {
  text-decoration: underline;
}

.err {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, #fecaca 30%, transparent);
  color: #b91c1c;
  font-size: 12px;
}

.mono {
  font-family: var(--mono);
}

.inline-err {
  margin: 0 0 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: color-mix(in srgb, #fecaca 35%, transparent);
  color: #b91c1c;
  font-size: 12px;
}

.small {
  font-size: 11px;
}

.pad {
  padding: 6px 0;
}
</style>
