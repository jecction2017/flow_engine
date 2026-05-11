<template>
  <div class="spans-explorer">
    <div class="se-toolbar">
      <label class="ctl">
        <span>节点</span>
        <select v-model="filters.node_id" class="inp">
          <option value="">全部节点</option>
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
      <label class="ctl wide">
        <span>scope_key</span>
        <input
          v-model.trim="filters.scope_key"
          class="inp mono"
          placeholder="如 alert_id（精确匹配，回车搜索）"
          @keyup.enter="reload"
        />
      </label>
      <button type="button" class="btn ghost small" :disabled="loading" @click="reload">
        {{ loading ? "查询中…" : "搜索" }}
      </button>
      <button v-if="hasFilters" type="button" class="link small" @click="resetFilters">重置</button>
      <span class="spacer" />
      <span class="muted small">
        共 {{ resp?.total ?? 0 }} 条 · 第 {{ Math.floor((resp?.offset ?? 0) / pageSize) + 1 }} 页
      </span>
      <button type="button" class="btn small ghost" :disabled="offset === 0" @click="prevPage">上一页</button>
      <button type="button" class="btn small ghost" :disabled="!hasNext" @click="nextPage">下一页</button>
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <table class="se-table">
      <thead>
        <tr>
          <th style="width:64px">span_id</th>
          <th style="width:48px">seq</th>
          <th>node_id</th>
          <th style="width:90px">类型</th>
          <th style="width:90px">状态</th>
          <th>scope_key</th>
          <th style="width:170px">started_at</th>
          <th style="width:90px">耗时</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="loading">
          <td colspan="8" class="muted center">加载中…</td>
        </tr>
        <tr v-else-if="!items.length">
          <td colspan="8" class="muted center">没有匹配的 Span</td>
        </tr>
        <tr
          v-for="s in items"
          :key="s.id"
          :class="[spanStatusClass(s.status), { active: selectedSpanId === s.id }]"
          @click="openSpan(s.id)"
        >
          <td class="mono">#{{ s.id }}</td>
          <td class="mono small">{{ s.span_seq }}</td>
          <td class="mono" :title="s.node_id">{{ s.node_id }}</td>
          <td><span class="tag type">{{ s.node_type }}</span></td>
          <td><span class="tag" :class="spanStatusClass(s.status)">{{ s.status }}</span></td>
          <td class="mono small scope-cell" :title="s.scope_key">{{ s.scope_key || "—" }}</td>
          <td class="mono small">{{ formatTs(s.started_at) }}</td>
          <td class="mono small">{{ formatDuration(s.duration_ms) }}</td>
        </tr>
      </tbody>
    </table>

    <Teleport v-if="selectedSpanDetail" to="body">
      <div class="se-drawer-overlay" @click.self="closeSpan">
        <div class="se-drawer-wrap">
          <SpanDetailDrawer
            :span="selectedSpanDetail"
            @close="closeSpan"
            @navigate="openSpan"
          />
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import {
  getSpan,
  listDeployRunSpans,
  listTestRunSpans,
  type SpanDetail,
  type SpanStatus,
  type SpansListResponse,
} from "@/api/spans";
import SpanDetailDrawer from "@/components/SpanDetailDrawer.vue";

const props = defineProps<{
  /** Exactly one of `deployRunId` / `testRunId` must be set. */
  deployRunId?: number;
  testRunId?: number;
  /** Page size — defaults to 50, the backend max is 500. */
  pageSize?: number;
}>();

const pageSize = computed(() => props.pageSize ?? 50);

const filters = reactive<{
  node_id: string;
  status: string;
  scope_key: string;
}>({
  node_id: "",
  status: "",
  scope_key: "",
});

const loading = ref(false);
const error = ref("");
const resp = ref<SpansListResponse | null>(null);
const offset = ref(0);

const selectedSpanId = ref<number | null>(null);
const selectedSpanDetail = ref<SpanDetail | null>(null);

const items = computed(() => resp.value?.items ?? []);
const nodeOptions = computed(() => resp.value?.node_ids ?? []);

const hasNext = computed(() => {
  if (!resp.value) return false;
  return offset.value + items.value.length < resp.value.total;
});

const hasFilters = computed(
  () => !!filters.node_id || !!filters.status || !!filters.scope_key,
);

async function reload(): Promise<void> {
  loading.value = true;
  error.value = "";
  const params = {
    node_id: filters.node_id || undefined,
    status: filters.status || undefined,
    scope_key: filters.scope_key || undefined,
    offset: offset.value,
    limit: pageSize.value,
  };
  try {
    if (props.deployRunId != null) {
      resp.value = await listDeployRunSpans(props.deployRunId, params);
    } else if (props.testRunId != null) {
      resp.value = await listTestRunSpans(props.testRunId, params);
    } else {
      throw new Error("SpansExplorer 必须提供 deployRunId 或 testRunId");
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function resetFilters(): void {
  filters.node_id = "";
  filters.status = "";
  filters.scope_key = "";
  offset.value = 0;
  void reload();
}

function prevPage(): void {
  offset.value = Math.max(0, offset.value - pageSize.value);
  void reload();
}

function nextPage(): void {
  if (!hasNext.value) return;
  offset.value += pageSize.value;
  void reload();
}

async function openSpan(spanId: number): Promise<void> {
  selectedSpanId.value = spanId;
  try {
    selectedSpanDetail.value = await getSpan(spanId);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    selectedSpanDetail.value = null;
  }
}

function closeSpan(): void {
  selectedSpanId.value = null;
  selectedSpanDetail.value = null;
}

// Re-query when explicit dropdown filters change (scope_key is
// keyboard-driven via Enter / 搜索 button to avoid hammering the API).
watch(
  () => [filters.node_id, filters.status],
  () => {
    offset.value = 0;
    void reload();
  },
);

// Re-query when the parent switches runs.
watch(
  () => [props.deployRunId, props.testRunId],
  () => {
    offset.value = 0;
    resp.value = null;
    closeSpan();
    void reload();
  },
);

onMounted(() => {
  void reload();
});

function spanStatusClass(st: SpanStatus): string {
  if (st === "success") return "ok";
  if (st === "failed") return "bad";
  if (st === "skipped") return "skipped";
  if (st === "running") return "running";
  return "info";
}

function formatDuration(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTs(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}
</script>

<style scoped>
.spans-explorer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.se-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: end;
  padding: 8px 4px;
  border-bottom: 1px dashed var(--border);
}

.ctl {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: var(--muted);
}

.ctl.wide {
  flex: 1 1 200px;
  min-width: 180px;
}

.ctl .inp {
  font-size: 12px;
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
}

.spacer { flex: 1 1 auto; }

.se-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  background: var(--surface);
}

.se-table th,
.se-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}

.se-table th {
  background: #fbfdff;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  position: sticky;
  top: 0;
}

.se-table tbody tr {
  cursor: pointer;
}

.se-table tbody tr:hover {
  background: #f1f5f9;
}

.se-table tr.active {
  background: color-mix(in srgb, #3b82f6 10%, transparent) !important;
}

.se-table tr.bad {
  background: color-mix(in srgb, #fecaca 10%, transparent);
}

.scope-cell {
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
}

.tag.type {
  background: color-mix(in srgb, #6366f1 12%, transparent);
  color: #4338ca;
  border-color: color-mix(in srgb, #6366f1 30%, transparent);
}

.tag.ok { background: color-mix(in srgb, #10b981 14%, transparent); color: #047857; }
.tag.bad { background: color-mix(in srgb, #ef4444 14%, transparent); color: #b91c1c; }
.tag.skipped { background: color-mix(in srgb, #94a3b8 22%, transparent); color: #475569; }
.tag.running { background: color-mix(in srgb, #3b82f6 14%, transparent); color: #1d4ed8; }

.muted { color: var(--muted); }
.center { text-align: center; }

.link {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  padding: 0;
  font-size: 11px;
}

.link:hover { text-decoration: underline; }

.err {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, #fecaca 30%, transparent);
  color: #b91c1c;
  font-size: 12px;
}

.mono { font-family: var(--mono); }

.se-drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}

.se-drawer-wrap {
  width: min(720px, 92vw);
  height: 100%;
  background: var(--surface);
  overflow: auto;
  box-shadow: -8px 0 24px rgba(15, 23, 42, 0.12);
}
</style>
