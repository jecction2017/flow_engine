/** Labels and helpers for deployment detail overview (运行中心 · 管理详情 · 概览). */

import { CronExpressionParser } from "cron-parser";
import type { Assignment, Deployment, DeploymentDetail, WorkerTargeting } from "@/api/deployments";
import type { SubscriptionSummary } from "@/api/subscriptionObservability";
import type { FlowRunSummary } from "@/api/flowRuns";

export function deploymentStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: "等待调度",
    running: "运行中",
    stopping: "停止中",
    stopped: "已停止",
    failed: "失败",
  };
  return map[status] ?? status;
}

export function deploymentModeLabel(mode: string): string {
  if (mode === "production") return "生产";
  if (mode === "shadow") return "灰度";
  return mode;
}

/** CSS modifier for deployment mode (not lifecycle status). */
export function deploymentModeMod(mode: string): string {
  if (mode === "shadow") return "dep-mode--shadow";
  if (mode === "production") return "dep-mode--production";
  return "";
}

/** List card modifier — production vs shadow lane color. */
export function deploymentListItemMod(mode: string): string {
  if (mode === "shadow") return "dep2-item--shadow";
  if (mode === "production") return "dep2-item--production";
  return "";
}

/** Flow run / deploy run mode (debug is ad-hoc and test paths only). */
export function runModeLabel(mode: string): string {
  const map: Record<string, string> = {
    debug: "调试",
    production: "生产",
    shadow: "灰度",
  };
  return map[mode] ?? mode;
}

export function workerStatusLabel(status: string): string {
  const map: Record<string, string> = {
    active: "在线",
    idle: "空闲",
    dead: "离线",
  };
  return map[status] ?? status;
}

export function scheduleTypeLabel(scheduleType: string): string {
  const map: Record<string, string> = {
    once: "单次运行",
    cron: "定时（Cron）",
    subscription: "消息触发",
  };
  return map[scheduleType] ?? scheduleType;
}

export function runStatusLabel(status: string): string {
  const map: Record<string, string> = {
    running: "运行中",
    completed: "已完成",
    failed: "失败",
    terminated: "已终止",
  };
  return map[status] ?? status;
}

export function messageStatusLabel(status: string): string {
  const map: Record<string, string> = {
    processing: "处理中",
    completed: "已完成",
    failed: "失败",
  };
  return map[status] ?? status;
}

export function workerTargetingLabel(targeting: WorkerTargeting | undefined): string {
  if (!targeting) return "任意节点";
  if (targeting.mode === "pin") return `绑定 ${targeting.worker_id}`;
  if (targeting.mode === "pool") {
    const ids = (targeting.worker_ids || []).join(", ");
    return ids ? `节点池 ${ids}` : "节点池（空）";
  }
  return "任意节点";
}

/** Display label for env_profile_code; empty means platform default profile. */
export function deploymentEnvLabel(envProfileCode: string | undefined | null): string {
  const code = (envProfileCode || "").trim();
  return code || "默认";
}

export function deploymentScheduleSubtitle(
  d: Deployment,
  _subSummary: SubscriptionSummary | null,
): string {
  const env = deploymentEnvLabel(d.env_profile_code);
  const st = scheduleTypeLabel(String(d.schedule_type));
  if (d.schedule_type === "cron") {
    const expr = d.schedule_config?.cron_expr;
    return expr ? `${st} · ${expr} · 环境-${env}` : `${st} · 环境-${env}`;
  }
  return `${st} · 环境-${env}`;
}

export function statusDetailReasonLabel(detail: Record<string, unknown> | null | undefined): string {
  const reason = String(detail?.reason || "").trim();
  if (reason === "no_eligible_worker") return "无可用工作节点";
  if (reason === "pin_worker_offline") return "绑定节点离线";
  if (reason === "subscription_ingress_failed") return "订阅接入失败";
  if (reason === "subscription_ingress_retrying") return "订阅接入重试中";
  return reason || "异常";
}

export function statusDetailMessage(detail: Record<string, unknown> | null | undefined): string {
  const msg = detail?.message;
  return typeof msg === "string" ? msg : "";
}

export function statusDetailWhen(detail: Record<string, unknown> | null | undefined): string | null {
  const ts = detail?.ts;
  return typeof ts === "string" ? ts : null;
}

export function statusDetailWorker(detail: Record<string, unknown> | null | undefined): string | null {
  const w = detail?.worker_id;
  return typeof w === "string" && w ? w : null;
}

export function statusDetailQueuedFailed(detail: Record<string, unknown> | null | undefined): number | null {
  const n = detail?.queued_failed;
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}

export function statusDetailActiveCount(detail: Record<string, unknown> | null | undefined): number | null {
  const n = detail?.active_worker_count;
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}

export function statusDetailPool(detail: Record<string, unknown> | null | undefined): string[] | null {
  const t = detail?.targeting;
  if (t && typeof t === "object" && (t as { mode?: string }).mode === "pool") {
    const ids = (t as { worker_ids?: unknown[] }).worker_ids;
    if (Array.isArray(ids)) {
      return ids.map((x) => String(x)).filter((x) => x);
    }
  }
  return null;
}

export type HealthSuggestedAction = "workers" | "messages" | "runs";

export function statusDetailSuggestedAction(
  detail: Record<string, unknown> | null | undefined,
): HealthSuggestedAction {
  const reason = String(detail?.reason || "").trim();
  if (reason === "no_eligible_worker" || reason === "pin_worker_offline") return "workers";
  if (reason === "subscription_ingress_failed" || reason === "subscription_ingress_retrying") {
    return "messages";
  }
  return "runs";
}

export function statusDetailIngressAttempt(
  detail: Record<string, unknown> | null | undefined,
): number | null {
  const n = detail?.attempt ?? detail?.attempts;
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}

export function statusDetailIngressMaxAttempts(
  detail: Record<string, unknown> | null | undefined,
): number | null {
  const n = detail?.max_attempts;
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}

export function statusDetailNextRetryAt(
  detail: Record<string, unknown> | null | undefined,
): string | null {
  const ts = detail?.next_retry_at;
  return typeof ts === "string" && ts ? ts : null;
}

export function isSubscriptionIngressRetrying(
  detail: Record<string, unknown> | null | undefined,
): boolean {
  return String(detail?.reason || "").trim() === "subscription_ingress_retrying";
}

export function shouldShowHealthBanner(
  d: DeploymentDetail,
  subSummary: SubscriptionSummary | null,
): boolean {
  if (d.status_detail && Object.keys(d.status_detail).length > 0) return true;
  const alertStatuses = new Set(["failed", "stopping", "pending"]);
  if (!alertStatuses.has(String(d.status))) return false;
  const noAssignment = !(d.assignments?.length);
  const msgFailed = (subSummary?.messages.by_status.failed ?? 0) > 0;
  const runFailed = (subSummary?.runs.by_status.failed ?? 0) > 0;
  return noAssignment || msgFailed || runFailed;
}

export function countRunsByStatus(runs: FlowRunSummary[]): {
  total: number;
  running: number;
  completed: number;
  failed: number;
} {
  const out = { total: runs.length, running: 0, completed: 0, failed: 0 };
  for (const r of runs) {
    const st = String(r.status);
    if (st === "running") out.running += 1;
    else if (st === "completed") out.completed += 1;
    else if (st === "failed") out.failed += 1;
  }
  return out;
}

export function workerPolicyTypeLabel(type: string): string {
  if (type === "single_active") return "单活";
  if (type === "multi_active") return "多活";
  return type;
}

export function workerPolicySummary(policy: Deployment["worker_policy"]): string {
  const parts: string[] = [];
  if (policy?.type) parts.push(workerPolicyTypeLabel(String(policy.type)));
  if (policy?.min_workers != null) parts.push(`最少 ${policy.min_workers} 节点`);
  if (policy?.max_restarts != null) parts.push(`最多重启 ${policy.max_restarts} 次`);
  if (policy?.restart_backoff_s != null) parts.push(`退避 ${policy.restart_backoff_s}s`);
  return parts.length ? parts.join(" · ") : "默认";
}

/** 配置页 Worker 策略行：仅模式与节点数，不含重启退避（避免与接入重试等重复）。 */
export function workerPolicyConfigLabel(policy: Deployment["worker_policy"]): string {
  const parts: string[] = [];
  if (policy?.type) parts.push(workerPolicyTypeLabel(String(policy.type)));
  if (policy?.min_workers != null) parts.push(`最少 ${policy.min_workers} 节点`);
  return parts.length ? parts.join(" · ") : "默认";
}

export function truncateOverviewText(text: string | null | undefined, maxLen: number): string {
  const t = String(text ?? "").trim();
  if (!t) return "—";
  if (t.length <= maxLen) return t;
  return `${t.slice(0, maxLen)}…`;
}

export function assignmentRoleLabel(role: string): string {
  const r = String(role || "").toLowerCase();
  if (r === "leader") return "Leader";
  if (r === "standby") return "Standby";
  if (r === "replica") return "Replica";
  return role || "—";
}

export type AssignmentsByRole = {
  leader: Assignment[];
  standby: Assignment[];
  replica: Assignment[];
  other: Assignment[];
};

export function groupAssignmentsByRole(assignments: Assignment[] | undefined): AssignmentsByRole {
  const out: AssignmentsByRole = { leader: [], standby: [], replica: [], other: [] };
  for (const a of assignments ?? []) {
    const r = String(a.role || "").toLowerCase();
    if (r === "leader") out.leader.push(a);
    else if (r === "standby") out.standby.push(a);
    else if (r === "replica") out.replica.push(a);
    else out.other.push(a);
  }
  return out;
}

export function subscriptionFieldsFromScheduleConfig(
  config: Record<string, unknown> | undefined | null,
): { consumer_id: string | null; max_in_flight: number | null } {
  const c = config ?? {};
  const sub = (c.subscription ?? {}) as Record<string, unknown>;
  const dispatch = (c.dispatch ?? {}) as Record<string, unknown>;
  const consumer_id = String(sub.consumer_id ?? "").trim() || null;
  const raw = dispatch.max_in_flight;
  const max_in_flight =
    typeof raw === "number" && Number.isFinite(raw) ? Math.max(1, Math.floor(raw)) : null;
  return { consumer_id, max_in_flight };
}

/** Next cron fire (UTC ISO); null if expression invalid. */
export function computeCronNextRunIso(cronExpr: string | undefined | null): string | null {
  const expr = String(cronExpr ?? "").trim();
  if (!expr) return null;
  try {
    const it = CronExpressionParser.parse(expr, { utc: true });
    return it.next().toDate().toISOString();
  } catch {
    return null;
  }
}

export function configuredWorkerCount(policy: Deployment["worker_policy"]): number | null {
  const n = policy?.min_workers;
  if (typeof n === "number" && Number.isFinite(n)) return Math.max(1, Math.floor(n));
  return null;
}

export type OverviewAlertItem = {
  id: string;
  level: "bad" | "warn";
  title: string;
  detail?: string;
  action?: HealthSuggestedAction;
};

/** 仅返回需要人工处理的告警（不含状态说明类废话）。 */
export function buildDeploymentOverviewAlerts(
  d: DeploymentDetail,
  subSummary: SubscriptionSummary | null,
): OverviewAlertItem[] {
  const items: OverviewAlertItem[] = [];
  const detail = d.status_detail;
  const hasDetail = Boolean(detail && Object.keys(detail).length > 0);
  const st = String(d.status);

  if (st === "failed" || hasDetail) {
    const meta: string[] = [];
    if (detail) {
      const msg = statusDetailMessage(detail);
      if (msg) meta.push(msg);
      const when = statusDetailWhen(detail);
      if (when) meta.push(`时间 ${when}`);
      const att = statusDetailIngressAttempt(detail);
      const maxAtt = statusDetailIngressMaxAttempts(detail);
      if (att != null && maxAtt != null) meta.push(`重试 ${att}/${maxAtt}`);
      const next = statusDetailNextRetryAt(detail);
      if (next) meta.push(`下次重试 ${next}`);
    }
    items.push({
      id: "status-detail",
      level: st === "failed" ? "bad" : "warn",
      title: hasDetail ? statusDetailReasonLabel(detail!) : deploymentStatusLabel(st),
      detail: meta.length ? meta.join(" · ") : undefined,
      action: statusDetailSuggestedAction(detail ?? null),
    });
    return items;
  }

  if (st === "stopping") {
    items.push({
      id: "stopping",
      level: "warn",
      title: "部署正在停止",
      action: "runs",
    });
    return items;
  }

  if (st === "pending" && !(d.assignments?.length)) {
    items.push({
      id: "no-worker",
      level: "warn",
      title: "尚无工作节点分配",
      action: "workers",
    });
  }

  const msgFailed = subSummary?.messages.by_status.failed ?? 0;
  if (d.schedule_type === "subscription" && msgFailed > 0) {
    items.push({
      id: "msg-failed",
      level: "warn",
      title: `${msgFailed} 条消息处理失败`,
    });
  }

  return items;
}

export function deploymentScheduleSubline(
  d: DeploymentDetail,
  opts: {
    cronNextIso: string | null;
    formatTs: (iso: string | null) => string;
    consumerId: string | null;
    maxInFlight: number | null;
  },
): string {
  const policy = workerPolicySummary(d.worker_policy);
  const target = workerTargetingLabel(d.worker_targeting);
  const extras = [policy !== "默认" ? policy : "", target !== "任意节点" ? target : ""].filter(Boolean);

  if (d.schedule_type === "cron") {
    const expr = String(d.schedule_config?.cron_expr ?? "").trim();
    const next = opts.cronNextIso ? `下次 ${opts.formatTs(opts.cronNextIso)}` : "";
    return [expr, next, ...extras].filter(Boolean).join(" · ");
  }

  if (d.schedule_type === "subscription") {
    const cid = opts.consumerId || "—";
    const conc = opts.maxInFlight != null ? `并发上限 ${opts.maxInFlight}` : "";
    return [cid, conc, ...extras].filter(Boolean).join(" · ");
  }

  return extras.join(" · ");
}

export function formatAssignmentSummary(
  d: DeploymentDetail,
  workerStatus: (workerId: string) => string | null,
): string {
  const configured = configuredWorkerCount(d.worker_policy);
  const assigned = d.assignments?.length ?? 0;
  const by = groupAssignmentsByRole(d.assignments);

  let head: string;
  if (assigned === 0) {
    head = configured != null ? `未分配（需 ${configured} 个节点）` : "未分配";
  } else if (configured != null) {
    head = `${assigned}/${configured} 已分配`;
  } else {
    head = `${assigned} 个节点`;
  }

  const roleBits: string[] = [];
  for (const role of ["leader", "standby", "replica"] as const) {
    const list = by[role];
    if (!list.length) continue;
    const ids = list
      .map((a) => {
        const st = workerStatus(a.worker_id);
        return st ? `${a.worker_id}（${workerStatusLabel(st)}）` : a.worker_id;
      })
      .join("、");
    roleBits.push(`${assignmentRoleLabel(role)} ${ids}`);
  }
  if (by.other.length) {
    roleBits.push(`其他 ${by.other.map((a) => a.worker_id).join("、")}`);
  }

  return roleBits.length ? `${head}：${roleBits.join(" · ")}` : head;
}

export type ConfigRow = { label: string; value: string; mono?: boolean };
export type ConfigSection = { title: string; rows: ConfigRow[] };

function formatCapabilityRuleBrief(rule: Deployment["capability_policy"][number]): string {
  const cat = rule.builtin_category ?? "*";
  const name = rule.builtin_name ?? "*";
  return `${cat}/${name} → ${rule.action}`;
}

export function buildDeploymentConfigSections(
  d: DeploymentDetail,
  formatTs: (iso: string | null) => string,
): ConfigSection[] {
  const sections: ConfigSection[] = [];
  const sub = subscriptionFieldsFromScheduleConfig(
    d.schedule_config as Record<string, unknown> | undefined,
  );
  const cfg = (d.schedule_config ?? {}) as Record<string, unknown>;
  const ingress = (cfg.ingress_policy ?? {}) as Record<string, unknown>;

  sections.push({
    title: "标识",
    rows: [
      { label: "流程 / 版本", value: `${d.flow_code}  v${d.ver_no}`, mono: true },
      { label: "部署 ID", value: `#${d.id}`, mono: true },
      { label: "部署方式", value: deploymentModeLabel(d.mode) },
      { label: "环境", value: deploymentEnvLabel(d.env_profile_code) },
      { label: "创建时间", value: d.created_at ? formatTs(d.created_at) : "—", mono: true },
      { label: "更新时间", value: d.updated_at ? formatTs(d.updated_at) : "—", mono: true },
    ],
  });

  const schedRows: ConfigRow[] = [{ label: "类型", value: scheduleTypeLabel(String(d.schedule_type)) }];
  if (d.schedule_type === "cron") {
    const expr = String(d.schedule_config?.cron_expr ?? "").trim();
    if (expr) schedRows.push({ label: "Cron", value: expr, mono: true });
  } else if (d.schedule_type === "subscription") {
    if (sub.consumer_id) schedRows.push({ label: "消费者", value: sub.consumer_id, mono: true });
    if (sub.max_in_flight != null) {
      schedRows.push({ label: "并发上限", value: String(sub.max_in_flight), mono: true });
    }
    const consumption = (cfg.consumption ?? {}) as Record<string, unknown>;
    if (consumption.batch_max_records != null) {
      schedRows.push({
        label: "批大小",
        value: String(consumption.batch_max_records),
        mono: true,
      });
    }
    if (ingress.max_restarts != null || ingress.restart_backoff_s != null) {
      schedRows.push({
        label: "接入重试",
        value: `最多 ${ingress.max_restarts ?? "—"} 次 · 退避 ${ingress.restart_backoff_s ?? "—"}s`,
      });
    }
  }
  sections.push({ title: "调度", rows: schedRows });

  sections.push({
    title: "Worker",
    rows: [
      { label: "策略", value: workerPolicyConfigLabel(d.worker_policy) },
      { label: "定向", value: workerTargetingLabel(d.worker_targeting) },
    ],
  });

  const rules = d.capability_policy ?? [];
  if (rules.length) {
    sections.push({
      title: "能力策略",
      rows: rules.map((r, i) => ({
        label: `#${i + 1}`,
        value: formatCapabilityRuleBrief(r),
        mono: true,
      })),
    });
  }

  return sections;
}
