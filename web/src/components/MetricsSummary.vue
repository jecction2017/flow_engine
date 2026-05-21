<template>
  <div class="metrics-summary">
    <div class="ms-toolbar">
      <span class="muted small">统计窗口</span>
      <div class="window-pills">
        <button
          v-for="opt in WINDOW_OPTIONS"
          :key="opt.value"
          type="button"
          class="pill"
          :class="{ active: windowMinutes === opt.value }"
          @click="setWindow(opt.value)"
        >
          {{ opt.label }}
        </button>
      </div>
      <span class="spacer" />
      <button type="button" class="btn ghost small" :disabled="loading" @click="reload">
        {{ loading ? "刷新中…" : "刷新" }}
      </button>
      <label class="auto-refresh small">
        <input v-model="autoRefresh" type="checkbox" />
        <span>每 30s 自动刷新</span>
      </label>
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <div v-if="loading && nodes.length === 0" class="muted center pad">
      统计加载中…
    </div>
    <div v-else-if="!loading && nodes.length === 0" class="muted center pad">
      当前窗口内尚无聚合数据（subscription 流程刚启动需等待首个 5min 桶滚动）。
    </div>

    <div v-else class="ms-grid">
      <article v-for="node in nodes" :key="node.node_id" class="ms-card" :class="cardSeverity(node)">
        <header class="ms-head">
          <span class="ms-node mono" :title="node.node_id">{{ node.node_id }}</span>
          <span class="ms-rate" :class="rateClass(node.success_rate)">
            {{ formatRate(node.success_rate) }}
          </span>
        </header>
        <dl class="ms-kpis">
          <div>
            <dt>span_count</dt>
            <dd class="mono num">{{ formatNum(node.span_count) }}</dd>
          </div>
          <div>
            <dt>throughput</dt>
            <dd class="mono num">{{ formatThroughput(node.throughput_per_s) }}</dd>
          </div>
          <div>
            <dt>失败</dt>
            <dd class="mono num bad-num">{{ formatNum(node.failed_count) }}</dd>
          </div>
          <div>
            <dt>跳过</dt>
            <dd class="mono num">{{ formatNum(node.skipped_count) }}</dd>
          </div>
          <div>
            <dt>avg</dt>
            <dd class="mono num">{{ formatDuration(node.avg_ms) }}</dd>
          </div>
          <div>
            <dt>p50</dt>
            <dd class="mono num">{{ formatDuration(node.p50_ms) }}</dd>
          </div>
          <div>
            <dt>p95</dt>
            <dd class="mono num">{{ formatDuration(node.p95_ms) }}</dd>
          </div>
          <div>
            <dt>p99</dt>
            <dd class="mono num">{{ formatDuration(node.p99_ms) }}</dd>
          </div>
          <div>
            <dt>max</dt>
            <dd class="mono num">{{ formatDuration(node.max_ms) }}</dd>
          </div>
        </dl>
        <footer class="ms-foot">
          <button
            type="button"
            class="link small"
            @click="emit('drill', node.node_id)"
            :title="`查看 ${node.node_id} 的 Span 列表`"
          >
            查看 Span →
          </button>
        </footer>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  isMultiNodeSummary,
  queryMetricsSummary,
  type MetricsSummaryResponse,
  type NodeMetricSummary,
} from "@/api/metrics";

const WINDOW_OPTIONS: { label: string; value: number }[] = [
  { label: "5min", value: 5 },
  { label: "1h", value: 60 },
  { label: "6h", value: 360 },
  { label: "24h", value: 1440 },
];

const props = defineProps<{ deployRunId: number }>();
const emit = defineEmits<{ (e: "drill", nodeId: string): void }>();

const windowMinutes = ref<number>(60);
const loading = ref(false);
const error = ref("");
const nodes = ref<NodeMetricSummary[]>([]);
const autoRefresh = ref(true);
let timer: number | null = null;

async function reload(): Promise<void> {
  if (props.deployRunId == null) return;
  loading.value = true;
  error.value = "";
  try {
    const resp: MetricsSummaryResponse = await queryMetricsSummary(
      props.deployRunId,
      { window_minutes: windowMinutes.value },
    );
    if (isMultiNodeSummary(resp)) {
      nodes.value = sortNodes(resp.nodes);
    } else {
      nodes.value = sortNodes([resp]);
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function sortNodes(arr: NodeMetricSummary[]): NodeMetricSummary[] {
  // Surface problematic nodes first: failure_count desc, then span_count desc.
  return [...arr].sort((a, b) => {
    if (b.failed_count !== a.failed_count) return b.failed_count - a.failed_count;
    return b.span_count - a.span_count;
  });
}

function setWindow(v: number): void {
  if (windowMinutes.value === v) return;
  windowMinutes.value = v;
}

function startTimer(): void {
  stopTimer();
  if (!autoRefresh.value) return;
  timer = window.setInterval(() => {
    if (!loading.value) void reload();
  }, 30_000);
}

function stopTimer(): void {
  if (timer != null) {
    window.clearInterval(timer);
    timer = null;
  }
}

watch(windowMinutes, () => {
  void reload();
});

watch(
  () => props.deployRunId,
  () => {
    void reload();
  },
);

watch(autoRefresh, (on) => {
  if (on) startTimer();
  else stopTimer();
});

onMounted(() => {
  void reload();
  startTimer();
});

onBeforeUnmount(() => {
  stopTimer();
});

function cardSeverity(node: NodeMetricSummary): string {
  if (node.failed_count > 0) {
    const rate = node.success_rate;
    if (rate != null && rate < 0.9) return "sev-bad";
    return "sev-warn";
  }
  return "sev-ok";
}

function rateClass(rate: number | null): string {
  if (rate == null) return "muted";
  if (rate >= 0.99) return "ok";
  if (rate >= 0.9) return "warn";
  return "bad";
}

function formatRate(rate: number | null): string {
  if (rate == null) return "—";
  return `${(rate * 100).toFixed(rate < 0.99 ? 2 : 2)}%`;
}

function formatNum(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 10_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function formatThroughput(qps: number | null): string {
  if (qps == null || qps === 0) return "—";
  if (qps >= 1) return `${qps.toFixed(2)}/s`;
  const perMin = qps * 60;
  if (perMin >= 1) return `${perMin.toFixed(2)}/min`;
  const perHour = qps * 3600;
  return `${perHour.toFixed(1)}/h`;
}

function formatDuration(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}
</script>

<style scoped>
.metrics-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ms-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 4px;
  border-bottom: 1px dashed var(--border);
}

.window-pills {
  display: inline-flex;
  gap: 4px;
}

.pill {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
  border-radius: 999px;
  cursor: pointer;
}

.pill.active {
  background: color-mix(in srgb, #6366f1 14%, transparent);
  color: #4338ca;
  border-color: color-mix(in srgb, #6366f1 35%, transparent);
}

.auto-refresh {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--muted);
}

.spacer { flex: 1 1 auto; }

.err {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, #fecaca 30%, transparent);
  color: #b91c1c;
  font-size: 12px;
}

.muted { color: var(--muted); }
.center { text-align: center; }
.pad { padding: 16px; }

.ms-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
}

.ms-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  position: relative;
}

.ms-card.sev-bad { border-left: 4px solid #ef4444; }
.ms-card.sev-warn { border-left: 4px solid #f59e0b; }
.ms-card.sev-ok { border-left: 4px solid #10b981; }

.ms-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
}

.ms-node {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1 1 auto;
}

.ms-rate {
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  font-weight: 600;
}

.ms-rate.ok { color: #047857; }
.ms-rate.warn { color: #b45309; }
.ms-rate.bad { color: #b91c1c; }

.ms-kpis {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px 10px;
  margin: 0;
}

.ms-kpis > div {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.ms-kpis dt {
  font-size: 10px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ms-kpis dd {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.bad-num { color: #b91c1c; }

.ms-foot {
  border-top: 1px dashed var(--border);
  padding-top: 5px;
  text-align: right;
}

.link {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  padding: 0;
  font-size: 11px;
}

.link:hover { text-decoration: underline; }

.mono { font-family: var(--mono); }
</style>
