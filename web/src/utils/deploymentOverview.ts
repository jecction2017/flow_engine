/** Labels and helpers for deployment detail overview (运行中心 · 管理详情 · 概览). */

import { parseExpression } from "cron-parser";
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

export function workerPolicySummary(policy: Deployment["worker_policy"], scheduleType?: string): string {
  const parts: string[] = [];
  if (policy?.type) parts.push(workerPolicyTypeLabel(String(policy.type)));
  const countLabel = workerPolicyCountLabel(policy, scheduleType);
  if (countLabel) parts.push(countLabel);
  if (policy?.max_restarts != null) parts.push(`最多重启 ${policy.max_restarts} 次`);
  if (policy?.restart_backoff_s != null) parts.push(`退避 ${policy.restart_backoff_s}s`);
  return parts.length ? parts.join(" · ") : "默认";
}

/** 配置页 Worker 策略行：仅模式与节点数，不含重启退避（避免与接入重试等重复）。 */
export function workerPolicyConfigLabel(policy: Deployment["worker_policy"], scheduleType?: string): string {
  const parts: string[] = [];
  if (policy?.type) parts.push(workerPolicyTypeLabel(String(policy.type)));
  const countLabel = workerPolicyCountLabel(policy, scheduleType);
  if (countLabel) parts.push(countLabel);
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
  if (r === "leader") return "主节点";
  if (r === "standby") return "备用";
  if (r === "replica") return "副本";
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

/** Cron template is actively scheduled (Coordinator only fires when status is running). */
export function isCronScheduleActive(d: Pick<Deployment, "schedule_type" | "status">): boolean {
  return String(d.schedule_type) === "cron" && String(d.status) === "running";
}

/** Next cron fire (UTC ISO) from now; null if expression invalid or empty. */
export function computeCronNextRunIso(cronExpr: string | undefined | null): string | null {
  const expr = String(cronExpr ?? "").trim();
  if (!expr) return null;
  try {
    const it = parseExpression(expr, { utc: true, currentDate: new Date() });
    return it.next().toDate().toISOString();
  } catch {
    return null;
  }
}

export function targetWorkersFromPolicy(policy: Deployment["worker_policy"]): number | null {
  const p = policy ?? {};
  const raw = p.target_workers ?? (p as { min_workers?: number }).min_workers;
  if (typeof raw === "number" && Number.isFinite(raw)) return Math.max(1, Math.floor(raw));
  return null;
}

export function configuredWorkerCount(policy: Deployment["worker_policy"]): number | null {
  return targetWorkersFromPolicy(policy);
}

export function workerPolicyCountLabel(
  policy: Deployment["worker_policy"],
  scheduleType?: string,
): string | null {
  const n = targetWorkersFromPolicy(policy);
  if (n == null) return null;
  const type = String(policy?.type ?? "single_active");
  const st = String(scheduleType ?? "");
  if (st === "once") return "1 节点";
  if (type === "multi_active") return `目标 ${n} 并发`;
  const standby = Math.max(0, n - 1);
  if (standby === 0) return "1 主节点";
  return `1 主 + ${standby} 备`;
}

export type ScheduleTriggerChip = {
  label: string;
  value: string;
  mono?: boolean;
  highlight?: boolean;
  muted?: boolean;
  /** 订阅等场景：消费者占宽、并发上限占窄 */
  layout?: "wide" | "compact";
};

export type RoleBlockKey = "leader" | "standby" | "replica";

export type RoleBindKind = "any" | "specified";

/** How the worker shown in a role block relates to assignment / targeting. */
export type RoleOccupancy = "assigned_ok" | "assigned_weak" | "vacant";

export type WorkerChipView = {
  key: string;
  role: RoleBlockKey;
  roleLabel: string;
  bindKind: RoleBindKind;
  occupancy: RoleOccupancy;
  workerId: string | null;
  workerStatus: string | null;
  title: string | null;
};

export type ScheduleNodeOverview = {
  scheduleTypeLabel: string;
  triggerChips: ScheduleTriggerChip[];
  policyTypeLabel: string;
  allocationRatio: string;
  allocationTone: "ok" | "warn" | "muted";
  /** Pin / pool worker ids for inline「绑定」segment; null when targeting is any. */
  bindingIds: string | null;
  workerChips: WorkerChipView[];
};

function bindingIdsForTargeting(targeting: WorkerTargeting | undefined): string | null {
  if (!targeting) return null;
  if (targeting.mode === "pin") {
    const id = String(targeting.worker_id ?? "").trim();
    return id || null;
  }
  if (targeting.mode === "pool") {
    const ids = (targeting.worker_ids || []).map((x) => String(x).trim()).filter(Boolean);
    return ids.length ? ids.join(" ") : null;
  }
  return null;
}

function assignmentsForRoleSlots(
  roles: RoleBlockKey[],
  by: AssignmentsByRole,
): (Assignment | null)[] {
  const cursor: Record<RoleBlockKey, number> = { leader: 0, standby: 0, replica: 0 };
  return roles.map((role) => {
    const list = by[role];
    const idx = cursor[role];
    cursor[role] += 1;
    return list[idx] ?? null;
  });
}

function roleSkeleton(policyType: string | undefined, configured: number | null): RoleBlockKey[] {
  if (policyType === "single_active") {
    const n = Math.max(configured ?? 1, 1);
    const roles: RoleBlockKey[] = ["leader"];
    for (let i = 1; i < n; i++) roles.push("standby");
    return roles.length ? roles : ["leader"];
  }
  const n = Math.max(configured ?? 1, 1);
  return Array.from({ length: n }, () => "replica" as RoleBlockKey);
}

function specifiedWorkerIds(targeting: WorkerTargeting | undefined): string[] {
  if (!targeting) return [];
  if (targeting.mode === "pin") {
    const id = String(targeting.worker_id ?? "").trim();
    return id ? [id] : [];
  }
  if (targeting.mode === "pool") {
    return (targeting.worker_ids || []).map((x) => String(x).trim()).filter(Boolean);
  }
  return [];
}

function isDeploymentLive(status: string): boolean {
  return status === "running" || status === "pending";
}

function isWorkerHealthy(status: string | null): boolean {
  return status === "active";
}

function resolveWorkerChip(
  role: RoleBlockKey,
  slotIndex: number,
  assignment: Assignment | null,
  specifiedId: string | null,
  workerStatus: (workerId: string) => string | null,
  deploymentStatus: string,
  formatTs: (iso: string | null) => string,
): WorkerChipView {
  const roleName = assignmentRoleLabel(role);
  const key = `role-${role}-${slotIndex}`;

  if (!assignment) {
    const titleParts = [`${roleName} · 待分配`];
    if (specifiedId) titleParts.push(`指定 ${specifiedId}`);
    if (!isDeploymentLive(deploymentStatus)) {
      titleParts.push(deploymentStatus === "stopped" ? "部署未启动" : "部署未在运行");
    }
    return {
      key,
      role,
      roleLabel: roleName,
      bindKind: specifiedId ? "specified" : "any",
      occupancy: "vacant",
      workerId: null,
      workerStatus: null,
      title: titleParts.join(" · "),
    };
  }

  const bindKind: RoleBindKind = specifiedId ? "specified" : "any";
  const live = isDeploymentLive(deploymentStatus);
  const st = workerStatus(assignment.worker_id);
  let occupancy: RoleOccupancy = "assigned_ok";
  const titleParts = [`${roleName}`, assignment.worker_id];
  if (assignment.lease_expires_at) {
    titleParts.push(`租约 ${formatTs(assignment.lease_expires_at)}`);
  }

  if (specifiedId && assignment.worker_id !== specifiedId) {
    occupancy = "assigned_weak";
    titleParts.push(`与指定 ${specifiedId} 不一致`);
  } else if (!live) {
    occupancy = "assigned_weak";
    titleParts.push(deploymentStatus === "stopped" ? "部署已停止" : "部署未在运行");
  } else if (!isWorkerHealthy(st)) {
    occupancy = "assigned_weak";
    if (st) titleParts.push(workerStatusLabel(st));
  } else if (bindKind === "specified") {
    titleParts.push("已绑定");
  } else {
    titleParts.push("已分配");
  }

  return {
    key,
    role,
    roleLabel: roleName,
    bindKind,
    occupancy,
    workerId: assignment.worker_id,
    workerStatus: st,
    title: titleParts.join(" · "),
  };
}

/** Structured model for deployment overview schedule + node panel. */
export function buildScheduleNodeOverview(
  d: DeploymentDetail,
  workerStatus: (workerId: string) => string | null,
  opts: {
    cronNextIso: string | null;
    formatTs: (iso: string | null) => string;
    consumerId: string | null;
    maxInFlight: number | null;
  },
): ScheduleNodeOverview {
  const st = String(d.schedule_type);
  const typeLabel = scheduleTypeLabel(st);
  const triggerChips: ScheduleTriggerChip[] = [];

  if (st === "cron") {
    const expr = String(d.schedule_config?.cron_expr ?? "").trim();
    if (expr) triggerChips.push({ label: "Cron", value: expr, mono: true });
    const cronScheduled = isCronScheduleActive(d);
    if (!cronScheduled) {
      triggerChips.push({ label: "下次运行", value: "无", muted: true });
    } else if (opts.cronNextIso) {
      triggerChips.push({
        label: "下次运行",
        value: opts.formatTs(opts.cronNextIso),
        mono: true,
        highlight: true,
      });
    } else if (expr) {
      triggerChips.push({ label: "下次运行", value: "表达式无法解析", muted: true });
    } else {
      triggerChips.push({ label: "下次运行", value: "无", muted: true });
    }
  } else if (st === "subscription") {
    triggerChips.push({
      label: "消费者",
      value: opts.consumerId || "—",
      mono: true,
      layout: "wide",
    });
    if (opts.maxInFlight != null) {
      triggerChips.push({
        label: "并发上限",
        value: String(opts.maxInFlight),
        mono: true,
        layout: "compact",
      });
    }
  } else {
    triggerChips.push({
      label: "触发",
      value: "手动启动后执行，无自动调度",
      muted: true,
    });
  }

  const configured = configuredWorkerCount(d.worker_policy);
  const policyType = d.worker_policy?.type ? String(d.worker_policy.type) : undefined;
  const policyTypeLabel = policyType ? workerPolicyTypeLabel(policyType) : "默认";
  const specifiedIds = specifiedWorkerIds(d.worker_targeting);

  const by = groupAssignmentsByRole(d.assignments);
  const assigned = d.assignments?.length ?? 0;
  const roles = roleSkeleton(policyType, configured);
  const slotAssignments = assignmentsForRoleSlots(roles, by);

  const workerChips = roles.map((role, index) =>
    resolveWorkerChip(
      role,
      index,
      slotAssignments[index] ?? null,
      specifiedIds[index] ?? null,
      workerStatus,
      String(d.status),
      opts.formatTs,
    ),
  );

  let allocationRatio: string;
  let allocationTone: ScheduleNodeOverview["allocationTone"] = "muted";
  if (configured != null) {
    allocationRatio = `${assigned}/${configured}`;
    if (assigned === 0) allocationTone = "warn";
    else if (assigned < configured) allocationTone = "warn";
    else allocationTone = "ok";
  } else {
    allocationRatio = String(assigned);
    allocationTone = assigned > 0 ? "ok" : "warn";
  }

  return {
    scheduleTypeLabel: typeLabel,
    triggerChips,
    policyTypeLabel,
    allocationRatio,
    allocationTone,
    bindingIds: bindingIdsForTargeting(d.worker_targeting),
    workerChips,
  };
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
  const policy = workerPolicySummary(d.worker_policy, String(d.schedule_type));
  const target = workerTargetingLabel(d.worker_targeting);
  const extras = [policy !== "默认" ? policy : "", target !== "任意节点" ? target : ""].filter(Boolean);

  if (d.schedule_type === "cron") {
    const expr = String(d.schedule_config?.cron_expr ?? "").trim();
    let next = "";
    if (isCronScheduleActive(d)) {
      next = opts.cronNextIso ? `下次 ${opts.formatTs(opts.cronNextIso)}` : "";
    }
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
    head = configured != null ? `未分配（目标 ${configured} 个节点）` : "未分配";
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
      { label: "策略", value: workerPolicyConfigLabel(d.worker_policy, String(d.schedule_type)) },
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

export function formatDeploymentConfigJson(d: DeploymentDetail): string {
  return JSON.stringify(
    {
      schedule_config: d.schedule_config,
      worker_policy: d.worker_policy,
      capability_policy: d.capability_policy,
      worker_targeting: d.worker_targeting,
      env_profile_code: d.env_profile_code,
    },
    null,
    2,
  );
}
