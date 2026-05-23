<template>
  <div class="dep-overview">
    <!-- Layer 1: Health banner -->
    <section
      v-if="showHealthBanner"
      class="health-banner"
      :class="{
        warn: deployment.status === 'stopping' || deployment.status === 'pending' || ingressRetrying,
        bad: deployment.status === 'failed',
      }"
      aria-label="健康告警"
    >
      <div class="health-banner-main">
        <div class="health-banner-title">
          <span class="tag small" :class="statusTagClass(deployment.status)">
            {{ statusLabel(deployment.status) }}
          </span>
          <span v-if="deployment.status_detail" class="health-reason">
            {{ reasonLabel(deployment.status_detail) }}
          </span>
          <span v-if="statusMessage(deployment.status_detail)" class="muted small health-msg">
            {{ statusMessage(deployment.status_detail) }}
          </span>
        </div>
        <div v-if="hasDiagDetails" class="health-meta muted small">
          <span v-if="statusWhen(deployment.status_detail)">时间 {{ formatTs(statusWhen(deployment.status_detail)!) }}</span>
          <span v-if="statusWorker(deployment.status_detail)"> · Worker {{ statusWorker(deployment.status_detail) }}</span>
          <span v-if="statusPool(deployment.status_detail)?.length">
            · 池 {{ statusPool(deployment.status_detail)!.join(", ") }}
          </span>
          <span v-if="statusActiveCount(deployment.status_detail) != null">
            · 在线节点 {{ statusActiveCount(deployment.status_detail) }}
          </span>
          <span v-if="statusQueuedFailed(deployment.status_detail) != null">
            · 排队失败 {{ statusQueuedFailed(deployment.status_detail) }}
          </span>
          <span v-if="ingressAttempt != null && ingressMaxAttempts != null">
            · 重试 {{ ingressAttempt }}/{{ ingressMaxAttempts }}
          </span>
          <span v-if="ingressNextRetryAt">
            · 下次重试 {{ formatTs(ingressNextRetryAt) }}
          </span>
        </div>
        <div v-if="!deployment.assignments?.length && deployment.status === 'pending'" class="muted small">
          尚未分配工作节点
        </div>
      </div>
      <div class="health-banner-actions">
        <button
          v-if="suggestedAction === 'workers'"
          type="button"
          class="btn small primary"
          @click="emit('navigate-workers')"
        >查看工作节点</button>
        <button
          v-else-if="suggestedAction === 'messages'"
          type="button"
          class="btn small primary"
          @click="emit('navigate-tab', 'messages')"
        >查看消费</button>
        <button
          v-else
          type="button"
          class="btn small primary"
          @click="emit('navigate-tab', 'runs')"
        >查看运行</button>
        <button type="button" class="btn small ghost" @click="emit('refresh')">刷新</button>
      </div>
      <details v-if="deployment.status_detail" class="diag-raw">
        <summary class="muted small">原始 JSON</summary>
        <pre class="cfg mono">{{ JSON.stringify(deployment.status_detail, null, 2) }}</pre>
      </details>
    </section>

    <!-- Layer 2: Metric cards -->
    <div class="overview-grid">
      <article class="ov-card">
        <div class="ov-head">
          <div class="ov-title">运行实例</div>
          <span v-if="loadingRunsPreview" class="muted small">加载中…</span>
        </div>
        <div class="ov-metrics">
          <div class="ov-metric">
            <div class="ov-num mono">{{ runMetrics.total }}</div>
            <div class="ov-label">全部</div>
          </div>
          <div class="ov-metric">
            <div class="ov-num mono">{{ runMetrics.running }}</div>
            <div class="ov-label">运行中</div>
          </div>
          <div class="ov-metric">
            <div class="ov-num mono">{{ runMetrics.completed }}</div>
            <div class="ov-label">已完成</div>
          </div>
          <div class="ov-metric">
            <div class="ov-num mono" :class="{ bad: runMetrics.failed > 0 }">{{ runMetrics.failed }}</div>
            <div class="ov-label">失败</div>
          </div>
        </div>
        <div class="ov-actions">
          <button type="button" class="btn small primary" @click="emit('navigate-tab', 'runs')">查看全部运行</button>
        </div>
      </article>

      <article class="ov-card">
        <div class="ov-title">调度与部署</div>
        <dl class="ov-dl">
          <div><dt>部署方式</dt><dd>{{ modeLabel(deployment.mode) }}</dd></div>
          <div><dt>环境</dt><dd class="mono">{{ deployment.env_profile_code || "—" }}</dd></div>
          <div><dt>调度方式</dt><dd>{{ scheduleLabel(deployment.schedule_type) }}</dd></div>
          <div v-if="deployment.schedule_type === 'cron' && deployment.schedule_config?.cron_expr">
            <dt>Cron</dt><dd class="mono">{{ deployment.schedule_config.cron_expr }}</dd>
          </div>
          <div v-if="isSubscription && subSummary?.consumer_id">
            <dt>Consumer</dt><dd class="mono">{{ subSummary.consumer_id }}</dd>
          </div>
          <div v-if="isSubscription && subSummary?.messages.last_updated_at">
            <dt>最近消息</dt><dd class="mono small">{{ formatTs(subSummary.messages.last_updated_at) }}</dd>
          </div>
          <div><dt>节点定向</dt><dd>{{ targetingLabel(deployment.worker_targeting) }}</dd></div>
        </dl>
        <div class="ov-actions">
          <button type="button" class="btn small ghost" @click="emit('navigate-tab', 'config')">完整配置</button>
          <button type="button" class="btn small ghost" @click="emit('edit')">编辑配置</button>
        </div>
      </article>

      <article v-if="isSubscription" class="ov-card">
        <div class="ov-head">
          <div class="ov-title">消息账本</div>
          <span v-if="loadingSubSummary" class="muted small">加载中…</span>
        </div>
        <template v-if="subSummary">
          <div class="ov-metrics">
            <div class="ov-metric">
              <div class="ov-num mono">{{ subSummary.messages.total }}</div>
              <div class="ov-label">全部</div>
            </div>
            <div class="ov-metric">
              <div class="ov-num mono">{{ subSummary.messages.by_status.processing ?? 0 }}</div>
              <div class="ov-label">处理中</div>
            </div>
            <div class="ov-metric">
              <div class="ov-num mono">{{ subSummary.messages.by_status.completed ?? 0 }}</div>
              <div class="ov-label">已完成</div>
            </div>
            <div class="ov-metric">
              <div class="ov-num mono" :class="{ bad: (subSummary.messages.by_status.failed ?? 0) > 0 }">
                {{ subSummary.messages.by_status.failed ?? 0 }}
              </div>
              <div class="ov-label">失败</div>
            </div>
          </div>
          <div class="ov-actions">
            <button type="button" class="btn small primary" @click="emit('navigate-tab', 'messages')">消息账本</button>
            <button type="button" class="btn small ghost" @click="emit('refresh')">刷新</button>
          </div>
        </template>
        <div v-else class="muted small pad">暂无消费统计</div>
      </article>

      <article v-else class="ov-card" :class="{ highlight: !assignmentCount }">
        <div class="ov-title">执行资源</div>
        <div class="ov-metrics ov-metrics--compact">
          <div class="ov-metric">
            <div class="ov-num mono" :class="{ bad: !assignmentCount }">{{ assignmentCount }}</div>
            <div class="ov-label">已分配</div>
          </div>
        </div>
        <ul v-if="assignmentPreview.length" class="assn-list compact">
          <li v-for="a in assignmentPreview" :key="a.id">
            <span class="mono">{{ a.worker_id }}</span>
            <span class="tag small">{{ a.role }}</span>
            <span
              v-if="workerStatusById(a.worker_id)"
              class="tag small"
              :class="workerStatusClass(workerStatusById(a.worker_id)!)"
            >{{ workerStatusLabel(workerStatusById(a.worker_id)!) }}</span>
            <span v-if="a.lease_expires_at" class="muted small">租约 {{ formatTs(a.lease_expires_at) }}</span>
          </li>
        </ul>
        <div v-else class="muted small pad">尚未分配工作节点</div>
        <p v-if="assignmentCount > assignmentPreview.length" class="muted small">
          共 {{ assignmentCount }} 个，仅展示前 {{ assignmentPreview.length }} 个
        </p>
        <div class="ov-actions">
          <button type="button" class="btn small primary" @click="emit('navigate-workers')">查看工作节点</button>
          <button type="button" class="btn small ghost" @click="emit('refresh')">刷新分配</button>
        </div>
      </article>
    </div>

    <!-- Layer 3: Policy summary -->
    <section class="side-section policy-section">
      <div class="lbl">调度与策略</div>
      <div class="kv-grid policy-kv">
        <div class="kv">
          <div class="k">Worker 策略</div>
          <div class="v small">{{ workerPolicyText(deployment.worker_policy) }}</div>
        </div>
        <div class="kv">
          <div class="k">
            能力策略
            <InfoTip text="部署附加策略与节点、环境能力策略按帮助文档顺序合并，仅本部署运行生效。" />
          </div>
          <div class="v small">
            {{ capabilityRuleCount }} 条规则
            <button type="button" class="linkish" @click="emit('navigate-tab', 'config')">查看完整配置</button>
            <button type="button" class="linkish" @click="emit('edit')">编辑</button>
          </div>
        </div>
        <div class="kv">
          <div class="k">创建时间</div>
          <div class="v mono small">{{ deployment.created_at ? formatTs(deployment.created_at) : "—" }}</div>
        </div>
        <div class="kv">
          <div class="k">更新时间</div>
          <div class="v mono small">{{ deployment.updated_at ? formatTs(deployment.updated_at) : "—" }}</div>
        </div>
      </div>
      <ul v-if="isSubscription && assignmentPreview.length" class="assn-list compact assn-inline">
        <li v-for="a in assignmentPreview" :key="'sub-' + a.id">
          <span class="mono">{{ a.worker_id }}</span>
          <span class="tag small">{{ a.role }}</span>
          <span v-if="a.lease_expires_at" class="muted small">租约 {{ formatTs(a.lease_expires_at) }}</span>
        </li>
      </ul>
    </section>

    <!-- Layer 4A: Recent runs -->
    <section class="side-section">
      <div class="lbl-row">
        <div class="lbl">最近运行</div>
        <button type="button" class="btn small ghost" :disabled="loadingRunsPreview" @click="emit('refresh')">刷新</button>
      </div>
      <div class="ov-table-wrap">
        <table class="grid-table mini">
          <thead>
            <tr>
              <th style="width:80px">运行</th>
              <th style="width:100px">状态</th>
              <th style="width:110px">耗时</th>
              <th>Worker</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loadingRunsPreview">
              <td colspan="4" class="muted center">加载中…</td>
            </tr>
            <tr v-else-if="!runsPreview.length">
              <td colspan="4" class="muted center">
                暂无运行记录
                <span v-if="deployment.status === 'running'" class="block small">调度已启动，等待首次触发</span>
              </td>
            </tr>
            <tr
              v-for="r in runsPreview"
              :key="r.id"
              class="clickable"
              @click="emit('open-run', r.id)"
            >
              <td class="mono">#{{ r.id }}</td>
              <td>
                <span class="tag small" :class="runStatusTagClass(r.status)">{{ runStatusLabel(r.status) }}</span>
              </td>
              <td class="mono small">{{ runElapsed(r) }}</td>
              <td class="mono small">{{ r.worker_id || "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="ov-actions">
        <button type="button" class="btn small primary" @click="emit('navigate-tab', 'runs')">查看全部运行</button>
      </div>
    </section>

    <!-- Layer 4B: Recent failed messages (subscription) -->
    <section v-if="isSubscription" class="side-section">
      <div class="lbl-row">
        <div class="lbl">最近失败消息</div>
        <button
          v-if="failedMessageCount > 0"
          type="button"
          class="btn small ghost"
          @click="emit('navigate-tab', 'messages')"
        >消息账本</button>
      </div>
      <template v-if="failedMessageCount > 0 && subSummary">
        <table class="grid-table mini">
          <thead>
            <tr>
              <th>位置</th>
              <th style="width:90px">状态</th>
              <th>错误</th>
              <th style="width:150px">时间</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="m in subSummary.recent_failed_messages"
              :key="m.id"
              class="clickable"
              @click="emit('open-message', m)"
            >
              <td class="mono small">{{ m.topic }}:{{ m.partition }}:{{ m.offset }}</td>
              <td>
                <span class="tag small" :class="messageStatusTagClass(m.status)">{{ messageStatusLabel(m.status) }}</span>
              </td>
              <td class="small err-cell">{{ truncateText(m.error, 120) }}</td>
              <td class="mono small">{{ formatTs(m.updated_at) }}</td>
            </tr>
          </tbody>
        </table>
      </template>
      <div v-else class="muted small pad">暂无失败消息</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { Assignment, DeploymentDetail } from "@/api/deployments";
import type { FlowRunSummary } from "@/api/flowRuns";
import type { SubscriptionMessageRow, SubscriptionSummary } from "@/api/subscriptionObservability";
import type { Worker } from "@/api/workers";
import InfoTip from "@/components/InfoTip.vue";
import {
  countRunsByStatus,
  deploymentModeLabel,
  deploymentStatusLabel,
  messageStatusLabel,
  runStatusLabel,
  scheduleTypeLabel,
  workerStatusLabel,
  isSubscriptionIngressRetrying,
  shouldShowHealthBanner,
  statusDetailActiveCount,
  statusDetailIngressAttempt,
  statusDetailIngressMaxAttempts,
  statusDetailMessage,
  statusDetailNextRetryAt,
  statusDetailPool,
  statusDetailQueuedFailed,
  statusDetailReasonLabel,
  statusDetailSuggestedAction,
  statusDetailWhen,
  statusDetailWorker,
  truncateOverviewText,
  workerPolicySummary,
  workerTargetingLabel,
} from "@/utils/deploymentOverview";

const props = defineProps<{
  deployment: DeploymentDetail;
  subSummary: SubscriptionSummary | null;
  runsPreview: FlowRunSummary[];
  runsPreviewTotal: number;
  workers: Worker[];
  loadingSubSummary: boolean;
  loadingRunsPreview: boolean;
  formatTs: (iso: string | null) => string;
  runElapsed: (r: FlowRunSummary) => string;
}>();

const emit = defineEmits<{
  refresh: [];
  "navigate-tab": [tab: "runs" | "messages" | "config"];
  "navigate-workers": [];
  "open-run": [runId: number];
  "open-message": [message: SubscriptionMessageRow];
  edit: [];
}>();

const isSubscription = computed(() => props.deployment.schedule_type === "subscription");

const showHealthBanner = computed(() =>
  shouldShowHealthBanner(props.deployment, props.subSummary),
);

const ingressRetrying = computed(() =>
  isSubscriptionIngressRetrying(props.deployment.status_detail ?? null),
);

const ingressAttempt = computed(() =>
  statusDetailIngressAttempt(props.deployment.status_detail ?? null),
);

const ingressMaxAttempts = computed(() =>
  statusDetailIngressMaxAttempts(props.deployment.status_detail ?? null),
);

const ingressNextRetryAt = computed(() =>
  statusDetailNextRetryAt(props.deployment.status_detail ?? null),
);

const suggestedAction = computed(() =>
  statusDetailSuggestedAction(props.deployment.status_detail ?? null),
);

const assignmentCount = computed(() => props.deployment.assignments?.length ?? 0);

const assignmentPreview = computed((): Assignment[] => {
  const list = props.deployment.assignments ?? [];
  return list.slice(0, 5);
});

const capabilityRuleCount = computed(
  () => props.deployment.capability_policy?.length ?? 0,
);

const failedMessageCount = computed(
  () => props.subSummary?.messages.by_status.failed ?? 0,
);

const runMetrics = computed(() => {
  if (isSubscription.value && props.subSummary) {
    const by = props.subSummary.runs.by_status;
    return {
      total: props.subSummary.runs.total,
      running: by.running ?? 0,
      completed: by.completed ?? 0,
      failed: by.failed ?? 0,
    };
  }
  const fromPreview = countRunsByStatus(props.runsPreview);
  const total = props.runsPreviewTotal > 0 ? props.runsPreviewTotal : fromPreview.total;
  return {
    total,
    running: fromPreview.running,
    completed: fromPreview.completed,
    failed: fromPreview.failed,
  };
});

const hasDiagDetails = computed(() => {
  const d = props.deployment.status_detail;
  if (!d) return false;
  return Boolean(
    statusWhen(d)
      || statusWorker(d)
      || statusPool(d)?.length
      || statusActiveCount(d) != null
      || statusQueuedFailed(d) != null
      || ingressAttempt.value != null
      || ingressNextRetryAt.value,
  );
});

function workerStatusById(workerId: string): string | null {
  const w = props.workers.find((x) => x.worker_id === workerId);
  return w ? String(w.status) : null;
}

function statusLabel(s: string) {
  return deploymentStatusLabel(s);
}
function modeLabel(m: string) {
  return deploymentModeLabel(m);
}
function scheduleLabel(s: string) {
  return scheduleTypeLabel(s);
}
function targetingLabel(t: DeploymentDetail["worker_targeting"]) {
  return workerTargetingLabel(t);
}
function reasonLabel(d: Record<string, unknown>) {
  return statusDetailReasonLabel(d);
}
function statusMessage(d: Record<string, unknown> | null | undefined) {
  return statusDetailMessage(d);
}
function statusWhen(d: Record<string, unknown> | null | undefined) {
  return statusDetailWhen(d);
}
function statusWorker(d: Record<string, unknown> | null | undefined) {
  return statusDetailWorker(d);
}
function statusPool(d: Record<string, unknown> | null | undefined) {
  return statusDetailPool(d);
}
function statusActiveCount(d: Record<string, unknown> | null | undefined) {
  return statusDetailActiveCount(d);
}
function statusQueuedFailed(d: Record<string, unknown> | null | undefined) {
  return statusDetailQueuedFailed(d);
}
function workerPolicyText(policy: DeploymentDetail["worker_policy"]) {
  return workerPolicySummary(policy);
}
function truncateText(text: string | null | undefined, maxLen: number) {
  return truncateOverviewText(text, maxLen);
}

function statusTagClass(status: string): string {
  if (status === "running") return "running";
  if (status === "completed" || status === "stopped") return "ok";
  if (status === "failed") return "bad";
  if (status === "stopping") return "warn";
  return "info";
}

function runStatusTagClass(status: string): string {
  if (status === "running") return "running";
  if (status === "completed") return "ok";
  if (status === "failed") return "bad";
  if (status === "terminated") return "warn";
  return "info";
}

function messageStatusTagClass(status: string): string {
  if (status === "processing") return "running";
  if (status === "completed") return "ok";
  if (status === "failed") return "bad";
  return "info";
}

function workerStatusClass(status: string): string {
  if (status === "active") return "ok";
  if (status === "dead") return "dead";
  return "info";
}
</script>

<style scoped>
.dep-overview {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.health-banner {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  background: color-mix(in srgb, var(--accent-soft) 25%, var(--surface));
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.health-banner.warn {
  border-color: color-mix(in srgb, #d97706 40%, var(--border));
  background: color-mix(in srgb, #fef3c7 35%, var(--surface));
}

.health-banner.bad {
  border-color: color-mix(in srgb, #b91c1c 35%, var(--border));
  background: color-mix(in srgb, #fee2e2 30%, var(--surface));
}

.health-banner-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.health-banner-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.health-reason {
  font-weight: 700;
  font-size: 13px;
}

.health-banner-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.health-meta {
  line-height: 1.4;
}

.diag-raw {
  margin-top: 4px;
}

.diag-raw summary {
  cursor: pointer;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.ov-card.highlight {
  border-color: color-mix(in srgb, #d97706 45%, var(--border));
}

.ov-dl {
  margin: 0;
  display: grid;
  gap: 6px;
  font-size: 12px;
}

.ov-dl > div {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 8px;
  align-items: baseline;
}

.ov-dl dt {
  margin: 0;
  color: var(--muted);
}

.ov-dl dd {
  margin: 0;
  min-width: 0;
  word-break: break-word;
}

.ov-metrics--compact {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  max-width: 200px;
}

.ov-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.ov-title {
  font-weight: 700;
  font-size: 13px;
}

.ov-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.ov-metric {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fbfdff;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.ov-num {
  font-size: 18px;
  font-weight: 800;
  line-height: 1.05;
}

.ov-label {
  font-size: 11px;
  color: var(--muted);
}

.ov-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.ov-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.bad {
  color: #b91c1c;
}

.lbl-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.lbl-row .lbl {
  margin-bottom: 0;
}

.policy-kv {
  margin-top: 4px;
}

.assn-list.compact {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
}

.assn-list.compact li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.assn-inline {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
}

.ov-table-wrap {
  overflow: auto;
  min-width: 0;
  border-radius: 10px;
}

.block {
  display: block;
  margin-top: 4px;
}

.err-cell {
  color: color-mix(in srgb, var(--danger, #c0392b) 85%, var(--text));
  word-break: break-word;
}

tr.clickable {
  cursor: pointer;
}

tr.clickable:hover td {
  background: color-mix(in srgb, var(--accent-soft) 45%, transparent);
}

.linkish {
  border: none;
  background: none;
  padding: 0;
  margin-left: 6px;
  color: var(--accent);
  cursor: pointer;
  text-decoration: underline;
  font: inherit;
  font-size: inherit;
}

.pad {
  padding: 8px 0;
}

.cfg {
  margin: 8px 0 0;
  padding: 10px;
  border-radius: 8px;
  background: var(--surface-2);
  font-size: 11px;
  overflow: auto;
  max-height: 200px;
}

@media (max-width: 980px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .ov-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.side-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lbl {
  font-size: 11px;
  color: var(--muted);
  font-weight: 600;
  margin-bottom: 4px;
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.kv {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fbfdff;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.kv .k {
  font-size: 11px;
  color: var(--muted);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 4px;
}

.kv .v {
  font-size: 12px;
  color: var(--text);
  font-weight: 700;
  min-width: 0;
}

.grid-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

.grid-table th,
.grid-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  font-size: 12px;
  vertical-align: middle;
}

.grid-table th {
  background: #fbfdff;
  color: var(--muted);
  font-weight: 600;
  font-size: 11px;
}

.grid-table tbody tr:last-child td {
  border-bottom: none;
}

.grid-table.mini th,
.grid-table.mini td {
  padding: 6px 10px;
}

.muted {
  color: var(--muted);
}

.center {
  text-align: center;
}

.small {
  font-size: 11px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.tag {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
  white-space: nowrap;
}

.tag.small {
  font-size: 9px;
}

.tag.ok {
  background: color-mix(in srgb, #10b981 14%, transparent);
  color: #047857;
  border-color: color-mix(in srgb, #10b981 35%, transparent);
}

.tag.bad {
  background: color-mix(in srgb, #ef4444 14%, transparent);
  color: #b91c1c;
  border-color: color-mix(in srgb, #ef4444 35%, transparent);
}

.tag.dead {
  background: color-mix(in srgb, #94a3b8 18%, transparent);
  color: #475569;
  border-color: color-mix(in srgb, #94a3b8 40%, transparent);
}

.tag.warn {
  background: color-mix(in srgb, #f59e0b 18%, transparent);
  color: #92400e;
  border-color: color-mix(in srgb, #f59e0b 35%, transparent);
}

.tag.running {
  background: color-mix(in srgb, #3b82f6 14%, transparent);
  color: #1d4ed8;
  border-color: color-mix(in srgb, #3b82f6 35%, transparent);
}

.tag.info {
  background: color-mix(in srgb, var(--accent-soft) 50%, transparent);
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 25%, transparent);
}

@media (max-width: 1080px) {
  .kv-grid {
    grid-template-columns: 1fr;
  }
}
</style>
