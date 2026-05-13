<template>
  <div class="run-panel" :class="{ open: visible }">
    <header class="bar">
      <div class="title">
        <span>流程试运行</span>
        <span class="badge suppressed-inline" title="试运行固定为调试模式，副作用类内置函数默认抑制，不会触发真实生产副作用">
          副作用已抑制
        </span>
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
          {{ pending ? "运行中…" : "试运行" }}
        </button>
        <button class="btn ghost" @click="$emit('close')">关闭</button>
      </div>
    </header>

    <div class="grid">
      <section class="col">
        <div class="lbl">Profile 覆盖（可留空）</div>
        <select v-model="profileText" class="one-line mono">
          <option value="">使用全局默认（{{ defaultProfile || "default" }}）</option>
          <option v-for="p in profileOptions" :key="p" :value="p">{{ p }}</option>
        </select>
        <div class="lbl">initial_context 覆盖（JSON，可留空）</div>
        <textarea v-model="ctxText" class="area mono" rows="10" spellcheck="false" />
        <div class="lbl">runtime_patch（JSON，可留空）</div>
        <textarea v-model="runtimePatchText" class="area mono" rows="7" spellcheck="false" placeholder="{ }" />
        <details class="cap-details">
          <summary class="cap-sum">本次附加策略（可选，仅本次试运行）</summary>
          <div class="cap-hint">
            试运行固定为调试模式，副作用类内置函数默认抑制。此处仅对<strong>这一次试运行请求</strong>追加规则，可放行或填写重定向参数（由具体内置函数使用）。
            节点上的「副作用函数抑制规则」在流程里已持久化；此处为临时叠加。正式生产运行请创建部署。
          </div>
          <CapabilityRulesEditor v-model="capabilityPolicy" />
        </details>
        <p v-if="error" class="err">{{ error }}</p>
      </section>
      <section class="col timeline-col">
        <div class="lbl timeline-lbl">
          <span>节点执行时间线</span>
          <span v-if="response" class="muted">{{ rawRuns.length }} 条执行记录</span>
        </div>
        <div v-if="!response" class="hint">未运行</div>
        <div v-else-if="rawRuns.length === 0" class="hint">没有节点被调度</div>
        <ExecutionLinkTree
          v-else
          :rows="trialLinkRows"
          :timeline-min-ms="0"
          :timeline-max-ms="maxMs"
          :collapsed="collapsed"
          :secondary-open-key="openLogsFor"
          :detail-on-row-click="false"
          :log-button="true"
          :show-node-meta="false"
          @toggle-collapsed="toggleCollapsed"
          @toggle-secondary="toggleLogDrawer"
        >
          <template #toolbar>
            <button class="link" type="button" @click="expandAll">全部展开</button>
            <span class="sep">·</span>
            <button class="link" type="button" @click="collapseAll">全部折叠</button>
            <span class="sep">·</span>
            <span class="rt-filter-lbl">日志级别</span>
            <button
              v-for="lvl in LOG_LEVELS"
              :key="lvl"
              type="button"
              class="rt-chip-btn"
              :class="[`lvl-${lvl}`, { active: levelFilter.has(lvl) }]"
              @click="toggleLevelFilter(lvl)"
            >
              {{ lvl }}
            </button>
            <button v-if="levelFilter.size > 0" type="button" class="link" @click="clearLevelFilter">清除</button>
            <span v-if="levelFilter.size > 0" class="muted">命中 {{ filterHitCount }} / 总计 {{ rawRuns.length }}</span>
          </template>
          <template #secondary="{ row }">
            <div class="rt-logs-drawer">
              <div class="rt-logs-head">
                <span>{{ row.nodeId }} 日志</span>
                <span class="muted">
                  共 {{ logCountsByRunOrder.get(row.key) ?? 0 }} 条
                  <template v-if="levelFilter.size > 0">· 已过滤 {{ filteredLogsFor(row.key).length }} 条</template>
                </span>
              </div>
              <ul v-if="filteredLogsFor(row.key).length" class="rt-logs-list mono">
                <li
                  v-for="(entry, i) in filteredLogsFor(row.key)"
                  :key="i"
                  class="rt-log-row"
                  :class="`lvl-${entry.level}`"
                >
                  <span class="rt-log-ts">+{{ entry.ts_ms }}ms</span>
                  <span class="rt-log-lvl">{{ entry.level }}</span>
                  <span class="rt-log-src" :title="`来源: ${entry.source}`">
                    {{ entry.source }}<span v-if="entry.attempt" class="rt-log-attempt">#{{ entry.attempt }}</span>
                  </span>
                  <span class="rt-log-msg">{{ entry.message }}</span>
                  <span v-if="entry.truncated" class="rt-log-trunc" title="达到日志上限，后续条目被丢弃">...</span>
                </li>
              </ul>
              <div v-else class="muted rt-logs-empty">当前过滤条件下没有可显示的日志</div>
            </div>
          </template>
          <template #footer>
            <div v-if="trialLinkRows.length === 0" class="rt-filter-empty muted">
              当前日志级别筛选下没有执行记录
            </div>
            <section v-if="flowLogs.length" class="rt-flow-logs">
              <div class="rt-flow-logs-head">
                <span>流程级日志</span>
                <span class="muted">{{ flowLogs.length }} 条 · on_start / on_complete / on_failure</span>
              </div>
              <ul v-if="filteredFlowLogs.length" class="rt-logs-list mono">
                <li
                  v-for="(entry, i) in filteredFlowLogs"
                  :key="i"
                  class="rt-log-row"
                  :class="`lvl-${entry.level}`"
                >
                  <span class="rt-log-ts">+{{ entry.ts_ms }}ms</span>
                  <span class="rt-log-lvl">{{ entry.level }}</span>
                  <span class="rt-log-src" :title="`来源: ${entry.source}`">{{ entry.source }}</span>
                  <span class="rt-log-msg">{{ entry.message }}</span>
                  <span v-if="entry.truncated" class="rt-log-trunc" title="达到日志上限">...</span>
                </li>
              </ul>
              <div v-else class="muted rt-logs-empty">当前过滤条件下没有可显示的日志</div>
            </section>
          </template>
        </ExecutionLinkTree>
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
import { fetchProfileConfig } from "@/api/profiles";
import CapabilityRulesEditor from "@/components/CapabilityRulesEditor.vue";
import ExecutionLinkTree, { type ExecutionLinkRow } from "@/components/ExecutionLinkTree.vue";
import type { CapabilityRule } from "@/types/flow";

const LOG_LEVELS = ["debug", "info", "warn", "error"] as const;
type KnownLogLevel = (typeof LOG_LEVELS)[number];

function normalizeKnownLevel(level: string | undefined): KnownLogLevel | null {
  const s = typeof level === "string" ? level.trim().toLowerCase() : "";
  return (LOG_LEVELS as readonly string[]).includes(s) ? (s as KnownLogLevel) : null;
}

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
}>();
defineEmits<{ (e: "close"): void }>();

const ctxText = ref("");
const profileText = ref("");
const profileOptions = ref<string[]>(["default"]);
const defaultProfile = ref("default");
const runtimePatchText = ref("");
const merge = ref(true);
const timeoutSec = ref(30);
const pending = ref(false);
const response = ref<RunFlowResponse | null>(null);
const error = ref<string | null>(null);
// 试运行临时附加策略（高级）；服务端永远 RunMode.DEBUG，此处只能 ALLOW / REDIRECT。
const capabilityPolicy = ref<CapabilityRule[]>([]);
const collapsed = reactive(new Set<string>());
/** id of the currently open log drawer, or null when none is open. */
const openLogsFor = ref<string | null>(null);
/** Active log-level filter. Empty set = show all. */
const levelFilter = reactive(new Set<KnownLogLevel>());

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

void (async () => {
  try {
    const res = await fetchProfileConfig();
    defaultProfile.value = res.default_profile || "default";
    profileOptions.value = Array.isArray(res.profiles) && res.profiles.length ? [...res.profiles] : ["default"];
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

/** Parent row key: ``parent_order`` when present, else latest preceding row with ``parent_id``. */
function resolveParentRunKey(r: NodeRunInfo, sorted: NodeRunInfo[]): string | null {
  const po = r.parent_order;
  if (po != null && Number.isFinite(Number(po))) {
    return String(po);
  }
  const pid = r.parent_id?.trim();
  if (!pid) return null;
  for (let i = sorted.length - 1; i >= 0; i--) {
    const cand = sorted[i]!;
    if (cand.order >= r.order) continue;
    if (cand.node_id === pid) return String(cand.order);
  }
  return null;
}

function runMatchesLevelFilter(run: NodeRunInfo): boolean {
  if (levelFilter.size === 0) return true;
  const all = Array.isArray(run.logs) ? run.logs : [];
  return all.some((e) => {
    const nk = normalizeKnownLevel(e.level);
    return nk != null && levelFilter.has(nk);
  });
}

/**
 * Flatten the parent/child tree (keys = ``order`` strings) so repeated
 * ``node_id`` across loop iterations stay distinct — aligned with persisted spans.
 */
const treeRows = computed<TreeRow[]>(() => {
  const runs = rawRuns.value;
  if (runs.length === 0) return [];
  const sorted = [...runs].sort((a, b) => a.order - b.order);
  const byOrder = new Map(sorted.map((rr) => [rr.order, rr]));
  const childrenByParent = new Map<string | null, number[]>();
  const parentByOrder = new Map<number, string | null>();
  for (const r of sorted) {
    const pk = resolveParentRunKey(r, sorted);
    parentByOrder.set(r.order, pk);
    if (!childrenByParent.has(pk)) childrenByParent.set(pk, []);
    childrenByParent.get(pk)!.push(r.order);
  }
  for (const arr of childrenByParent.values()) {
    arr.sort((a, b) => a - b);
  }
  let visibleOrderSet: Set<number> | null = null;
  if (levelFilter.size > 0) {
    visibleOrderSet = new Set<number>();
    for (const r of sorted) {
      if (!runMatchesLevelFilter(r)) continue;
      visibleOrderSet.add(r.order);
      let parentKey = parentByOrder.get(r.order) ?? null;
      while (parentKey != null) {
        const po = Number(parentKey);
        if (!Number.isFinite(po) || visibleOrderSet.has(po)) break;
        visibleOrderSet.add(po);
        parentKey = parentByOrder.get(po) ?? null;
      }
    }
  }
  const out: TreeRow[] = [];
  const walk = (orderIds: number[], depth: number, ancestorGuides: boolean[]) => {
    const visibleOrders = visibleOrderSet
      ? orderIds.filter((ord) => visibleOrderSet!.has(ord))
      : orderIds;
    visibleOrders.forEach((ord, idx) => {
      const run = byOrder.get(ord)!;
      const isLast = idx === visibleOrders.length - 1;
      const childOrders = childrenByParent.get(String(ord)) ?? [];
      out.push({
        ...run,
        depth,
        hasChildren: childOrders.length > 0,
        isLast,
        guides: [...ancestorGuides],
      });
      if (childOrders.length > 0 && !collapsed.has(String(ord))) {
        walk(childOrders, depth + 1, [...ancestorGuides, !isLast]);
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

function formatDur(ms: number | null): string {
  if (ms == null) return "-";
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatOffset(ms: number): string {
  if (ms < 1000) return `+${ms}ms`;
  if (ms < 60_000) return `+${(ms / 1000).toFixed(3)}s`;
  const mins = Math.floor(ms / 60_000);
  const sec = ((ms % 60_000) / 1000).toFixed(3);
  return `+${mins}m${sec}s`;
}

function formatDelta(ms: number): string {
  if (ms < 1000) return `Δ+${ms}ms`;
  if (ms < 60_000) return `Δ+${(ms / 1000).toFixed(3)}s`;
  const mins = Math.floor(ms / 60_000);
  const sec = ((ms % 60_000) / 1000).toFixed(3);
  return `Δ+${mins}m${sec}s`;
}

function trialTone(st: string): string {
  if (st === "SUCCESS") return "ok";
  if (st === "FAILED") return "bad";
  if (st === "SKIPPED") return "skipped";
  if (st === "RUNNING" || st === "DISPATCHED" || st === "STAGING") return "running";
  return "info";
}

const trialLinkRows = computed<ExecutionLinkRow[]>(() => {
  const m = maxMs.value;
  let prevStartedMs: number | null = null;
  return treeRows.value.map((tr) => {
    const start = tr.started_ms ?? tr.first_seen_ms ?? 0;
    const end = tr.finished_ms ?? (tr.started_ms != null ? Math.max(tr.started_ms, m) : start + 1);
    let startedDeltaDisplay: string | undefined;
    let startedDeltaTitle: string | undefined;
    if (tr.started_ms != null && prevStartedMs != null) {
      const delta = Math.max(0, tr.started_ms - prevStartedMs);
      startedDeltaDisplay = formatDelta(delta);
      startedDeltaTitle = `相对上一行开始时间 +${delta}ms`;
    }
    if (tr.started_ms != null) prevStartedMs = tr.started_ms;
    const badges: { label: string; title?: string }[] = [];
    if (tr.iterations != null) badges.push({ label: `×${tr.iterations}`, title: "迭代次数" });
    else     if (tr.execution_count && tr.execution_count > 1) {
      badges.push({ label: `×${tr.execution_count}`, title: "执行次数" });
    }
    const logCount = filteredLogsFor(String(tr.order)).length;
    return {
      key: String(tr.order),
      orderDisplay: String(tr.order + 1),
      depth: tr.depth,
      hasChildren: tr.hasChildren,
      isLast: tr.isLast,
      guides: tr.guides,
      nodeId: tr.node_id,
      nodeType: "",
      scopeKey: "",
      startedDisplay: tr.started_ms != null ? formatOffset(tr.started_ms) : "—",
      startedTitle: tr.started_ms != null ? `相对流程起点 +${tr.started_ms}ms` : undefined,
      startedDeltaDisplay,
      startedDeltaTitle,
      durationMs: tr.duration_ms,
      durationDisplay: formatDur(tr.duration_ms),
      statusLabel: tr.final_state,
      statusTone: trialTone(tr.final_state),
      filterMatch: levelFilter.size > 0 && logCount > 0,
      logCount,
      barStartMs: start,
      barEndMs: Math.max(end, start + 1),
      metaBadges: badges.length ? badges : undefined,
    };
  });
});

const filterHitCount = computed(() =>
  levelFilter.size === 0 ? 0 : trialLinkRows.value.reduce((n, r) => n + (r.logCount > 0 ? 1 : 0), 0),
);

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

const logCountsByRunOrder = computed<Map<string, number>>(() => {
  const m = new Map<string, number>();
  for (const r of rawRuns.value) {
    m.set(String(r.order), Array.isArray(r.logs) ? r.logs.length : 0);
  }
  return m;
});

function entryMatchesFilter(e: LogEntry): boolean {
  if (levelFilter.size === 0) return true;
  const nk = normalizeKnownLevel(e.level);
  return nk != null && levelFilter.has(nk);
}

function filteredLogsFor(runOrderKey: string): LogEntry[] {
  const ord = Number(runOrderKey);
  const run = rawRuns.value.find((r) => r.order === ord);
  const all = Array.isArray(run?.logs) ? (run!.logs as LogEntry[]) : [];
  return all.filter(entryMatchesFilter);
}

const filteredFlowLogs = computed<LogEntry[]>(() =>
  flowLogs.value.filter(entryMatchesFilter),
);

function toggleLevelFilter(lvl: KnownLogLevel): void {
  if (levelFilter.has(lvl)) levelFilter.delete(lvl);
  else levelFilter.add(lvl);
}

function clearLevelFilter(): void {
  levelFilter.clear();
}

function toggleLogDrawer(runOrderKey: string): void {
  openLogsFor.value = openLogsFor.value === runOrderKey ? null : runOrderKey;
}

function toggleCollapsed(runOrderKey: string): void {
  if (collapsed.has(runOrderKey)) collapsed.delete(runOrderKey);
  else collapsed.add(runOrderKey);
}

function expandAll(): void {
  collapsed.clear();
}

function collapseAll(): void {
  const sorted = [...rawRuns.value].sort((a, b) => a.order - b.order);
  const parents = new Set<string>();
  for (const c of sorted) {
    const pk = resolveParentRunKey(c, sorted);
    if (pk != null) parents.add(pk);
  }
  parents.forEach((k) => collapsed.add(k));
}

function stateClass(state: string): string {
  if (state === "COMPLETED") return "ok";
  if (state === "FAILED") return "bad";
  if (state === "TERMINATED") return "warn";
  return "info";
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
      capability_policy: capabilityPolicy.value as unknown as Array<Record<string, unknown>>,
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

.badge.suppressed-inline {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 2px 7px;
  background: color-mix(in srgb, #f59e0b 18%, transparent);
  color: #92400e;
  border-color: color-mix(in srgb, #f59e0b 35%, transparent);
}

.cap-details {
  margin-top: 8px;
  border-top: 1px dashed var(--border);
  padding-top: 6px;
}

.cap-sum {
  font-size: 11px;
  color: var(--muted);
  cursor: pointer;
  user-select: none;
  padding: 2px 0;
}

.cap-sum:hover {
  color: var(--accent);
}

.cap-details[open] .cap-sum {
  margin-bottom: 6px;
  color: var(--text);
}

.cap-hint {
  font-size: 11px;
  line-height: 1.55;
  color: var(--muted);
  background: color-mix(in srgb, var(--accent-soft, #e0e7ff) 60%, #fff);
  border-radius: 6px;
  padding: 6px 10px;
  margin-bottom: 6px;
}

.cap-hint strong {
  color: var(--text);
  font-weight: 600;
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
