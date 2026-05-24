<template>
  <div class="dep-overview">
    <!-- 1. 告警：仅有实质问题时展示 -->
    <div v-if="alerts.length" class="alerts" role="alert">
      <div v-for="a in alerts" :key="a.id" class="alert" :class="a.level">
        <div class="alert-text">
          <strong>{{ a.title }}</strong>
          <span v-if="a.detail" class="muted small"> — {{ a.detail }}</span>
        </div>
        <button
          v-if="a.action === 'workers'"
          type="button"
          class="btn small ghost"
          @click="emit('navigate-workers')"
        >节点</button>
        <button
          v-else-if="a.action === 'runs'"
          type="button"
          class="btn small ghost"
          @click="emit('navigate-tab', 'runs')"
        >运行</button>
      </div>
    </div>

    <!-- 2. 运行调度：触发规则 + 节点策略/角色就位 -->
    <section class="sched-ov" aria-label="运行调度">
      <header class="sched-ov-head">
        <h3 class="sched-ov-title">运行调度</h3>
        <button type="button" class="btn small ghost" @click="emit('refresh')">刷新</button>
      </header>

      <div class="sched-ov-body">
        <article class="sched-ov-col sched-ov-col--trigger">
          <div class="sched-type-row">
            <span class="sched-ov-col-label">调度类型</span>
            <span class="sched-type-badge">{{ scheduleOverview.scheduleTypeLabel }}</span>
          </div>
          <div class="sched-trigger-grid">
            <div
              v-for="chip in scheduleOverview.triggerChips"
              :key="chip.label"
              class="sched-kv"
              :class="{ 'sched-kv--highlight': chip.highlight, 'sched-kv--muted': chip.muted }"
            >
              <span class="sched-kv-label">{{ chip.label }}</span>
              <span class="sched-kv-value" :class="{ mono: chip.mono }">{{ chip.value }}</span>
            </div>
          </div>
        </article>

        <article class="sched-ov-col sched-ov-col--nodes">
          <div class="sched-meta-row">
            <span class="sched-meta-chip">
              <span class="sched-meta-chip-label">节点策略</span>
              <span class="sched-meta-chip-value">{{ scheduleOverview.policyTypeLabel }}</span>
            </span>
            <span class="sched-meta-chip">
              <span class="sched-meta-chip-label">已分配</span>
              <span
                class="sched-meta-chip-value mono"
                :class="`sched-meta-chip-value--${scheduleOverview.allocationTone}`"
              >{{ scheduleOverview.allocationRatio }}</span>
            </span>
          </div>

          <div class="worker-chip-row">
            <div
              v-for="chip in scheduleOverview.workerChips"
              :key="chip.key"
              class="worker-chip"
              :class="workerChipClasses(chip)"
              :title="chip.title ?? undefined"
            >
              <span class="worker-chip-role">{{ chip.roleLabel }}</span>
              <span class="worker-chip-id mono">{{ chip.workerId || "—" }}</span>
              <span class="worker-chip-flags" aria-hidden="true">
                <span v-if="chip.bindKind === 'specified'" class="wf wf-pin">定</span>
                <span
                  v-if="chip.occupancy === 'assigned_ok' || chip.occupancy === 'assigned_weak'"
                  class="wf wf-assign"
                >配</span>
                <span v-if="chip.microLabel" class="wf wf-state">{{ chip.microLabel }}</span>
              </span>
              <span
                v-if="chip.workerStatus && chip.occupancy !== 'vacant'"
                class="worker-chip-dot"
                :class="workerStatusClass(chip.workerStatus)"
              />
            </div>
          </div>

          <div v-if="scheduleOverview.allocationTone === 'warn'" class="sched-ov-foot">
            <button type="button" class="btn small ghost" @click="emit('navigate-workers')">查看节点</button>
          </div>
        </article>
      </div>
    </section>

    <!-- 3. 运行记录 + 最近运行 -->
    <section class="ov-section" aria-label="运行记录">
      <div class="ov-two-col">
        <article class="ov-panel">
          <header class="ov-panel-head">
            <h4 class="ov-panel-title">运行记录</h4>
            <span v-if="loadingRunsPreview" class="muted small">加载中…</span>
          </header>
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
          <div class="ov-panel-actions">
            <button type="button" class="btn small primary" @click="emit('navigate-tab', 'runs')">查看全部运行</button>
          </div>
        </article>

        <article class="ov-panel ov-panel--table">
          <header class="ov-panel-head">
            <h4 class="ov-panel-title">最近运行</h4>
            <button type="button" class="btn small ghost" :disabled="loadingRunsPreview" @click="emit('refresh')">
              刷新
            </button>
          </header>
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
                  <td colspan="4" class="muted center">暂无运行记录</td>
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
        </article>
      </div>
    </section>

    <!-- 4. 消息账本 + 最近失败（仅消息触发） -->
    <section v-if="isSubscription" class="ov-section" aria-label="消息账本">
      <div class="ov-two-col">
        <article class="ov-panel">
          <header class="ov-panel-head">
            <h4 class="ov-panel-title">消息账本</h4>
            <span v-if="loadingSubSummary" class="muted small">加载中…</span>
          </header>
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
                <div class="ov-num mono" :class="{ bad: failedMessageCount > 0 }">
                  {{ subSummary.messages.by_status.failed ?? 0 }}
                </div>
                <div class="ov-label">失败</div>
              </div>
            </div>
            <p v-if="subSummary.messages.last_updated_at" class="muted small panel-note">
              最近更新 {{ formatTs(subSummary.messages.last_updated_at) }}
            </p>
          </template>
          <div v-else class="muted small pad">暂无消费统计</div>
          <div class="ov-panel-actions">
            <button type="button" class="btn small primary" @click="emit('navigate-tab', 'messages')">消息账本</button>
          </div>
        </article>

        <article class="ov-panel ov-panel--table">
          <header class="ov-panel-head">
            <h4 class="ov-panel-title">最近失败消息</h4>
            <button
              v-if="failedMessageCount > 0"
              type="button"
              class="btn small ghost"
              @click="emit('navigate-tab', 'messages')"
            >消息账本</button>
          </header>
          <div class="ov-table-wrap">
            <table v-if="failedMessageCount > 0 && subSummary" class="grid-table mini">
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
                    <span class="tag small" :class="messageStatusTagClass(m.status)">
                      {{ messageStatusLabel(m.status) }}
                    </span>
                  </td>
                  <td class="small err-cell">{{ truncateText(m.error, 120) }}</td>
                  <td class="mono small">{{ formatTs(m.updated_at) }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="muted small pad center">暂无失败消息</p>
          </div>
        </article>
      </div>
    </section>

    <!-- 5. 部署配置：单块分组 -->
    <section class="config-panel" aria-label="部署配置">
      <header class="config-panel-head">
        <h3 class="config-panel-title">部署配置</h3>
        <div class="config-panel-actions">
          <button type="button" class="btn small ghost" @click="emit('edit')">编辑</button>
          <button type="button" class="btn small ghost" @click="emit('navigate-tab', 'config')">JSON</button>
        </div>
      </header>
      <div class="config-groups">
        <div v-for="sec in configSections" :key="sec.title" class="config-group">
          <div class="config-group-label">{{ sec.title }}</div>
          <dl class="config-rows">
            <div v-for="row in sec.rows" :key="row.label" class="config-row">
              <dt>{{ row.label }}</dt>
              <dd :class="{ mono: row.mono }">{{ row.value }}</dd>
            </div>
          </dl>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { DeploymentDetail } from "@/api/deployments";
import type { FlowRunSummary } from "@/api/flowRuns";
import type { SubscriptionMessageRow, SubscriptionSummary } from "@/api/subscriptionObservability";
import type { Worker } from "@/api/workers";
import {
  buildDeploymentConfigSections,
  buildDeploymentOverviewAlerts,
  buildScheduleNodeOverview,
  computeCronNextRunIso,
  countRunsByStatus,
  messageStatusLabel,
  runStatusLabel,
  subscriptionFieldsFromScheduleConfig,
  truncateOverviewText,
  workerStatusLabel,
  type WorkerChipView,
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

const alerts = computed(() => buildDeploymentOverviewAlerts(props.deployment, props.subSummary));

const subFields = computed(() =>
  subscriptionFieldsFromScheduleConfig(
    props.deployment.schedule_config as Record<string, unknown> | undefined,
  ),
);

const consumerId = computed(
  () => props.subSummary?.consumer_id || subFields.value.consumer_id,
);

const cronExpr = computed(() => {
  if (props.deployment.schedule_type !== "cron") return null;
  return String(props.deployment.schedule_config?.cron_expr ?? "").trim() || null;
});

const cronNextRunIso = computed(() => computeCronNextRunIso(cronExpr.value));

function workerStatusForId(workerId: string): string | null {
  const w = props.workers.find((x) => x.worker_id === workerId);
  return w ? String(w.status) : null;
}

const scheduleOverview = computed(() =>
  buildScheduleNodeOverview(props.deployment, workerStatusForId, {
    cronNextIso: cronNextRunIso.value,
    formatTs: props.formatTs,
    consumerId: consumerId.value,
    maxInFlight: subFields.value.max_in_flight,
  }),
);

function workerStatusClass(status: string): string {
  if (status === "active") return "ok";
  if (status === "dead") return "dead";
  return "info";
}

function workerChipClasses(chip: WorkerChipView): Record<string, boolean> {
  return {
    "worker-chip--specified": chip.bindKind === "specified",
    "worker-chip--any": chip.bindKind === "any",
    "worker-chip--assigned-ok": chip.occupancy === "assigned_ok",
    "worker-chip--assigned-weak": chip.occupancy === "assigned_weak",
    "worker-chip--specified-idle": chip.occupancy === "specified_idle",
    "worker-chip--vacant": chip.occupancy === "vacant",
  };
}

const failedMessageCount = computed(() => props.subSummary?.messages.by_status.failed ?? 0);

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

const configSections = computed(() => buildDeploymentConfigSections(props.deployment, props.formatTs));

function truncateText(text: string | null | undefined, maxLen: number) {
  return truncateOverviewText(text, maxLen);
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
</script>

<style scoped>
.dep-overview {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* —— 告警 —— */
.alerts {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.alert {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  border-left: 3px solid var(--border);
  background: color-mix(in srgb, var(--accent-soft) 20%, var(--surface));
}

.alert.warn {
  border-left-color: #d97706;
  background: color-mix(in srgb, #fef3c7 45%, var(--surface));
}

.alert.bad {
  border-left-color: #b91c1c;
  background: color-mix(in srgb, #fee2e2 40%, var(--surface));
}

.alert-text {
  min-width: 0;
  font-size: 12px;
  line-height: 1.4;
}

.alert-text strong {
  font-weight: 700;
}

/* —— 运行调度 —— */
.sched-ov {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  overflow: hidden;
  min-width: 0;
}

.sched-ov-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: #fbfdff;
}

.sched-ov-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
}

.sched-type-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.sched-type-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 55%, transparent);
  color: var(--accent);
  white-space: nowrap;
}

.sched-ov-body {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) minmax(0, 1.6fr);
  gap: 0;
  align-items: stretch;
}

.sched-ov-col {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.sched-ov-col--trigger {
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, #fbfdff 80%, var(--surface));
}

.sched-ov-col-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.sched-trigger-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}

.sched-kv {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.sched-kv--highlight {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 35%, var(--surface));
}

.sched-kv--muted .sched-kv-value {
  font-weight: 500;
  color: var(--muted);
}

.sched-kv-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
}

.sched-kv-value {
  font-size: 12px;
  font-weight: 700;
  line-height: 1.35;
  word-break: break-word;
}

.sched-meta-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.sched-meta-chip {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px dashed color-mix(in srgb, var(--border) 90%, transparent);
  background: color-mix(in srgb, var(--border) 22%, transparent);
  max-width: 100%;
}

.sched-meta-chip-label {
  color: var(--muted);
  font-weight: 600;
  flex-shrink: 0;
}

.sched-meta-chip-value {
  font-weight: 700;
}

.sched-meta-chip-value--ok {
  color: #047857;
}

.sched-meta-chip-value--warn {
  color: #b45309;
}

.sched-meta-chip-value--muted {
  color: var(--muted);
}

.worker-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  flex: 1;
  align-content: flex-start;
}

.worker-chip {
  position: relative;
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  gap: 2px 6px;
  align-items: center;
  min-width: 118px;
  max-width: 200px;
  padding: 6px 8px 5px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: #fbfdff;
  cursor: default;
}

.worker-chip--any {
  border-style: dashed;
  background: color-mix(in srgb, var(--border) 10%, var(--surface));
}

.worker-chip--specified {
  border-color: color-mix(in srgb, var(--accent) 32%, var(--border));
}

.worker-chip--specified-idle {
  border-style: dashed;
  border-color: color-mix(in srgb, #d97706 42%, var(--border));
  background: color-mix(in srgb, #fef3c7 32%, var(--surface));
}

.worker-chip--specified-idle .worker-chip-id {
  color: #92400e;
}

.worker-chip--assigned-weak {
  border-color: color-mix(in srgb, #f59e0b 38%, var(--border));
  background: color-mix(in srgb, #fffbeb 50%, var(--surface));
}

.worker-chip--assigned-ok.worker-chip--specified {
  background: color-mix(in srgb, var(--accent-soft) 18%, #fbfdff);
}

.worker-chip--vacant .worker-chip-id {
  color: var(--muted);
  font-weight: 600;
}

.worker-chip-role {
  grid-row: 1 / 3;
  align-self: center;
  font-size: 9px;
  font-weight: 700;
  line-height: 1.15;
  min-width: 28px;
  max-width: 36px;
  padding: 2px 3px;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  background: color-mix(in srgb, var(--border) 45%, transparent);
  color: var(--muted);
  flex-shrink: 0;
}

.worker-chip--specified .worker-chip-role {
  background: color-mix(in srgb, var(--accent-soft) 80%, transparent);
  color: var(--accent);
}

.worker-chip-id {
  font-size: 11px;
  font-weight: 700;
  line-height: 1.25;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.worker-chip-flags {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-wrap: wrap;
}

.wf {
  font-size: 9px;
  font-weight: 700;
  line-height: 1;
  padding: 1px 4px;
  border-radius: 3px;
}

.wf-pin {
  color: var(--accent);
  background: color-mix(in srgb, var(--accent-soft) 65%, transparent);
}

.wf-assign {
  color: #047857;
  background: color-mix(in srgb, #10b981 14%, transparent);
}

.wf-state {
  color: #92400e;
  background: color-mix(in srgb, #f59e0b 16%, transparent);
}

.worker-chip--vacant .wf {
  display: none;
}

.worker-chip-dot {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--muted);
}

.worker-chip-dot.ok {
  background: #10b981;
}

.worker-chip-dot.dead {
  background: #94a3b8;
}

.worker-chip-dot.info {
  background: #3b82f6;
}

.sched-ov-foot {
  display: flex;
  justify-content: flex-end;
}

.tag.dead {
  background: color-mix(in srgb, #94a3b8 18%, transparent);
  color: #475569;
  border-color: color-mix(in srgb, #94a3b8 40%, transparent);
}

.tag.vacant {
  background: color-mix(in srgb, #94a3b8 12%, transparent);
  color: #64748b;
  border-color: color-mix(in srgb, #94a3b8 35%, transparent);
}

/* —— 运行 / 消息双列 —— */
.ov-section {
  min-width: 0;
}

.ov-two-col {
  display: grid;
  grid-template-columns: minmax(200px, 280px) minmax(0, 1fr);
  gap: 12px;
  align-items: stretch;
}

.ov-panel {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.ov-panel--table {
  padding-bottom: 8px;
}

.ov-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.ov-panel-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
}

.ov-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
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

.ov-panel-actions {
  margin-top: auto;
  display: flex;
  justify-content: flex-end;
}

.panel-note {
  margin: 0;
}

.ov-table-wrap {
  overflow: auto;
  min-width: 0;
  flex: 1;
  border-radius: 8px;
  border: 1px solid var(--border);
}

.pad {
  padding: 8px 0;
}

/* —— 配置单块 —— */
.config-panel {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  overflow: hidden;
}

.config-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: #fbfdff;
}

.config-panel-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
}

.config-panel-actions {
  display: flex;
  gap: 6px;
}

.config-groups {
  padding: 4px 0;
}

.config-group {
  padding: 10px 14px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
}

.config-group:last-child {
  border-bottom: none;
}

.config-group-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}

.config-rows {
  margin: 0;
  display: grid;
  gap: 4px 16px;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
}

.config-row {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 8px;
  align-items: baseline;
  font-size: 12px;
}

.config-row dt {
  margin: 0;
  color: var(--muted);
  font-weight: 500;
}

.config-row dd {
  margin: 0;
  font-weight: 600;
  min-width: 0;
  word-break: break-word;
}

/* —— 表格 —— */
.grid-table {
  width: 100%;
  border-collapse: collapse;
}

.grid-table th,
.grid-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  font-size: 12px;
  vertical-align: middle;
}

.grid-table th {
  color: var(--muted);
  font-weight: 600;
  font-size: 11px;
  border-bottom-width: 1px;
}

.grid-table tbody tr:last-child td {
  border-bottom: none;
}

tr.clickable {
  cursor: pointer;
}

tr.clickable:hover td {
  background: color-mix(in srgb, var(--accent-soft) 40%, transparent);
}

.err-cell {
  color: color-mix(in srgb, var(--danger, #c0392b) 85%, var(--text));
  word-break: break-word;
}

.bad {
  color: #b91c1c;
}

.muted {
  color: var(--muted);
}

.small {
  font-size: 11px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.center {
  text-align: center;
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

@media (max-width: 900px) {
  .sched-ov-body {
    grid-template-columns: 1fr;
  }

  .sched-ov-col--trigger {
    border-right: none;
    border-bottom: 1px solid var(--border);
  }

  .ov-two-col {
    grid-template-columns: 1fr;
  }

  .config-rows {
    grid-template-columns: 1fr;
  }
}
</style>
