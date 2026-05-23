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

    <!-- 2. 调度与部署：仅实时调度与节点分配 -->
    <section class="schedule-panel" aria-label="调度与部署">
      <header class="schedule-panel-head">
        <h3 class="schedule-panel-title">调度与部署</h3>
        <button type="button" class="btn small ghost" @click="emit('refresh')">刷新</button>
      </header>
      <dl class="schedule-dl">
        <div class="schedule-row">
          <dt>调度类型</dt>
          <dd>{{ scheduleTypeLabel(deployment.schedule_type) }}</dd>
        </div>
        <template v-for="row in scheduleInfoRows" :key="row.label">
          <div class="schedule-row">
            <dt>{{ row.label }}</dt>
            <dd :class="{ mono: row.mono, muted: row.muted }">{{ row.value }}</dd>
          </div>
        </template>
        <div class="schedule-divider" aria-hidden="true" />
        <div class="schedule-row">
          <dt>配置节点</dt>
          <dd>{{ configuredWorkersText }}</dd>
        </div>
        <div class="schedule-row">
          <dt>当前分配</dt>
          <dd>
            <ul v-if="assignmentLines.length" class="assign-lines">
              <li v-for="(line, i) in assignmentLines" :key="i" class="assign-line">
                <span class="assign-role">{{ line.role }}</span>
                <span class="mono assign-id">{{ line.workerId }}</span>
                <span
                  v-if="line.workerStatus"
                  class="tag small"
                  :class="workerStatusClass(line.workerStatus)"
                >{{ workerStatusLabel(line.workerStatus) }}</span>
                <span v-if="line.lease" class="muted small assign-lease">{{ line.lease }}</span>
              </li>
            </ul>
            <span v-else class="muted">未分配</span>
          </dd>
        </div>
      </dl>
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
  assignmentRoleLabel,
  buildDeploymentConfigSections,
  buildDeploymentOverviewAlerts,
  computeCronNextRunIso,
  configuredWorkerCount,
  countRunsByStatus,
  groupAssignmentsByRole,
  messageStatusLabel,
  runStatusLabel,
  scheduleTypeLabel,
  subscriptionFieldsFromScheduleConfig,
  truncateOverviewText,
  workerPolicyTypeLabel,
  workerStatusLabel,
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

type ScheduleInfoRow = { label: string; value: string; mono?: boolean; muted?: boolean };

const scheduleInfoRows = computed((): ScheduleInfoRow[] => {
  const st = props.deployment.schedule_type;
  if (st === "cron") {
    const rows: ScheduleInfoRow[] = [];
    if (cronExpr.value) {
      rows.push({ label: "定时设定", value: cronExpr.value, mono: true });
    }
    if (cronNextRunIso.value) {
      rows.push({ label: "下次运行", value: props.formatTs(cronNextRunIso.value), mono: true });
    } else if (cronExpr.value) {
      rows.push({ label: "下次运行", value: "表达式无法解析", muted: true });
    }
    return rows;
  }
  if (st === "subscription") {
    return [
      { label: "消费者", value: consumerId.value || "—", mono: true },
      {
        label: "并发上限",
        value: subFields.value.max_in_flight != null ? String(subFields.value.max_in_flight) : "—",
        mono: true,
      },
    ];
  }
  return [];
});

const configuredWorkersText = computed(() => {
  const n = configuredWorkerCount(props.deployment.worker_policy);
  const typeRaw = props.deployment.worker_policy?.type;
  const typeLabel = typeRaw ? workerPolicyTypeLabel(String(typeRaw)) : "";
  if (n != null && typeLabel) return `${n} 个节点 · ${typeLabel}`;
  if (n != null) return `${n} 个节点`;
  if (typeLabel) return typeLabel;
  return "—";
});

type AssignmentLine = {
  role: string;
  workerId: string;
  workerStatus: string | null;
  lease: string | null;
};

const assignmentLines = computed((): AssignmentLine[] => {
  const by = groupAssignmentsByRole(props.deployment.assignments);
  const lines: AssignmentLine[] = [];
  for (const role of ["leader", "standby", "replica"] as const) {
    for (const a of by[role]) {
      const w = props.workers.find((x) => x.worker_id === a.worker_id);
      lines.push({
        role: assignmentRoleLabel(role),
        workerId: a.worker_id,
        workerStatus: w ? String(w.status) : null,
        lease: a.lease_expires_at ? `租约 ${props.formatTs(a.lease_expires_at)}` : null,
      });
    }
  }
  for (const a of by.other) {
    const w = props.workers.find((x) => x.worker_id === a.worker_id);
    lines.push({
      role: assignmentRoleLabel(a.role),
      workerId: a.worker_id,
      workerStatus: w ? String(w.status) : null,
      lease: a.lease_expires_at ? `租约 ${props.formatTs(a.lease_expires_at)}` : null,
    });
  }
  return lines;
});

function workerStatusClass(status: string): string {
  if (status === "active") return "ok";
  if (status === "dead") return "dead";
  return "info";
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

/* —— 调度与部署 —— */
.schedule-panel {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.schedule-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.schedule-panel-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
}

.schedule-dl {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.schedule-row {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 10px 16px;
  align-items: start;
  font-size: 12px;
}

.schedule-row dt {
  margin: 0;
  color: var(--muted);
  font-weight: 600;
  line-height: 1.45;
}

.schedule-row dd {
  margin: 0;
  font-weight: 600;
  line-height: 1.45;
  min-width: 0;
  word-break: break-word;
}

.schedule-row dd.muted {
  font-weight: 500;
}

.schedule-divider {
  height: 1px;
  background: var(--border);
  margin: 2px 0;
}

.assign-lines {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.assign-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.assign-role {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
  min-width: 52px;
}

.assign-id {
  font-weight: 700;
}

.assign-lease {
  flex-basis: 100%;
  padding-left: 58px;
  font-size: 10px;
}

.tag.dead {
  background: color-mix(in srgb, #94a3b8 18%, transparent);
  color: #475569;
  border-color: color-mix(in srgb, #94a3b8 40%, transparent);
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
  .ov-two-col {
    grid-template-columns: 1fr;
  }

  .config-rows {
    grid-template-columns: 1fr;
  }
}
</style>
