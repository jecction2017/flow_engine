<template>
  <div class="run-detail">
    <header class="rd-head">
      <div class="rd-title">
        <span class="rd-id mono">{{ runDisplayLabel }}</span>
        <span class="rd-flow">{{ flowLabelById(detail.flow_code) }}</span>
        <span class="rd-ver">v{{ detail.ver_no }}</span>
        <span class="badge mode">{{ detail.mode }}</span>
        <span v-if="detail.schedule_type" class="badge sched">{{ detail.schedule_type }}</span>
        <span class="badge" :class="statusBadgeClass(detail.status)">{{ detail.status }}</span>
        <span v-if="elapsedText" class="muted">· {{ elapsedText }}</span>
      </div>
      <div class="rd-meta">
        <span v-if="detail.deployment_id" class="muted">deployment #{{ detail.deployment_id }}</span>
        <span v-if="detail.test_batch_id" class="muted">batch #{{ detail.test_batch_id }}</span>
        <span v-if="detail.worker_id" class="muted">worker {{ detail.worker_id }}</span>
        <span v-if="detail.started_at" class="muted" :title="detail.started_at">started {{ formatTs(detail.started_at) }}</span>
        <span v-if="detail.finished_at" class="muted" :title="detail.finished_at">finished {{ formatTs(detail.finished_at) }}</span>
      </div>
      <div v-if="hasCounters" class="rd-counters">
        <div class="counter" :title="`累计触发 ${detail.span_count ?? 0} 次 Span（含未采样）`">
          <span class="counter-lbl">span_count</span>
          <span class="counter-val mono">{{ formatNum(detail.span_count) }}</span>
        </div>
        <div
          class="counter"
          :title="`实际写库 ${detail.sampled_span_count ?? 0} 条；采样率 ${sampleRatePct}`"
        >
          <span class="counter-lbl">sampled</span>
          <span class="counter-val mono">{{ formatNum(detail.sampled_span_count) }}</span>
          <span v-if="sampleRatePct" class="counter-rate">({{ sampleRatePct }})</span>
        </div>
      </div>
    </header>

    <CollapsibleFailureCard
      v-if="detail.error || detail.failure_detail"
      title="运行失败"
      :preview="failurePreview"
    >
      <FailureReportPanel
        :failure-detail="detail.failure_detail"
        :fallback-text="detail.error"
      />
    </CollapsibleFailureCard>

    <nav v-if="tabs.length > 1" class="rd-tabs">
      <button
        v-for="t in tabs"
        :key="t.id"
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === t.id }"
        @click="setTab(t.id)"
      >
        {{ t.label }}
      </button>
    </nav>

    <section v-if="activeTab === 'overview' && isDeployRun" class="rd-section">
      <div class="rd-section-head">
        <span>节点聚合统计（{{ scheduleLabel }}）</span>
        <span class="muted small">实时窗口聚合，5min 桶滚动写入</span>
      </div>
      <MetricsSummary
        :deploy-run-id="detail.id"
        @drill="onDrillNode"
      />
    </section>

    <template v-if="activeTab === 'spans'">
      <SpansExplorer
        v-if="isDeployRun"
        :deploy-run-id="detail.id"
        :key="`deploy-${detail.id}-${drillNodeKey}`"
        :page-size="50"
        :initial-node-id="drillNodeId"
        help-tip="按父子关系嵌套展示；有日志的节点可点数字按钮或点击行查看日志与 attributes，与试运行时间线一致"
      />
      <SpansExplorer
        v-else
        :test-run-id="detail.id"
        :key="`test-${detail.id}`"
        :page-size="50"
        help-tip="按父子关系嵌套展示；有日志的节点可点数字按钮或点击行查看日志与 attributes，与试运行时间线一致"
      />
    </template>

    <section v-if="evaluationBlock && activeTab === 'evaluation'" class="rd-section">
      <div class="rd-section-head">
        <span>评估结果（assertions）</span>
        <span class="badge" :class="evaluationBlock.verdict === 'pass' ? 'ok' : 'bad'">
          {{ evaluationBlock.verdict }}
        </span>
      </div>
      <p v-if="evaluationBlock.reason" class="muted small pad">{{ evaluationBlock.reason }}</p>
      <p v-if="evaluationBlock.message" class="err small">{{ evaluationBlock.message }}</p>
      <ul v-if="evaluationBlock.rules?.length" class="eval-rules">
        <li
          v-for="(rule, i) in evaluationBlock.rules"
          :key="i"
          :class="{ ok: rule.pass, bad: !rule.pass }"
        >
          <span class="mono">{{ rule.id }}</span>
          <span>{{ rule.pass ? "pass" : "fail" }}</span>
          <span v-if="rule.message" class="muted">{{ rule.message }}</span>
        </li>
      </ul>
    </section>

    <section v-if="activeTab === 'result' && hasGlobalNs" class="rd-section">
      <div class="rd-section-head">
        <span>运行结果上下文（global_ns）</span>
        <InfoTip text="流程运行结束时的全局命名空间快照（已剔除 dictionary），与试运行结果中的 global_ns 一致。" />
      </div>
      <ReadonlyJsonEditor :model-value="globalNsText" :default-height="240" :min-height="120" />
    </section>

    <section v-if="activeTab === 'context' && detail.trigger_context" class="rd-section">
      <div class="rd-section-head">
        <span>触发上下文（trigger_context）</span>
      </div>
      <ReadonlyJsonEditor :model-value="triggerCtxText" :default-height="220" :min-height="120" />
    </section>

    <section v-if="activeTab === 'flow_logs'" class="rd-section">
      <FlowLogsPanel :logs="flowLogs" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import type { FlowRunDetail } from "@/api/flowRuns";
import { useFlowLabels } from "@/composables/useFlowLabels";
import CollapsibleFailureCard from "@/components/CollapsibleFailureCard.vue";
import FailureReportPanel from "@/components/FailureReportPanel.vue";
import { failurePreviewText } from "@/utils/formatFailureReport";
import FlowLogsPanel from "@/components/FlowLogsPanel.vue";
import InfoTip from "@/components/InfoTip.vue";
import MetricsSummary from "@/components/MetricsSummary.vue";
import ReadonlyJsonEditor from "@/components/ReadonlyJsonEditor.vue";
import SpansExplorer from "@/components/SpansExplorer.vue";
import { formatDeployRunNo } from "@/utils/deployRunDisplay";

type TabId = "overview" | "spans" | "result" | "evaluation" | "context" | "flow_logs";

const props = defineProps<{ detail: FlowRunDetail }>();

const { flowLabelById, ensureFlowList } = useFlowLabels();

onMounted(() => {
  void ensureFlowList();
});

const isDeployRun = computed(() => props.detail.deployment_id != null);

const runDisplayLabel = computed(() =>
  isDeployRun.value ? formatDeployRunNo(props.detail) : `#${props.detail.id}`,
);
const isTestRun = computed(() => props.detail.test_batch_id != null);
const scheduleLabel = computed(() => props.detail.schedule_type || "deployment");

const evaluationBlock = computed(() => {
  const ev = props.detail.evaluation;
  if (!ev || typeof ev !== "object") return null;
  if (!ev.verdict && !(ev.rules && ev.rules.length) && !ev.reason && !ev.message) return null;
  return ev;
});

const tabs = computed<{ id: TabId; label: string }[]>(() => {
  const out: { id: TabId; label: string }[] = [];
  if (isDeployRun.value) {
    out.push({ id: "overview", label: "概览" });
  }
  out.push({ id: "spans", label: "执行链路" });
  if (hasGlobalNs.value) {
    out.push({ id: "result", label: "运行结果" });
  }
  if (evaluationBlock.value) {
    out.push({ id: "evaluation", label: "评估结果" });
  }
  if (props.detail.trigger_context) {
    out.push({ id: "context", label: "触发上下文" });
  }
  if (flowLogs.value.length > 0) {
    out.push({ id: "flow_logs", label: "流程钩子日志" });
  }
  return out;
});

const flowLogs = computed(() =>
  Array.isArray(props.detail.flow_logs) ? props.detail.flow_logs : [],
);

const failurePreview = computed(() =>
  failurePreviewText({
    failureDetail: props.detail.failure_detail,
    error: props.detail.error,
  }),
);

const hasGlobalNs = computed(() => {
  const g = props.detail.global_ns;
  return g != null && typeof g === "object" && Object.keys(g).length > 0;
});

const globalNsText = computed(() =>
  hasGlobalNs.value ? JSON.stringify(props.detail.global_ns, null, 2) : "",
);

const activeTab = ref<TabId>(tabs.value[0]?.id ?? "spans");

// If the run changes (deploy → test, etc.) reset to the first available tab.
watch(
  () => props.detail.id,
  () => {
    const first = tabs.value[0]?.id;
    if (first && !tabs.value.some((t) => t.id === activeTab.value)) {
      activeTab.value = first;
    } else if (first && tabs.value.length === 1) {
      activeTab.value = first;
    }
  },
);

function setTab(id: TabId): void {
  activeTab.value = id;
}

// When the overview's "查看 Span →" link is clicked, jump to the
// execution tree pre-filtered on that node_id. The drill key bumps the
// SpansExplorer's key so it re-applies the filter cleanly.
const drillNodeKey = ref(0);
const drillNodeId = ref<string | null>(null);

function onDrillNode(nodeId: string): void {
  drillNodeId.value = nodeId;
  drillNodeKey.value += 1;
  activeTab.value = "spans";
}

const hasCounters = computed(
  () => props.detail.span_count != null || props.detail.sampled_span_count != null,
);

const sampleRatePct = computed(() => {
  const total = props.detail.span_count ?? 0;
  const sampled = props.detail.sampled_span_count ?? 0;
  if (total <= 0) return "";
  const rate = sampled / total;
  if (rate >= 0.99) return "≈100%";
  return `${(rate * 100).toFixed(2)}%`;
});

function statusBadgeClass(st: string): string {
  if (st === "completed") return "ok";
  if (st === "failed") return "bad";
  if (st === "terminated") return "warn";
  if (st === "running") return "running";
  return "info";
}

function formatNum(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 10_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
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
  if (Number.isNaN(a)) return "";
  const end = Number.isNaN(b) ? Date.now() : b;
  const diff = end - a;
  if (diff < 0) return "";
  if (diff < 1000) return `${diff}ms`;
  if (diff < 60_000) return `${(diff / 1000).toFixed(2)}s`;
  if (diff < 3_600_000) return `${(diff / 60_000).toFixed(1)}min`;
  return `${(diff / 3_600_000).toFixed(1)}h`;
});

const triggerCtxText = computed(() =>
  props.detail.trigger_context ? JSON.stringify(props.detail.trigger_context, null, 2) : "",
);

// Silence "unused" linter warnings.
void isTestRun;
</script>

<style scoped>
.run-detail {
  display: flex;
  flex-direction: column;
  gap: 10px;
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

.rd-id { color: var(--muted); font-weight: 500; }
.rd-flow { font-weight: 700; }
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

.rd-counters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 6px;
  border-top: 1px dashed var(--border);
  padding-top: 6px;
}

.counter {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  font-size: 11px;
}

.counter-lbl {
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 10px;
  font-weight: 600;
}

.counter-val {
  font-weight: 700;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: #1d4ed8;
}

.counter-rate {
  color: var(--muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.muted { color: var(--muted); font-weight: 400; font-size: 11px; }

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

.badge.sched {
  background: color-mix(in srgb, #14b8a6 14%, transparent);
  color: #0f766e;
  border-color: color-mix(in srgb, #14b8a6 35%, transparent);
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

.rd-tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border);
  padding-left: 4px;
}

.tab-btn {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-bottom: none;
  border-top-left-radius: 6px;
  border-top-right-radius: 6px;
  background: #f8fafc;
  color: var(--muted);
  cursor: pointer;
  margin-bottom: -1px;
}

.tab-btn.active {
  background: var(--surface);
  color: var(--text);
  border-bottom: 1px solid var(--surface);
}

.rd-section {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  overflow: hidden;
  padding: 0;
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

.rd-section-head + * {
  padding: 10px 12px;
}

/* Evaluation */

.eval-rules {
  list-style: none;
  margin: 0;
  padding: 8px 12px;
  font-size: 12px;
}

.eval-rules li {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
}

.eval-rules li.ok { color: #047857; }
.eval-rules li.bad { color: #b91c1c; }
.eval-rules li:last-child { border-bottom: none; }

.center { text-align: center; }
.pad { padding: 12px; margin: 0; }
.small { font-size: 11px; }

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

.mono { font-family: var(--mono); }
</style>
