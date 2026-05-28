<template>
  <div class="spans-explorer">
    <p v-if="error" class="err">{{ error }}</p>

    <ExecutionLinkTree
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
      <template #toolbar>
        <button type="button" class="link" @click="expandTree">全部展开</button>
        <span class="sep">·</span>
        <button type="button" class="link" @click="collapseTree">全部折叠</button>
        <InfoTip v-if="helpTip" :text="helpTip" />
        <span class="spacer" />
        <button
          v-if="hasFilters"
          type="button"
          class="rt-chip-btn rt-chip-toggle"
          :class="{ active: filters.include_descendants }"
          title="筛选命中父节点时，一并返回该父节点的完整子树"
          @click="toggleIncludeDescendants"
        >
          包含子节点
        </button>
        <button type="button" class="btn small ghost" :disabled="loading" @click="reload">
          {{ loading && !appendMode ? "查询中…" : "搜索" }}
        </button>
        <button v-if="hasFilters" type="button" class="link small" @click="resetFilters">重置</button>
        <span class="muted small">
          <template v-if="hasFilters">
            命中 {{ resp?.total_matched ?? 0 }} · 共 {{ resp?.total_roots ?? 0 }} 棵子树 · 本页 {{ items.length }} 个 Span
          </template>
          <template v-else>
            共 {{ resp?.total_roots ?? 0 }} 棵子树 · 本页 {{ items.length }} 个 Span
          </template>
        </span>
        <InfoTip
          v-if="truncationTip"
          :text="truncationTip"
          wide
          align-end
        />
        <button
          type="button"
          class="btn small ghost"
          :disabled="!hasNext || loading"
          @click="loadMore"
        >
          {{ loading && appendMode ? "加载中…" : "加载更多" }}
        </button>
      </template>

      <template #filters>
        <!-- col 1: 顺序 spacer -->
        <span class="rt-filters-spacer" aria-hidden="true" />
        <!-- col 2: dot spacer -->
        <span class="rt-filters-spacer" aria-hidden="true" />
        <!-- col 3: node_id -->
        <select v-model="filters.node_id" class="rt-finp" :title="selectedNodeOptionLabel || '全部节点'">
          <option value="">全部节点</option>
          <option v-for="opt in nodeOptions" :key="opt.node_id" :value="opt.node_id">
            {{ opt.node_name }}
          </option>
        </select>
        <!-- col 4: 类型 (no filter) -->
        <span class="rt-filters-spacer" aria-hidden="true" />
        <!-- col 5: scope_key -->
        <input
          v-model.trim="filters.scope_key"
          class="rt-finp mono"
          placeholder="业务键"
          title="scope_key 精确匹配，回车搜索"
          @keyup.enter="reload"
        />
        <!-- col 6: 开始时间范围 popover -->
        <span class="rt-filter-cell">
          <button
            type="button"
            class="rt-fbtn"
            :class="{ active: hasTimeRange }"
            :title="timeRangeTitle"
            :aria-expanded="timePopOpen"
            @click.stop="toggleTimePop"
          >
            <span aria-hidden="true">⏱</span>
          </button>
          <div v-if="timePopOpen" class="rt-popover" @click.stop>
            <div class="rt-popover-hd">
              <span>开始时间</span>
              <span class="muted">UTC 写入</span>
            </div>
            <div class="rt-popover-row">
              <span class="sub">≥</span>
              <input
                v-model="filters.started_after"
                type="datetime-local"
                step="1"
                class="rt-finp mono"
                @keyup.enter="commitPopAndReload"
              />
            </div>
            <div class="rt-popover-row">
              <span class="sub">&lt;</span>
              <input
                v-model="filters.started_before"
                type="datetime-local"
                step="1"
                class="rt-finp mono"
                @keyup.enter="commitPopAndReload"
              />
            </div>
            <div class="rt-popover-actions">
              <button v-if="hasTimeRange" type="button" class="link" @click="clearTimeRange">清除</button>
              <button type="button" class="link" @click="commitPopAndReload">应用</button>
            </div>
          </div>
        </span>
        <!-- col 7: 耗时范围 popover -->
        <span class="rt-filter-cell">
          <button
            type="button"
            class="rt-fbtn"
            :class="{ active: hasDurRange }"
            :title="durRangeTitle"
            :aria-expanded="durPopOpen"
            @click.stop="toggleDurPop"
          >
            <span aria-hidden="true">Δ</span>
          </button>
          <div v-if="durPopOpen" class="rt-popover" @click.stop>
            <div class="rt-popover-hd">
              <span>耗时</span>
              <span class="muted">毫秒</span>
            </div>
            <div class="rt-popover-row">
              <span class="sub">≥</span>
              <input
                v-model.number="filters.duration_min_ms"
                type="number"
                min="0"
                step="1"
                class="rt-finp mono"
                placeholder="—"
                @keyup.enter="commitPopAndReload"
              />
            </div>
            <div class="rt-popover-row">
              <span class="sub">≤</span>
              <input
                v-model.number="filters.duration_max_ms"
                type="number"
                min="0"
                step="1"
                class="rt-finp mono"
                placeholder="—"
                @keyup.enter="commitPopAndReload"
              />
            </div>
            <div class="rt-popover-actions">
              <button v-if="hasDurRange" type="button" class="link" @click="clearDurRange">清除</button>
              <button type="button" class="link" @click="commitPopAndReload">应用</button>
            </div>
          </div>
        </span>
        <!-- col 8: 时间线区 - 状态过滤 -->
        <select
          v-model="filters.status"
          class="rt-finp"
          :title="filters.status ? `状态：${filters.status}` : '全部状态'"
        >
          <option value="">全部状态</option>
          <option value="success">成功</option>
          <option value="failed">失败</option>
          <option value="skipped">跳过</option>
          <option value="running">运行中</option>
        </select>
        <!-- col 9 + col 10 span: log level chips -->
        <span class="rt-finp-chips rt-log-chips">
          <button
            v-for="lvl in LOG_LEVELS"
            :key="lvl"
            type="button"
            class="rt-chip-btn"
            :class="[`lvl-${lvl}`, { active: filters.log_level === lvl }]"
            :title="`日志级别：${lvl}`"
            @click="toggleLogLevel(lvl)"
          >
            {{ lvl[0].toUpperCase() }}
          </button>
        </span>
      </template>

      <template #secondary="{ row }">
        <div class="rt-inline-detail" @click.stop>
          <p v-if="detailErr" class="inline-err">{{ detailErr }}</p>
          <div v-else-if="detailLoading" class="muted small pad">加载详情…</div>
          <SpanInlineDetail v-else-if="detail && row.spanId != null && detail.id === row.spanId" :span="detail" />
        </div>
      </template>

      <template #footer>
        <div v-if="loading && !appendMode" class="tree-state">加载中…</div>
        <div v-else-if="!items.length" class="tree-state">没有匹配的 Span</div>
      </template>
    </ExecutionLinkTree>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
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
import InfoTip from "@/components/InfoTip.vue";
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
  /** Page size in **root subtrees**, not spans. Backend caps per-page
   *  span count separately (~5K) to bound the wire size. */
  pageSize?: number;
  initialNodeId?: string | null;
  /** Optional help text rendered next to "全部展开 / 全部折叠" as a
   *  hover-trigger info tip; replaces the old outer section header. */
  helpTip?: string;
}>();

const pageSize = computed(() => props.pageSize ?? 50);

const filters = reactive({
  node_id: "",
  status: "",
  scope_key: "",
  started_after: "",
  started_before: "",
  duration_min_ms: null as number | null,
  duration_max_ms: null as number | null,
  log_level: "" as "" | (typeof LOG_LEVELS)[number],
  /** Tree-mode modifier: when true, matched parent spans pull down
   *  their full subtree (in addition to the always-on ancestor chain).
   *  Only meaningful when other filters are non-empty; the UI hides the
   *  toggle otherwise. */
  include_descendants: false,
});

const loading = ref(false);
const error = ref("");
const resp = ref<SpansListResponse | null>(null);
const appendMode = ref(false);
const loadedItems = ref<SpanSummary[]>([]);
const linkRef = ref<InstanceType<typeof ExecutionLinkTree> | null>(null);

// Range filter popovers (started_at / duration). At most one is open at a
// time; clicking outside closes whichever is open. Both popovers share the
// same dismissal listener installed in onMounted.
const timePopOpen = ref(false);
const durPopOpen = ref(false);

const collapsedSpanKeys = reactive(new Set<string>());
const openDetailKey = ref<string | null>(null);
const detail = ref<SpanDetail | null>(null);
const detailLoading = ref(false);
const detailErr = ref("");

const items = computed(() => loadedItems.value);
const nodeOptions = computed(() => {
  const opts = resp.value?.node_options;
  if (Array.isArray(opts) && opts.length > 0) {
    return opts.map((it) => ({
      node_id: it.node_id,
      node_name: it.node_name || it.node_id,
    }));
  }
  const ids = resp.value?.node_ids ?? [];
  return ids.map((nid) => ({ node_id: nid, node_name: nid }));
});
const selectedNodeOptionLabel = computed(() => {
  const selected = filters.node_id?.trim();
  if (!selected) return "";
  const hit = nodeOptions.value.find((x) => x.node_id === selected);
  return hit?.node_name || selected;
});

const hasNext = computed(() => {
  // Pagination is by root subtree. The next page starts at offset =
  // resp.offset + resp.limit; if that's still < total_roots there is more
  // to load. Span count on the page is bounded separately by the server.
  if (!resp.value) return false;
  const consumed = resp.value.offset + resp.value.limit;
  return consumed < resp.value.total_roots;
});

const truncationTip = computed<string | null>(() => {
  const t = resp.value?.truncated;
  if (!t) return null;
  if (!t.matched && !t.returned) return null;
  // Both flags warn the user that filter refinement is required to see
  // every result. Wording is verbose because the InfoTip can host it.
  const parts: string[] = [];
  if (t.matched) {
    parts.push("过滤命中超过 10,000 条，部分匹配未参与树展开。");
  }
  if (t.returned) {
    parts.push("当前页展开后 span 超过 5,000 条，已按完整子树截断。");
  }
  parts.push("请收窄筛选条件（按节点、状态、时间或耗时）以获得完整结果。");
  return parts.join(" ");
});

const hasTimeRange = computed(
  () => !!filters.started_after.trim() || !!filters.started_before.trim(),
);

const hasDurRange = computed(
  () =>
    (filters.duration_min_ms != null && Number.isFinite(filters.duration_min_ms)) ||
    (filters.duration_max_ms != null && Number.isFinite(filters.duration_max_ms)),
);

const hasFilters = computed(() => {
  // Note: ``include_descendants`` is intentionally NOT counted here. It
  // is a *modifier* on filtered queries, not a filter itself; toggling it
  // alone with no other filter has no effect on the result set.
  if (filters.node_id) return true;
  if (filters.status) return true;
  if (filters.scope_key) return true;
  if (hasTimeRange.value) return true;
  if (hasDurRange.value) return true;
  if (filters.log_level) return true;
  return false;
});

function toggleIncludeDescendants(): void {
  filters.include_descendants = !filters.include_descendants;
  // Re-issue the query so the new mode takes effect immediately;
  // otherwise the chip's state would be out of sync with the listing.
  void reload();
}

const timeRangeTitle = computed(() => {
  const after = filters.started_after.trim();
  const before = filters.started_before.trim();
  if (!after && !before) return "开始时间筛选";
  return `开始时间：${after || "*"} ~ ${before || "*"}`;
});

const durRangeTitle = computed(() => {
  const min = filters.duration_min_ms;
  const max = filters.duration_max_ms;
  const minOk = min != null && Number.isFinite(min);
  const maxOk = max != null && Number.isFinite(max);
  if (!minOk && !maxOk) return "耗时筛选（毫秒）";
  return `耗时：${minOk ? min : "*"}ms ~ ${maxOk ? max : "*"}ms`;
});

function toggleLogLevel(lvl: (typeof LOG_LEVELS)[number]): void {
  filters.log_level = filters.log_level === lvl ? "" : lvl;
}

function toggleTimePop(): void {
  durPopOpen.value = false;
  timePopOpen.value = !timePopOpen.value;
}

function toggleDurPop(): void {
  timePopOpen.value = false;
  durPopOpen.value = !durPopOpen.value;
}

function closePopovers(): void {
  timePopOpen.value = false;
  durPopOpen.value = false;
}

function commitPopAndReload(): void {
  closePopovers();
  void reload();
}

function clearTimeRange(): void {
  filters.started_after = "";
  filters.started_before = "";
}

function clearDurRange(): void {
  filters.duration_min_ms = null;
  filters.duration_max_ms = null;
}

function onDocPointerDown(e: PointerEvent | MouseEvent): void {
  if (!timePopOpen.value && !durPopOpen.value) return;
  const target = e.target as Node | null;
  if (!target) return;
  const el = target instanceof Element ? target : null;
  // Only swallow if the click is outside both the popover and its trigger.
  // .rt-filter-cell hosts the trigger button + popover for each range filter.
  if (el && el.closest(".rt-filter-cell")) return;
  closePopovers();
}

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
  // Backend guarantees a well-formed forest: every non-null
  // parent_span_id is present in ``items``. We still resolve through
  // an id-set so a span whose parent was unexpectedly absent surfaces
  // as a forest root rather than vanishing — a defensive fallback that
  // turns server bugs into a visible (but degraded) tree instead of a
  // silent data loss.
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
      nodeName: r.node_name ?? "",
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
  // ``offset`` is counted in root subtrees, not spans. ``loadedItems`` is
  // a flat array of spans across multiple pages, so we cannot use its
  // length — instead derive the next offset from the previous response.
  const nextOffset = append && resp.value ? resp.value.offset + resp.value.limit : 0;
  const p: ListSpansParams = {
    offset: nextOffset,
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
  if (filters.include_descendants) p.include_descendants = true;
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
  filters.include_descendants = false;
  closePopovers();
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

onMounted(() => {
  document.addEventListener("pointerdown", onDocPointerDown, true);
});

onUnmounted(() => {
  document.removeEventListener("pointerdown", onDocPointerDown, true);
});

</script>

<style scoped>
.spans-explorer {
  display: flex;
  flex-direction: column;
  gap: 8px;
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

.err {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, #fecaca 30%, transparent);
  color: #b91c1c;
  font-size: 12px;
}

.inline-err {
  margin: 0 0 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: color-mix(in srgb, #fecaca 35%, transparent);
  color: #b91c1c;
  font-size: 12px;
}

.tree-state {
  padding: 18px 12px;
  font-size: 11px;
  color: var(--muted);
  text-align: center;
  border-top: 1px dashed var(--border);
}

.pad {
  padding: 6px 0;
}

/* ---- Utility classes consumed by content rendered into the
   ExecutionLinkTree #toolbar / #filters slots. Scoped to this
   component so they only style this component's slot content. ---- */

.small {
  font-size: 11px;
}

.muted {
  color: var(--muted);
}

.spacer {
  flex: 1 1 auto;
}

.sep {
  color: var(--muted);
  font-size: 11px;
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

.btn {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
}

.btn:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  color: var(--accent);
}

.btn.small {
  padding: 2px 7px;
  font-size: 11px;
}

.btn.ghost {
  background: #fff;
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* Per-cell filter wrapper hosting the trigger button + anchored popover.
   The popover positions itself relative to this cell via run-trace.css. */
.rt-filter-cell {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* Log-level chip group span 2 grid columns so the four single-letter
   chips fit comfortably regardless of column width. */
.rt-log-chips {
  grid-column: 9 / span 2;
}

@media (max-width: 1100px) {
  .rt-log-chips {
    grid-column: auto;
  }
}
</style>
