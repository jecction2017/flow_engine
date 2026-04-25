<template>
  <div class="run-panel" :class="{ open: visible }">
    <header class="bar">
      <div class="title">
        <span>流程运行结果</span>
        <span v-if="response" class="badge" :class="stateClass(response.state)">{{ response.state }}</span>
        <span v-if="response" class="muted">· {{ response.elapsed_ms }}ms</span>
        <template v-if="summary">
          <span class="chip ok" :title="'成功节点'">✓ {{ summary.ok }}</span>
          <span v-if="summary.failed" class="chip bad" :title="'失败节点'">✗ {{ summary.failed }}</span>
          <span v-if="summary.skipped" class="chip skipped" :title="'跳过节点'">⊘ {{ summary.skipped }}</span>
          <span v-if="summary.running" class="chip running" :title="'未完成节点'">◌ {{ summary.running }}</span>
        </template>
      </div>
      <div class="actions">
        <label class="opt">
          <input v-model="merge" type="checkbox" /> 合并 initial_context
        </label>
        <label class="opt">
          超时(s)
          <input v-model.number="timeoutSec" type="number" min="1" max="600" step="1" />
        </label>
        <button class="btn primary" :disabled="pending || !flowId" @click="run">
          {{ pending ? "运行中…" : "运行" }}
        </button>
        <button class="btn ghost" @click="$emit('close')">关闭</button>
      </div>
    </header>

    <div class="grid">
      <section class="col">
        <div class="lbl">Profile 覆盖（可留空）</div>
        <select v-model="profileText" class="one-line mono">
          <option value="">使用流程默认（{{ props.defaultProfile || "default" }}）</option>
          <option v-for="p in profileOptions" :key="p" :value="p">{{ p }}</option>
        </select>
        <div class="lbl">initial_context 覆盖（JSON，可留空）</div>
        <textarea v-model="ctxText" class="area mono" rows="10" spellcheck="false" />
        <div class="lbl">runtime_patch（JSON，可留空）</div>
        <textarea v-model="runtimePatchText" class="area mono" rows="7" spellcheck="false" placeholder="{ }" />
        <p v-if="error" class="err">{{ error }}</p>
      </section>
      <section class="col timeline-col">
        <div class="lbl timeline-lbl">
          <span>节点执行时间线</span>
          <span v-if="response" class="muted">{{ rawRuns.length }} 个节点</span>
        </div>
        <div v-if="!response" class="hint">未运行</div>
        <div v-else-if="rawRuns.length === 0" class="hint">没有节点被调度</div>
        <div v-else class="timeline">
          <div class="tl-axis">
            <span class="tl-axis-pad" />
            <span class="tl-axis-pad" />
            <span class="tl-axis-pad" />
            <div class="tl-axis-ticks">
              <span>0ms</span>
              <span>{{ Math.round(maxMs / 2) }}ms</span>
              <span>{{ maxMs }}ms</span>
            </div>
            <span class="tl-axis-pad" />
          </div>
          <div class="tl-toolbar">
            <button class="link" type="button" @click="expandAll">全部展开</button>
            <span class="sep">·</span>
            <button class="link" type="button" @click="collapseAll">全部折叠</button>
            <span class="sep">·</span>
            <span class="tl-filter-lbl">日志级别</span>
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
            <button
              v-if="levelFilter.size > 0"
              type="button"
              class="link"
              @click="clearLevelFilter"
            >
              清除
            </button>
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
                    <span
                      v-for="(hasLine, i) in row.guides"
                      :key="i"
                      class="tl-guide"
                      :class="{ on: hasLine }"
                    />
                    <span v-if="row.depth > 0" class="tl-guide elbow">
                      {{ row.isLast ? "└" : "├" }}
                    </span>
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
                  <span v-if="row.iterations != null" class="tl-meta" title="迭代次数">
                    × {{ row.iterations }}
                  </span>
                  <span
                    v-else-if="row.execution_count && row.execution_count > 1"
                    class="tl-meta"
                    title="执行次数"
                  >
                    × {{ row.execution_count }}
                  </span>
                  <button
                    v-if="(logCountsByNode.get(row.node_id) ?? 0) > 0"
                    type="button"
                    class="tl-logs-btn"
                    :aria-expanded="openLogsFor === row.node_id"
                    :title="`展开 / 折叠 ${row.node_id} 的日志`"
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
              <li
                v-if="openLogsFor === row.node_id"
                :key="row.node_id + ':logs'"
                class="tl-logs-drawer"
              >
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
                    <span v-if="entry.truncated" class="log-trunc" title="达到日志上限，后续条目被丢弃">…</span>
                  </li>
                </ul>
                <div v-else class="muted tl-logs-empty">
                  当前过滤条件下没有可显示的日志
                </div>
              </li>
            </template>
          </ul>
          <section v-if="flowLogs.length" class="flow-logs">
            <div class="flow-logs-head">
              <span>流程级日志</span>
              <span class="muted">{{ flowLogs.length }} 条 · on_start / on_complete / on_failure</span>
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
                <span class="log-src" :title="`来源: ${entry.source}`">{{ entry.source }}</span>
                <span class="log-msg">{{ entry.message }}</span>
                <span v-if="entry.truncated" class="log-trunc" title="达到日志上限">…</span>
              </li>
            </ul>
            <div v-else class="muted tl-logs-empty">
              当前过滤条件下没有可显示的日志
            </div>
          </section>
        </div>
      </section>
      <section class="col">
        <div class="lbl">全局上下文（global_ns）</div>
        <div v-if="response" class="dict-meta">
          <span>profile: <code class="mono">{{ response.resolved_profile ?? "—" }}</code></span>
          <span>hash: <code class="mono">{{ response.resolved_hash ?? "—" }}</code></span>
          <span>modules: {{ response.resolved_modules?.length ?? 0 }}</span>
        </div>
        <pre class="out mono">{{ globalsText }}</pre>
        <p v-if="response?.message" class="msg">{{ response.message }}</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { runFlow } from "@/api/flows";
import type { LogEntry, NodeRunInfo, RunFlowResponse } from "@/api/flows";
import { fetchDictProfiles } from "@/api/dict";

const ALL_LOG_LEVELS = ["debug", "info", "warn", "error"] as const;
type KnownLevel = (typeof ALL_LOG_LEVELS)[number];

type TreeRow = NodeRunInfo & {
  depth: number;
  hasChildren: boolean;
  isLast: boolean;
  /**
   * Per-ancestor vertical guide lines (one per ancestor depth). ``true``
   * means the ancestor at that depth still has further siblings below,
   * so we should draw a continuing line; ``false`` means empty space.
   */
  guides: boolean[];
};

const props = defineProps<{
  flowId: string | null;
  visible: boolean;
  initialContext: Record<string, unknown> | null | undefined;
  defaultProfile?: string | null;
}>();
defineEmits<{ (e: "close"): void }>();

const ctxText = ref("");
const profileText = ref("");
const profileOptions = ref<string[]>(["default"]);
const runtimePatchText = ref("");
const merge = ref(true);
const timeoutSec = ref(30);
const pending = ref(false);
const response = ref<RunFlowResponse | null>(null);
const error = ref<string | null>(null);
const collapsed = reactive(new Set<string>());
/** id of the currently open log drawer, or null when none is open. */
const openLogsFor = ref<string | null>(null);
/** Active log-level filter. Empty set = show all. */
const levelFilter = reactive(new Set<KnownLevel>());

watch(
  () => props.initialContext,
  (v) => {
    ctxText.value = v ? JSON.stringify(v, null, 2) : "";
  },
  { immediate: true },
);

watch(
  () => props.flowId,
  () => {
    response.value = null;
    error.value = null;
    collapsed.clear();
    openLogsFor.value = null;
  },
);

watch(
  () => props.defaultProfile,
  (p) => {
    if (p && !profileOptions.value.includes(p)) profileOptions.value = [...profileOptions.value, p].sort();
  },
  { immediate: true },
);

void (async () => {
  try {
    const res = await fetchDictProfiles();
    if (Array.isArray(res.profiles) && res.profiles.length) {
      profileOptions.value = [...res.profiles];
    }
  } catch {
    // fallback keep default option only
  }
})();

const globalsText = computed(() =>
  response.value ? JSON.stringify(response.value.global_ns, null, 2) : "// 未运行",
);

// Raw per-node runs. If the backend didn't return `node_runs` (older server),
// fall back to synthesising rows from `node_state` so the UI stays useful
// against mixed deployments.
const rawRuns = computed<NodeRunInfo[]>(() => {
  const r = response.value;
  if (!r) return [];
  if (Array.isArray(r.node_runs) && r.node_runs.length > 0) {
    return [...r.node_runs].sort((a, b) => a.order - b.order);
  }
  const entries = Object.entries(r.node_state ?? {});
  return entries.map(([nid, st], i) => ({
    node_id: nid,
    order: i,
    first_seen_ms: 0,
    started_ms: null,
    finished_ms: null,
    duration_ms: null,
    final_state: st,
    parent_id: null,
    transitions: [],
  }));
});

/**
 * Flatten the parent/child tree into the exact display order so the template
 * can iterate a single list while still retaining visual hierarchy via the
 * ``depth`` and ``guides`` metadata we attach to each row.
 *
 * We intentionally render "depth-first, order-ascending" -- that matches how
 * a human reads the underlying YAML and keeps sibling nodes chronologically
 * adjacent within each parent group.
 */
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
  const r = response.value;
  if (!r) return 0;
  let m = r.elapsed_ms || 0;
  for (const row of rawRuns.value) {
    if (row.finished_ms != null) m = Math.max(m, row.finished_ms);
    if (row.started_ms != null) m = Math.max(m, row.started_ms);
  }
  return Math.max(1, m);
});

const summary = computed(() => {
  if (!response.value) return null;
  const s = { ok: 0, failed: 0, skipped: 0, running: 0 };
  for (const row of rawRuns.value) {
    const st = row.final_state;
    if (st === "SUCCESS") s.ok += 1;
    else if (st === "FAILED") s.failed += 1;
    else if (st === "SKIPPED") s.skipped += 1;
    else s.running += 1;
  }
  return s;
});

const flowLogs = computed<LogEntry[]>(() => {
  const r = response.value;
  return Array.isArray(r?.flow_logs) ? (r!.flow_logs as LogEntry[]) : [];
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

const filteredFlowLogs = computed<LogEntry[]>(() =>
  flowLogs.value.filter(entryMatchesFilter),
);

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

function stateClass(state: string): string {
  if (state === "COMPLETED") return "ok";
  if (state === "FAILED") return "bad";
  if (state === "TERMINATED") return "warn";
  return "info";
}

function statusClass(st: string): string {
  if (st === "SUCCESS") return "ok";
  if (st === "FAILED") return "bad";
  if (st === "SKIPPED") return "skipped";
  if (st === "RUNNING" || st === "DISPATCHED" || st === "STAGING") return "running";
  return "info";
}

function barStyle(row: NodeRunInfo): Record<string, string> {
  const total = maxMs.value;
  const start = row.started_ms ?? row.first_seen_ms ?? 0;
  const end =
    row.finished_ms ?? (row.started_ms != null ? Math.max(row.started_ms, total) : start);
  const leftPct = Math.max(0, Math.min(100, (start / total) * 100));
  // Always draw a minimum 2% width bar so instant nodes stay visible.
  const rawWidth = ((end - start) / total) * 100;
  const widthPct = Math.max(2, Math.min(100 - leftPct, rawWidth));
  return {
    left: `${leftPct}%`,
    width: `${widthPct}%`,
  };
}

function formatDuration(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function rowTitle(row: NodeRunInfo): string {
  const parts = [
    `#${row.order + 1} ${row.node_id}`,
    `状态: ${row.final_state}`,
  ];
  if (row.started_ms != null) parts.push(`开始: +${row.started_ms}ms`);
  if (row.finished_ms != null) parts.push(`结束: +${row.finished_ms}ms`);
  parts.push(`耗时: ${formatDuration(row.duration_ms)}`);
  if (row.transitions.length) {
    parts.push(
      "轨迹: " + row.transitions.map((t) => `${t.state}@${t.t_ms}ms`).join(" → "),
    );
  }
  return parts.join("\n");
}

async function run() {
  if (!props.flowId) return;
  error.value = null;
  let override: Record<string, unknown> | null = null;
  let runtimePatch: Record<string, unknown> | null = null;
  const raw = ctxText.value.trim();
  if (raw) {
    try {
      const parsed: unknown = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("initial_context 必须是一个 JSON 对象");
      }
      override = parsed as Record<string, unknown>;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return;
    }
  }
  const patchRaw = runtimePatchText.value.trim();
  if (patchRaw) {
    try {
      const parsed: unknown = JSON.parse(patchRaw);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("runtime_patch 必须是一个 JSON 对象");
      }
      runtimePatch = parsed as Record<string, unknown>;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return;
    }
  }
  pending.value = true;
  try {
    response.value = await runFlow(props.flowId, {
      initial_context: override,
      merge: merge.value,
      timeout_sec: timeoutSec.value,
      profile: profileText.value.trim() || null,
      runtime_patch: runtimePatch,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    pending.value = false;
  }
}
</script>

<style scoped>
.run-panel {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--surface);
  border-top: 1px solid var(--border);
  box-shadow: 0 -12px 28px rgba(15, 23, 42, 0.08);
  transform: translateY(100%);
  transition: transform 0.22s ease;
  max-height: 62vh;
  display: flex;
  flex-direction: column;
  z-index: 40;
}

.run-panel.open {
  transform: translateY(0);
}

.bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 13px;
  flex-wrap: wrap;
}

.badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
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

.chip {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  letter-spacing: 0.02em;
}

.chip.ok {
  background: color-mix(in srgb, #10b981 12%, transparent);
  color: #047857;
  border-color: color-mix(in srgb, #10b981 30%, transparent);
}

.chip.bad {
  background: color-mix(in srgb, #ef4444 12%, transparent);
  color: #b91c1c;
  border-color: color-mix(in srgb, #ef4444 30%, transparent);
}

.chip.skipped {
  background: color-mix(in srgb, #94a3b8 16%, transparent);
  color: #475569;
  border-color: color-mix(in srgb, #94a3b8 30%, transparent);
}

.chip.running {
  background: color-mix(in srgb, #3b82f6 12%, transparent);
  color: #1d4ed8;
  border-color: color-mix(in srgb, #3b82f6 30%, transparent);
}

.muted {
  color: var(--muted);
  font-weight: 400;
  font-size: 11px;
}

.actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.opt {
  font-size: 11px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 4px;
}

.opt input[type="number"] {
  width: 64px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 3px 6px;
  font-size: 11px;
}

.btn {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}

.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
}

.btn.primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.8fr) minmax(0, 1fr);
  gap: 12px;
  padding: 12px;
  overflow: hidden;
}

.col {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.lbl {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 6px;
}

.timeline-lbl {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.hint {
  font-size: 12px;
  color: var(--muted);
  padding: 8px;
}

.area,
.out {
  flex: 1;
  min-height: 0;
  border-radius: 10px;
  font-size: 11px;
  line-height: 1.45;
}

.one-line {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fbfdff;
  padding: 8px 10px;
  font-size: 12px;
  margin-bottom: 10px;
  outline: none;
}

.area {
  padding: 10px;
  border: 1px solid var(--border);
  background: #fbfdff;
  resize: none;
  outline: none;
}

.area:focus {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.out {
  margin: 0;
  padding: 10px;
  border: 1px dashed var(--border);
  background: #0b1220;
  color: #e2e8f0;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.dict-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: -2px 0 8px;
  color: var(--muted);
  font-size: 11px;
}

.err {
  color: #b91c1c;
  font-size: 11px;
  margin: 6px 0 0;
}

.msg {
  font-size: 11px;
  color: var(--muted);
  margin: 6px 0 0;
}

.timeline-col {
  min-width: 0;
}

.timeline {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}

.tl-axis {
  display: grid;
  grid-template-columns: 22px 14px minmax(110px, 1.4fr) minmax(0, 3fr) 70px;
  gap: 8px;
  align-items: center;
  padding: 4px 10px;
  border-bottom: 1px dashed var(--border);
  font-size: 10px;
  color: var(--muted);
}

.tl-axis-pad {
  min-width: 0;
}

.tl-axis-ticks {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  font-variant-numeric: tabular-nums;
}

.tl-axis-ticks > span:nth-child(1) {
  text-align: left;
}

.tl-axis-ticks > span:nth-child(2) {
  text-align: center;
}

.tl-axis-ticks > span:nth-child(3) {
  text-align: right;
}

.tl-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-bottom: 1px dashed var(--border);
  font-size: 11px;
}

.tl-toolbar .link {
  background: none;
  border: none;
  color: var(--accent, #2563eb);
  cursor: pointer;
  padding: 0;
  font-size: 11px;
}

.tl-toolbar .link:hover {
  text-decoration: underline;
}

.tl-toolbar .sep {
  color: var(--muted);
}

.tl-rows {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow: auto;
  flex: 1;
  min-height: 0;
}

.tl-row {
  display: grid;
  grid-template-columns: 22px 14px minmax(110px, 1.4fr) minmax(0, 3fr) 70px;
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

.tl-row.ok .tl-dot {
  background: #10b981;
}

.tl-row.bad .tl-dot {
  background: #ef4444;
}

.tl-row.skipped .tl-dot {
  background: #94a3b8;
}

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
  color: var(--border, #e2e8f0);
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
  background: color-mix(in srgb, var(--border, #e2e8f0) 80%, transparent);
}

.tl-guide.elbow {
  color: color-mix(in srgb, var(--border, #e2e8f0) 80%, transparent);
  font-family: ui-monospace, monospace;
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

.tl-caret:hover {
  color: var(--text, #0f172a);
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

.tl-row.ok .tl-bar {
  background: linear-gradient(180deg, #34d399, #10b981);
}

.tl-row.bad .tl-bar {
  background: linear-gradient(180deg, #f87171, #ef4444);
}

.tl-row.skipped .tl-bar {
  background: repeating-linear-gradient(
    45deg,
    #cbd5e1 0 6px,
    #e2e8f0 6px 12px
  );
}

.tl-row.skipped .tl-bar-label {
  color: #475569;
  text-shadow: none;
}

.tl-row.running .tl-bar {
  background: linear-gradient(180deg, #60a5fa, #3b82f6);
}

.tl-status {
  font-size: 10px;
  color: var(--muted);
  text-align: right;
  font-weight: 600;
  letter-spacing: 0.02em;
}

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
  font-variant-numeric: tabular-nums;
}

.tl-logs-btn:hover {
  background: color-mix(in srgb, #3b82f6 18%, transparent);
}

.tl-row.has-logs .tl-id {
  color: color-mix(in srgb, var(--text, #0f172a) 90%, #1d4ed8);
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
  padding: 6px 0;
}

.logs-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  max-height: 240px;
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
  color: var(--text, #0f172a);
  white-space: pre-wrap;
  word-break: break-word;
}

.log-trunc {
  color: #b45309;
  font-weight: 700;
}

.flow-logs {
  padding: 8px 10px 10px;
  border-top: 1px dashed var(--border);
  background: #f8fafc;
}

.flow-logs-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 6px;
}

.tl-filter-lbl {
  color: var(--muted);
  margin-left: 4px;
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

.tl-row.ok .tl-status {
  color: #047857;
}

.tl-row.bad .tl-status {
  color: #b91c1c;
}

.tl-row.running .tl-status {
  color: #1d4ed8;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

@media (max-width: 960px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
