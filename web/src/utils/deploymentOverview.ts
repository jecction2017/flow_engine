/** Labels and helpers for deployment detail overview (运行中心 · 管理详情 · 概览). */

import type { Deployment, DeploymentDetail, WorkerTargeting } from "@/api/deployments";
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

export function deploymentScheduleSubtitle(
  d: Deployment,
  subSummary: SubscriptionSummary | null,
): string {
  const env = d.env_profile_code || "—";
  const st = scheduleTypeLabel(String(d.schedule_type));
  if (d.schedule_type === "cron") {
    const expr = d.schedule_config?.cron_expr;
    return expr ? `${st} · ${expr} · 环境 ${env}` : `${st} · 环境 ${env}`;
  }
  if (d.schedule_type === "subscription") {
    const consumer = subSummary?.consumer_id;
    return consumer ? `${st} · ${consumer} · 环境 ${env}` : `${st} · 环境 ${env}`;
  }
  return `${st} · 环境 ${env}`;
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

export function truncateOverviewText(text: string | null | undefined, maxLen: number): string {
  const t = String(text ?? "").trim();
  if (!t) return "—";
  if (t.length <= maxLen) return t;
  return `${t.slice(0, maxLen)}…`;
}
