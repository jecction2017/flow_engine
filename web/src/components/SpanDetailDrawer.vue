<template>
  <aside class="span-drawer" :class="{ inline: layout === 'inline' }">
    <header class="sd-head">
      <div class="sd-title">
        <span class="sd-id mono">#{{ span.id }}</span>
        <span class="sd-node mono" :title="span.node_id">{{ span.node_id }}</span>
        <span class="badge type">{{ span.node_type }}</span>
        <span class="badge" :class="spanStatusClass(span.status)">{{ span.status }}</span>
        <button type="button" class="btn ghost small close-btn" @click="emit('close')">
          {{ layout === "inline" ? "收起" : "关闭" }}
        </button>
      </div>
      <div class="sd-meta">
        <span v-if="span.scope_key" class="muted" :title="`scope_key=${span.scope_key}`">
          scope <code class="mono">{{ span.scope_key }}</code>
        </span>
        <span v-if="span.started_at" class="muted" :title="span.started_at">
          开始 {{ formatTs(span.started_at) }}
        </span>
        <span v-if="span.finished_at" class="muted" :title="span.finished_at">
          结束 {{ formatTs(span.finished_at) }}
        </span>
        <span v-if="span.duration_ms != null" class="muted">耗时 {{ formatDuration(span.duration_ms) }}</span>
        <span v-if="!span.sampled" class="badge warn" title="未达到采样阈值，但因失败被强制留存">
          unsampled
        </span>
      </div>
      <div v-if="parentSpanId != null" class="sd-parent">
        <span class="muted">父 Span</span>
        <button type="button" class="link mono" @click="emit('navigate', parentSpanId)">#{{ parentSpanId }} ↑</button>
      </div>
    </header>

    <pre v-if="span.error" class="err mono">{{ span.error }}</pre>

    <section v-if="childSummaries.length" class="sd-section">
      <div class="sd-section-head">
        <span>直接子节点（{{ childSummaries.length }}）</span>
        <button
          type="button"
          class="link small"
          :disabled="loadingChildren"
          @click="loadChildren"
        >
          {{ loadingChildren ? "加载中…" : "查询完整子 Span" }}
        </button>
      </div>
      <table class="child-table">
        <thead>
          <tr>
            <th>node_id</th>
            <th style="width:90px">状态</th>
            <th style="width:90px">耗时</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(c, i) in childSummaries" :key="i">
            <td class="mono">{{ c.node_id }}</td>
            <td>
              <span class="tag" :class="spanStatusClass(c.status)">{{ c.status }}</span>
            </td>
            <td class="mono small">{{ formatDuration(c.duration_ms) }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="resolvedChildSpans.length" class="sd-section">
      <div class="sd-section-head">
        <span>子 Span 列表（{{ resolvedChildSpans.length }}）</span>
        <span class="muted">点击行进入子 Span</span>
      </div>
      <ul class="child-spans">
        <li
          v-for="cs in resolvedChildSpans"
          :key="cs.id"
          class="child-span-row"
          :class="spanStatusClass(cs.status)"
          @click="emit('navigate', cs.id)"
        >
          <span class="cs-id mono">#{{ cs.id }}</span>
          <span class="cs-node mono">{{ cs.node_id }}</span>
          <span class="tag small" :class="spanStatusClass(cs.status)">{{ cs.status }}</span>
          <span class="muted small">{{ formatDuration(cs.duration_ms) }}</span>
        </li>
      </ul>
    </section>

    <section v-if="hasLogs" class="sd-section">
      <div class="sd-section-head">
        <span>日志（{{ logs.length }} 条）</span>
        <div class="lvl-toolbar">
          <button
            v-for="lvl in ALL_LOG_LEVELS"
            :key="lvl"
            type="button"
            class="chip-btn"
            :class="[`lvl-${lvl}`, { active: levelFilter.has(lvl) }]"
            @click="toggleLevelFilter(lvl)"
          >
            {{ lvl }}
          </button>
          <button v-if="levelFilter.size > 0" type="button" class="link small" @click="clearLevelFilter">
            清除
          </button>
        </div>
      </div>
      <ul v-if="filteredLogs.length" class="logs-list mono">
        <li
          v-for="(entry, i) in filteredLogs"
          :key="i"
          class="log-row"
          :class="`lvl-${entry.level}`"
        >
          <span class="log-ts">+{{ entry.t_ms }}ms</span>
          <span class="log-lvl">{{ entry.level }}</span>
          <span class="log-src" :title="entry.source">{{ entry.source }}</span>
          <span class="log-msg">{{ entry.msg }}</span>
        </li>
      </ul>
      <div v-else class="muted center pad">当前过滤条件下没有可显示的日志</div>
    </section>

    <section v-if="hasAttrs" class="sd-section">
      <div class="sd-section-head">
        <span>attributes</span>
      </div>
      <pre class="ctx mono">{{ attributesText }}</pre>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import {
  getSpanChildren,
  type SpanChildSummary,
  type SpanDetail,
  type SpanLogEntry,
  type SpanStatus,
  type SpanSummary,
} from "@/api/spans";

const ALL_LOG_LEVELS = ["debug", "info", "warn", "error"] as const;
type KnownLevel = (typeof ALL_LOG_LEVELS)[number];

const props = withDefaults(defineProps<{ span: SpanDetail; layout?: "drawer" | "inline" }>(), {
  layout: "drawer",
});
const emit = defineEmits<{
  (e: "close"): void;
  (e: "navigate", spanId: number): void;
}>();

const levelFilter = reactive(new Set<KnownLevel>());
const loadingChildren = ref(false);
const resolvedChildSpans = ref<SpanSummary[]>([]);
const errorText = ref("");

watch(
  () => props.span.id,
  () => {
    resolvedChildSpans.value = [];
    errorText.value = "";
  },
);

const parentSpanId = computed(() => props.span.parent_span_id ?? null);

const childSummaries = computed<SpanChildSummary[]>(() => {
  return Array.isArray(props.span.child_spans) ? props.span.child_spans : [];
});

const logs = computed<SpanLogEntry[]>(() => {
  return Array.isArray(props.span.logs) ? props.span.logs : [];
});

const hasLogs = computed(() => logs.value.length > 0);
const hasAttrs = computed(() => {
  const a = props.span.attributes;
  return a != null && Object.keys(a).length > 0;
});

const filteredLogs = computed<SpanLogEntry[]>(() => {
  if (levelFilter.size === 0) return logs.value;
  return logs.value.filter((e) => levelFilter.has(e.level as KnownLevel));
});

const attributesText = computed(() => {
  const a = props.span.attributes;
  return a ? JSON.stringify(a, null, 2) : "";
});

function toggleLevelFilter(lvl: KnownLevel): void {
  if (levelFilter.has(lvl)) levelFilter.delete(lvl);
  else levelFilter.add(lvl);
}

function clearLevelFilter(): void {
  levelFilter.clear();
}

async function loadChildren(): Promise<void> {
  if (loadingChildren.value) return;
  loadingChildren.value = true;
  errorText.value = "";
  try {
    const resp = await getSpanChildren(props.span.id, 500);
    resolvedChildSpans.value = resp.items;
  } catch (e) {
    errorText.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingChildren.value = false;
  }
}

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
.span-drawer {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-left: 1px solid var(--border);
  background: var(--surface);
  min-width: 360px;
  max-width: 100%;
}

.span-drawer.inline {
  border-left: none;
  border-radius: 8px;
  min-width: 0;
  padding: 10px;
  background: #fff;
}

.sd-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}

.sd-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
}

.sd-id {
  color: var(--muted);
  font-weight: 500;
}

.sd-node {
  font-weight: 700;
}

.close-btn {
  margin-left: auto;
}

.sd-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 11px;
}

.sd-parent {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.muted {
  color: var(--muted);
}

.err {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, #fecaca 30%, transparent);
  color: #b91c1c;
  font-size: 12px;
  white-space: pre-wrap;
}

.badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.badge.type {
  background: color-mix(in srgb, #6366f1 12%, transparent);
  color: #4338ca;
  border-color: color-mix(in srgb, #6366f1 30%, transparent);
}

.badge.ok {
  background: color-mix(in srgb, #10b981 14%, transparent);
  color: #047857;
  border-color: color-mix(in srgb, #10b981 35%, transparent);
}

.badge.bad {
  background: color-mix(in srgb, #ef4444 14%, transparent);
  color: #b91c1c;
  border-color: color-mix(in srgb, #ef4444 35%, transparent);
}

.badge.warn {
  background: color-mix(in srgb, #f59e0b 18%, transparent);
  color: #92400e;
  border-color: color-mix(in srgb, #f59e0b 35%, transparent);
}

.badge.running {
  background: color-mix(in srgb, #3b82f6 14%, transparent);
  color: #1d4ed8;
  border-color: color-mix(in srgb, #3b82f6 35%, transparent);
}

.badge.skipped {
  background: color-mix(in srgb, #94a3b8 22%, transparent);
  color: #475569;
}

.sd-section {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.sd-section-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  background: #fbfdff;
}

.child-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.child-table th,
.child-table td {
  padding: 5px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}

.child-table th {
  background: #fbfdff;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
}

.child-table tr:last-child td {
  border-bottom: none;
}

.tag {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
  display: inline-block;
}

.tag.ok { background: color-mix(in srgb, #10b981 14%, transparent); color: #047857; }
.tag.bad { background: color-mix(in srgb, #ef4444 14%, transparent); color: #b91c1c; }
.tag.skipped { background: color-mix(in srgb, #94a3b8 22%, transparent); color: #475569; }
.tag.running { background: color-mix(in srgb, #3b82f6 14%, transparent); color: #1d4ed8; }

.child-spans {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 240px;
  overflow: auto;
}

.child-span-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  font-size: 12px;
}

.child-span-row:hover {
  background: #f1f5f9;
}

.child-span-row.bad { background: color-mix(in srgb, #fecaca 10%, transparent); }
.child-span-row:last-child { border-bottom: none; }

.cs-id { color: var(--muted); flex: 0 0 auto; }
.cs-node { flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.lvl-toolbar {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.chip-btn {
  text-transform: uppercase;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  border-radius: 999px;
  padding: 1px 8px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
  cursor: pointer;
}

.chip-btn.active.lvl-info { background: color-mix(in srgb, #3b82f6 18%, transparent); color: #1d4ed8; border-color: color-mix(in srgb, #3b82f6 35%, transparent); }
.chip-btn.active.lvl-warn { background: color-mix(in srgb, #f59e0b 22%, transparent); color: #92400e; border-color: color-mix(in srgb, #f59e0b 40%, transparent); }
.chip-btn.active.lvl-error { background: color-mix(in srgb, #ef4444 20%, transparent); color: #b91c1c; border-color: color-mix(in srgb, #ef4444 35%, transparent); }
.chip-btn.active.lvl-debug { background: color-mix(in srgb, #94a3b8 22%, transparent); color: #475569; border-color: color-mix(in srgb, #94a3b8 40%, transparent); }

.logs-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 320px;
  overflow: auto;
}

.log-row {
  display: grid;
  grid-template-columns: 62px 46px 110px 1fr;
  gap: 8px;
  align-items: baseline;
  padding: 4px 10px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
  font-size: 11px;
  line-height: 1.45;
}

.log-row:last-child { border-bottom: none; }

.log-ts {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.log-lvl {
  text-transform: uppercase;
  font-weight: 700;
  font-size: 10px;
  letter-spacing: 0.04em;
  border-radius: 4px;
  padding: 1px 6px;
  background: #e2e8f0;
  color: #475569;
  text-align: center;
}

.log-row.lvl-info .log-lvl { background: color-mix(in srgb, #3b82f6 15%, transparent); color: #1d4ed8; }
.log-row.lvl-warn .log-lvl { background: color-mix(in srgb, #f59e0b 20%, transparent); color: #92400e; }
.log-row.lvl-error .log-lvl { background: color-mix(in srgb, #ef4444 18%, transparent); color: #b91c1c; }
.log-row.lvl-debug .log-lvl { background: color-mix(in srgb, #94a3b8 20%, transparent); color: #475569; }

.log-src {
  color: var(--muted);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-msg {
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

.ctx {
  margin: 0;
  padding: 10px 12px;
  font-size: 11px;
  line-height: 1.4;
  background: #0b1220;
  color: #e2e8f0;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 240px;
  overflow: auto;
}

.center { text-align: center; }
.pad { padding: 12px; }

.link {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  padding: 0;
  font-size: 11px;
}

.link.small { font-size: 11px; }
.link:hover { text-decoration: underline; }

.mono { font-family: var(--mono); }
</style>
