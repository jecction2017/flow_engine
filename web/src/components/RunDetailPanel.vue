<template>
  <div class="run-detail">
    <header class="rd-head">
      <div class="rd-title">
        <span class="rd-id mono">#{{ detail.id }}</span>
        <span class="rd-flow mono">{{ detail.flow_code }}</span>
        <span class="rd-ver">v{{ detail.ver_no }}</span>
        <span class="badge mode">{{ detail.mode }}</span>
        <span class="badge" :class="statusBadgeClass(detail.status)">{{ detail.status }}</span>
        <span v-if="elapsedText" class="muted">· {{ elapsedText }}</span>
        <span v-if="detail.iteration_count != null" class="muted">· iter {{ detail.iteration_count }}</span>
      </div>
      <div class="rd-meta">
        <span v-if="detail.deployment_id" class="muted">deployment #{{ detail.deployment_id }}</span>
        <span v-if="detail.test_batch_id" class="muted">batch #{{ detail.test_batch_id }}</span>
        <span v-if="detail.worker_id" class="muted">worker {{ detail.worker_id }}</span>
        <span v-if="detail.started_at" class="muted" :title="detail.started_at">started {{ formatTs(detail.started_at) }}</span>
        <span v-if="detail.finished_at" class="muted" :title="detail.finished_at">finished {{ formatTs(detail.finished_at) }}</span>
      </div>
    </header>

    <p v-if="detail.error" class="err">{{ detail.error }}</p>

    <section v-if="hasNodeRuns" class="rd-section">
      <div class="rd-section-head">
        <span>节点执行时间线</span>
        <span class="muted">{{ rawRuns.length }} 个节点</span>
      </div>
      <div class="timeline">
        <div class="tl-toolbar">
          <button class="link" type="button" @click="expandAll">全部展开</button>
          <span class="sep">·</span>
          <button class="link" type="button" @click="collapseAll">全部折叠</button>
          <span class="sep">·</span>
          <span class="muted">日志级别</span>
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
          <button v-if="levelFilter.size > 0" type="button" class="link" @click="clearLevelFilter">清除</button>
        </div>
        <ul class="tl-rows">
          <template v-for="row in treeRows" :key="row.node_id">
            <li
              class="tl-row"
              :class="[
                statusClass(row.final_state),
                { 'is-branch': row.hasChildren, 'has-logs': (logCountsByNode.get(row.node_id) ?? 0) > 0 },
              ]"
              :title="rowTitle(row)"
            >
              <span class="tl-order">{{ row.order + 1 }}</span>
              <span class="tl-dot" />
              <span class="tl-name mono">
                <span class="tl-indent" aria-hidden="true">
                  <span v-for="(hasLine, i) in row.guides" :key="i" class="tl-guide" :class="{ on: hasLine }" />
                  <span v-if="row.depth > 0" class="tl-guide elbow">{{ row.isLast ? "└" : "├" }}</span>
                </span>
                <button
                  v-if="row.hasChildren"
                  type="button"
                  class="tl-caret"
                  :aria-expanded="!collapsed.has(row.node_id)"
                  @click="toggleCollapsed(row.node_id)"
                >
                  {{ collapsed.has(row.node_id) ? "▶" : "▼" }}
                </button>
                <span v-else class="tl-caret-spacer" />
                <span class="tl-id" :title="row.node_id">{{ row.node_id }}</span>
                <span v-if="row.iterations != null" class="tl-meta">× {{ row.iterations }}</span>
                <span v-else-if="row.execution_count && row.execution_count > 1" class="tl-meta">× {{ row.execution_count }}</span>
                <button
                  v-if="(logCountsByNode.get(row.node_id) ?? 0) > 0"
                  type="button"
                  class="tl-logs-btn"
                  :aria-expanded="openLogsFor === row.node_id"
                  @click="toggleLogDrawer(row.node_id)"
                >
                  📝 {{ logCountsByNode.get(row.node_id) }}
                </button>
              </span>
              <div class="tl-track">
                <div class="tl-bar" :style="barStyle(row)">
                  <span class="tl-bar-label">{{ formatDuration(row.duration_ms) }}</span>
                </div>
              </div>
              <span class="tl-status">{{ row.final_state }}</span>
            </li>
            <li v-if="openLogsFor === row.node_id" :key="row.node_id + ':logs'" class="tl-logs-drawer">
              <div class="tl-logs-head">
                <span>{{ row.node_id }} 日志</span>
                <span class="muted">
                  共 {{ logCountsByNode.get(row.node_id) }} 条
                  <template v-if="levelFilter.size > 0">
                    · 已过滤 {{ filteredLogsFor(row.node_id).length }} 条
                  </template>
                </span>
              </div>
              <ul v-if="filteredLogsFor(row.node_id).length" class="logs-list mono">
                <li
                  v-for="(entry, i) in filteredLogsFor(row.node_id)"
                  :key="i"
                  class="log-row"
                  :class="`lvl-${entry.level}`"
                >
                  <span class="log-ts">+{{ entry.ts_ms }}ms</span>
                  <span class="log-lvl">{{ entry.level }}</span>
                  <span class="log-src" :title="`来源: ${entry.source}`">
                    {{ entry.source }}<span v-if="entry.attempt" class="log-attempt">#{{ entry.attempt }}</span>
                  </span>
                  <span class="log-msg">{{ entry.message }}</span>
                  <span v-if="entry.truncated" class="log-trunc">…</span>
                </li>
              </ul>
              <div v-else class="muted tl-logs-empty">当前过滤条件下没有可显示的日志</div>
            </li>
          </template>
        </ul>
      </div>
    </section>

    <section v-else-if="hasNodeStats" class="rd-section">
      <div class="rd-section-head">
        <span>节点聚合统计（resident）</span>
        <span v-if="detail.node_stats?.last_updated_at" class="muted">
          last_updated_at {{ formatTs(detail.node_stats.last_updated_at) }}
        </span>
      </div>
      <table class="stats-table">
        <thead>
          <tr>
            <th>节点</th>
            <th>执行次数</th>
            <th class="ok">成功</th>
            <th class="bad">失败</th>
            <th>平均耗时</th>
            <th>p99 耗时</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in statsRows" :key="row.node_id">
            <td class="mono">{{ row.node_id }}</td>
            <td>{{ row.count }}</td>
            <td class="ok">{{ row.success }}</td>
            <td class="bad">{{ row.failed }}</td>
            <td>{{ formatDuration(row.avg_ms) }}</td>
            <td>{{ formatDuration(row.p99_ms) }}</td>
          </tr>
          <tr v-if="statsRows.length === 0">
            <td colspan="6" class="muted center">暂无统计</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-else class="rd-section">
      <div class="rd-section-head">
        <span>节点执行时间线</span>
      </div>
      <p class="muted center pad">运行尚未结束或无节点数据</p>
    </section>

    <section v-if="flowLogs.length" class="rd-section">
      <div class="rd-section-head">
        <span>流程级日志</span>
        <span class="muted">{{ flowLogs.length }} 条</span>
      </div>
      <ul v-if="filteredFlowLogs.length" class="logs-list mono">
        <li
          v-for="(entry, i) in filteredFlowLogs"
          :key="i"
          class="log-row"
          :class="`lvl-${entry.level}`"
        >
          <span class="log-ts">+{{ entry.ts_ms }}ms</span>
          <span class="log-lvl">{{ entry.level }}</span>
          <span class="log-src">{{ entry.source }}</span>
          <span class="log-msg">{{ entry.message }}</span>
        </li>
      </ul>
      <div v-else class="muted tl-logs-empty">当前过滤条件下没有可显示的日志</div>
    </section>

    <section v-if="detail.trigger_context" class="rd-section">
      <div class="rd-section-head">
        <span>触发上下文（trigger_context）</span>
      </div>
      <pre class="ctx mono">{{ triggerCtxText }}</pre>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import type { LogEntry, NodeRunInfo } from "@/api/flows";
import type { FlowRunDetail } from "@/api/flowRuns";

const ALL_LOG_LEVELS = ["debug", "info", "warn", "error"] as const;
type KnownLevel = (typeof ALL_LOG_LEVELS)[number];

type TreeRow = NodeRunInfo & {
  depth: number;
  hasChildren: boolean;
  isLast: boolean;
  guides: boolean[];
};

const props = defineProps<{ detail: FlowRunDetail }>();

const collapsed = reactive(new Set<string>());
const openLogsFor = ref<string | null>(null);
const levelFilter = reactive(new Set<KnownLevel>());

const rawRuns = computed<NodeRunInfo[]>(() => {
  const arr = props.detail.node_runs;
  if (Array.isArray(arr) && arr.length > 0) {
    return [...arr].sort((a, b) => a.order - b.order);
  }
  return [];
});

const hasNodeRuns = computed(() => rawRuns.value.length > 0);

const hasNodeStats = computed(() => {
  const ns = props.detail.node_stats;
  if (!ns || typeof ns !== "object") return false;
  const per = (ns as { per_node?: Record<string, unknown> }).per_node;
  return per != null && Object.keys(per).length > 0;
});

const statsRows = computed(() => {
  const ns = props.detail.node_stats;
  if (!ns?.per_node) return [];
  return Object.entries(ns.per_node).map(([node_id, rec]) => ({
    node_id,
    count: rec.count ?? 0,
    success: rec.success ?? 0,
    failed: rec.failed ?? 0,
    avg_ms: rec.avg_ms ?? 0,
    p99_ms: rec.p99_ms ?? 0,
  }));
});

const treeRows = computed<TreeRow[]>(() => {
  const runs = rawRuns.value;
  if (runs.length === 0) return [];
  const byId = new Map<string, NodeRunInfo>(runs.map((r) => [r.node_id, r]));
  const childrenByParent = new Map<string | null, string[]>();
  for (const r of runs) {
    const pid = r.parent_id ?? null;
    const key = pid && byId.has(pid) ? pid : null;
    if (!childrenByParent.has(key)) childrenByParent.set(key, []);
    childrenByParent.get(key)!.push(r.node_id);
  }
  for (const arr of childrenByParent.values()) {
    arr.sort((a, b) => byId.get(a)!.order - byId.get(b)!.order);
  }

  const out: TreeRow[] = [];
  const walk = (ids: string[], depth: number, ancestorGuides: boolean[]) => {
    ids.forEach((id, idx) => {
      const run = byId.get(id)!;
      const isLast = idx === ids.length - 1;
      const childIds = childrenByParent.get(id) ?? [];
      out.push({
        ...run,
        depth,
        hasChildren: childIds.length > 0,
        isLast,
        guides: [...ancestorGuides],
      });
      if (childIds.length > 0 && !collapsed.has(id)) {
        walk(childIds, depth + 1, [...ancestorGuides, !isLast]);
      }
    });
  };
  walk(childrenByParent.get(null) ?? [], 0, []);
  return out;
});

const maxMs = computed(() => {
  let m = 1;
  for (const row of rawRuns.value) {
    if (row.finished_ms != null) m = Math.max(m, row.finished_ms);
    if (row.started_ms != null) m = Math.max(m, row.started_ms);
  }
  return Math.max(1, m);
});

const flowLogs = computed<LogEntry[]>(() => {
  const arr = props.detail.flow_logs;
  return Array.isArray(arr) ? arr : [];
});

const logCountsByNode = computed<Map<string, number>>(() => {
  const m = new Map<string, number>();
  for (const r of rawRuns.value) {
    m.set(r.node_id, Array.isArray(r.logs) ? r.logs.length : 0);
  }
  return m;
});

function entryMatchesFilter(e: LogEntry): boolean {
  if (levelFilter.size === 0) return true;
  return levelFilter.has(e.level as KnownLevel);
}

function filteredLogsFor(nid: string): LogEntry[] {
  const run = rawRuns.value.find((r) => r.node_id === nid);
  const all = Array.isArray(run?.logs) ? (run!.logs as LogEntry[]) : [];
  return all.filter(entryMatchesFilter);
}

const filteredFlowLogs = computed<LogEntry[]>(() => flowLogs.value.filter(entryMatchesFilter));

function toggleLevelFilter(lvl: KnownLevel): void {
  if (levelFilter.has(lvl)) levelFilter.delete(lvl);
  else levelFilter.add(lvl);
}

function clearLevelFilter(): void {
  levelFilter.clear();
}

function toggleLogDrawer(nid: string): void {
  openLogsFor.value = openLogsFor.value === nid ? null : nid;
}

function toggleCollapsed(nid: string): void {
  if (collapsed.has(nid)) collapsed.delete(nid);
  else collapsed.add(nid);
}

function expandAll(): void {
  collapsed.clear();
}

function collapseAll(): void {
  for (const r of rawRuns.value) {
    const hasKids = rawRuns.value.some((c) => c.parent_id === r.node_id);
    if (hasKids) collapsed.add(r.node_id);
  }
}

function statusClass(st: string): string {
  if (st === "SUCCESS") return "ok";
  if (st === "FAILED") return "bad";
  if (st === "SKIPPED") return "skipped";
  if (st === "RUNNING" || st === "DISPATCHED" || st === "STAGING") return "running";
  return "info";
}

function statusBadgeClass(st: string): string {
  if (st === "completed") return "ok";
  if (st === "failed") return "bad";
  if (st === "terminated") return "warn";
  if (st === "running") return "running";
  return "info";
}

function barStyle(row: NodeRunInfo): Record<string, string> {
  const total = maxMs.value;
  const start = row.started_ms ?? row.first_seen_ms ?? 0;
  const end = row.finished_ms ?? (row.started_ms != null ? Math.max(row.started_ms, total) : start);
  const leftPct = Math.max(0, Math.min(100, (start / total) * 100));
  const rawWidth = ((end - start) / total) * 100;
  const widthPct = Math.max(2, Math.min(100 - leftPct, rawWidth));
  return { left: `${leftPct}%`, width: `${widthPct}%` };
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

const elapsedText = computed(() => {
  const a = props.detail.started_at ? Date.parse(props.detail.started_at) : NaN;
  const b = props.detail.finished_at ? Date.parse(props.detail.finished_at) : NaN;
  if (Number.isNaN(a) || Number.isNaN(b)) return "";
  const diff = b - a;
  if (diff < 0) return "";
  if (diff < 1000) return `${diff}ms`;
  if (diff < 60_000) return `${(diff / 1000).toFixed(2)}s`;
  return `${(diff / 60_000).toFixed(1)}min`;
});

const triggerCtxText = computed(() =>
  props.detail.trigger_context ? JSON.stringify(props.detail.trigger_context, null, 2) : "",
);

function rowTitle(row: NodeRunInfo): string {
  const parts = [`#${row.order + 1} ${row.node_id}`, `状态: ${row.final_state}`];
  if (row.started_ms != null) parts.push(`开始: +${row.started_ms}ms`);
  if (row.finished_ms != null) parts.push(`结束: +${row.finished_ms}ms`);
  parts.push(`耗时: ${formatDuration(row.duration_ms)}`);
  if (row.transitions?.length) {
    parts.push("轨迹: " + row.transitions.map((t) => `${t.state}@${t.t_ms}ms`).join(" → "));
  }
  return parts.join("\n");
}
</script>

<style scoped>
.run-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rd-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 10px 12px;
}

.rd-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 13px;
}

.rd-id {
  color: var(--muted);
  font-weight: 500;
}

.rd-flow {
  font-weight: 700;
}

.rd-ver {
  font-size: 11px;
  color: var(--muted);
  background: #f1f5f9;
  border-radius: 4px;
  padding: 1px 6px;
}

.rd-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 11px;
}

.muted {
  color: var(--muted);
  font-weight: 400;
  font-size: 11px;
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

.badge.mode {
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

.err {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, #fecaca 30%, transparent);
  color: #b91c1c;
  font-size: 12px;
  white-space: pre-wrap;
}

.rd-section {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  overflow: hidden;
}

.rd-section-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: #fbfdff;
}

.center {
  text-align: center;
}

.pad {
  padding: 16px 12px;
  margin: 0;
}

.timeline {
  display: flex;
  flex-direction: column;
}

.tl-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px dashed var(--border);
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

.sep {
  color: var(--muted);
}

.tl-rows {
  list-style: none;
  margin: 0;
  padding: 0;
}

.tl-row {
  display: grid;
  grid-template-columns: 22px 14px minmax(140px, 1.4fr) minmax(0, 3fr) 80px;
  gap: 8px;
  align-items: center;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}

.tl-row:last-child {
  border-bottom: none;
}

.tl-order {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  text-align: center;
  background: #f1f5f9;
  border-radius: 999px;
  padding: 1px 0;
  font-variant-numeric: tabular-nums;
}

.tl-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #cbd5e1;
  justify-self: center;
}

.tl-row.ok .tl-dot { background: #10b981; }
.tl-row.bad .tl-dot { background: #ef4444; }
.tl-row.skipped .tl-dot { background: #94a3b8; }
.tl-row.running .tl-dot {
  background: #3b82f6;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.55; transform: scale(0.85); }
}

.tl-name {
  display: flex;
  align-items: center;
  gap: 2px;
  overflow: hidden;
  white-space: nowrap;
  min-width: 0;
}

.tl-indent {
  display: inline-flex;
  align-items: stretch;
  flex: 0 0 auto;
  height: 16px;
}

.tl-guide {
  width: 12px;
  display: inline-flex;
  justify-content: center;
  align-items: center;
  position: relative;
  color: var(--border);
  font-size: 10px;
  line-height: 1;
}

.tl-guide.on::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 1px;
  background: color-mix(in srgb, var(--border) 80%, transparent);
}

.tl-guide.elbow {
  color: color-mix(in srgb, var(--border) 80%, transparent);
}

.tl-caret {
  background: none;
  border: none;
  padding: 0;
  width: 14px;
  height: 14px;
  font-size: 9px;
  color: var(--muted);
  cursor: pointer;
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.tl-caret-spacer {
  display: inline-block;
  width: 14px;
  flex: 0 0 auto;
}

.tl-id {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1 1 auto;
}

.tl-row.is-branch .tl-id {
  font-weight: 600;
}

.tl-meta {
  flex: 0 0 auto;
  font-size: 10px;
  font-weight: 600;
  color: #1d4ed8;
  background: color-mix(in srgb, #3b82f6 10%, transparent);
  border-radius: 4px;
  padding: 1px 5px;
  margin-left: 4px;
  font-variant-numeric: tabular-nums;
}

.tl-track {
  position: relative;
  height: 18px;
  background: linear-gradient(
    to right,
    rgba(15, 23, 42, 0.04) 0 1px,
    transparent 1px 25%,
    rgba(15, 23, 42, 0.04) 25% calc(25% + 1px),
    transparent calc(25% + 1px) 50%,
    rgba(15, 23, 42, 0.04) 50% calc(50% + 1px),
    transparent calc(50% + 1px) 75%,
    rgba(15, 23, 42, 0.04) 75% calc(75% + 1px),
    transparent calc(75% + 1px) 100%
  );
  border-radius: 4px;
}

.tl-bar {
  position: absolute;
  top: 2px;
  bottom: 2px;
  min-width: 4px;
  border-radius: 3px;
  background: #cbd5e1;
  display: flex;
  align-items: center;
  padding: 0 4px;
  overflow: hidden;
  box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.06);
}

.tl-bar-label {
  font-size: 10px;
  color: #fff;
  white-space: nowrap;
  text-shadow: 0 0 2px rgba(0, 0, 0, 0.35);
  font-variant-numeric: tabular-nums;
}

.tl-row.ok .tl-bar { background: linear-gradient(180deg, #34d399, #10b981); }
.tl-row.bad .tl-bar { background: linear-gradient(180deg, #f87171, #ef4444); }
.tl-row.skipped .tl-bar {
  background: repeating-linear-gradient(45deg, #cbd5e1 0 6px, #e2e8f0 6px 12px);
}
.tl-row.skipped .tl-bar-label { color: #475569; text-shadow: none; }
.tl-row.running .tl-bar { background: linear-gradient(180deg, #60a5fa, #3b82f6); }

.tl-status {
  font-size: 10px;
  color: var(--muted);
  text-align: right;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.tl-row.ok .tl-status { color: #047857; }
.tl-row.bad .tl-status { color: #b91c1c; }
.tl-row.running .tl-status { color: #1d4ed8; }

.tl-logs-btn {
  flex: 0 0 auto;
  margin-left: 6px;
  font-size: 10px;
  font-weight: 600;
  color: #1d4ed8;
  background: color-mix(in srgb, #3b82f6 10%, transparent);
  border: 1px solid color-mix(in srgb, #3b82f6 25%, transparent);
  border-radius: 4px;
  padding: 1px 6px;
  cursor: pointer;
}

.tl-logs-btn:hover {
  background: color-mix(in srgb, #3b82f6 18%, transparent);
}

.tl-row.has-logs .tl-id {
  color: color-mix(in srgb, var(--text) 90%, #1d4ed8);
}

.tl-logs-drawer {
  padding: 8px 10px 10px;
  background: #f8fafc;
  border-bottom: 1px solid var(--border);
}

.tl-logs-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 6px;
}

.tl-logs-empty {
  font-size: 11px;
  padding: 6px 12px;
}

.logs-list {
  list-style: none;
  margin: 0;
  padding: 0;
  background: #fff;
  max-height: 280px;
  overflow: auto;
}

.log-row {
  display: grid;
  grid-template-columns: 62px 46px 110px 1fr auto;
  gap: 8px;
  align-items: baseline;
  padding: 4px 10px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
  font-size: 11px;
  line-height: 1.45;
}

.log-row:last-child {
  border-bottom: none;
}

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

.log-attempt {
  color: #b45309;
  margin-left: 3px;
}

.log-msg {
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

.log-trunc {
  color: #b45309;
  font-weight: 700;
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

.stats-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.stats-table th,
.stats-table td {
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}

.stats-table th {
  background: #fbfdff;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
}

.stats-table tr:last-child td {
  border-bottom: none;
}

.stats-table .ok { color: #047857; }
.stats-table .bad { color: #b91c1c; }

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

.mono {
  font-family: var(--mono);
}
</style>
