/** Build / validate SubscriptionSpec JSON for deployment schedule_config. */

import {
  buildParseSectionFromIngressMapping,
  type ContextMappingState,
} from "@/operations/contextMappingConfig";

export type { ContextMappingState, ContextMappingState as IngressMappingState } from "@/operations/contextMappingConfig";
export {
  DEFAULT_INGRESS_MAPPING,
  DEFAULT_INGRESS_MAPPING as DEFAULT_CONTEXT_MAPPING,
} from "@/operations/contextMappingConfig";

/** Empty = not chosen yet (UI placeholder). */
export type StartPositionMode = "" | "default" | "earliest" | "latest" | "offset" | "timestamp";

export type SubscriptionFormState = {
  consumer_id: string;
  start_position_mode: StartPositionMode;
  /** partition:offset pairs, e.g. "0:100, 1:200" */
  offsetsText: string;
  /** Unix epoch ms for timestamp mode */
  timestamp_ms: number;
  partitionsText: string;
  batch_max_records: number;
  poll_timeout_ms: number;
  max_in_flight: number;
  /** 0 = omit (backend default) */
  run_timeout_s: number;
  idempotencyEnabled: boolean;
  idempotency_window_s: number;
  /** Data-dictionary producer_id for DLQ publish */
  dlq_producer_id: string;
  ingress_max_restarts: number;
  ingress_restart_backoff_s: number;
};

export const DEFAULT_SUBSCRIPTION_FORM: SubscriptionFormState = {
  consumer_id: "",
  start_position_mode: "",
  offsetsText: "",
  timestamp_ms: 0,
  partitionsText: "",
  batch_max_records: 100,
  poll_timeout_ms: 1000,
  max_in_flight: 8,
  run_timeout_s: 0,
  idempotencyEnabled: false,
  idempotency_window_s: 86400,
  dlq_producer_id: "",
  ingress_max_restarts: 5,
  ingress_restart_backoff_s: 30,
};

export function parsePartitionsText(raw: string): number[] | null {
  const t = raw.trim();
  if (!t) return null;
  const parts = t.split(/[\s,]+/).filter(Boolean);
  const out: number[] = [];
  for (const p of parts) {
    const n = Number(p);
    if (!Number.isInteger(n) || n < 0) return null;
    out.push(n);
  }
  return out.length ? out : null;
}

/** Parse `0:100, 1:200` or `0=100` into partition → offset map. */
export function parseOffsetsText(raw: string): Record<number, number> | null {
  const t = raw.trim();
  if (!t) return null;
  const out: Record<number, number> = {};
  for (const part of t.split(/[\s,]+/).filter(Boolean)) {
    const m = part.match(/^(\d+)\s*[:=]\s*(\d+)$/);
    if (!m) return null;
    const partition = Number(m[1]);
    const offset = Number(m[2]);
    if (!Number.isInteger(partition) || partition < 0) return null;
    if (!Number.isInteger(offset) || offset < 0) return null;
    out[partition] = offset;
  }
  return Object.keys(out).length ? out : null;
}

export function buildStartPosition(
  form: Pick<SubscriptionFormState, "start_position_mode" | "offsetsText" | "timestamp_ms">,
): { ok: true; value: string | Record<string, unknown> | undefined } | { ok: false; error: string } {
  const mode = form.start_position_mode;
  if (!mode) {
    return { ok: false, error: "请选择从哪条消息开始读" };
  }
  if (mode === "default") {
    return { ok: true, value: "default" };
  }
  if (mode === "earliest" || mode === "latest") {
    return { ok: true, value: mode };
  }
  if (mode === "offset") {
    const offsets = parseOffsetsText(form.offsetsText);
    if (!offsets) {
      return {
        ok: false,
        error: "指定位点需填写分区 offset，格式如 0:100, 1:200（分区:offset）",
      };
    }
    return { ok: true, value: { mode: "offset", offsets } };
  }
  const ts = Number(form.timestamp_ms);
  if (!Number.isFinite(ts) || ts <= 0) {
    return { ok: false, error: "按时间消费需填写有效的起始时间（毫秒时间戳）" };
  }
  return { ok: true, value: { mode: "timestamp", timestamp_ms: Math.floor(ts) } };
}

export function buildSubscriptionScheduleConfig(
  form: SubscriptionFormState,
  mapping: ContextMappingState,
): { ok: true; config: Record<string, unknown> } | { ok: false; error: string } {
  if (!form.consumer_id.trim()) {
    return { ok: false, error: "请填写消息消费者 ID（数据字典中的 consumer_id）" };
  }

  const partitions = parsePartitionsText(form.partitionsText);
  if (form.partitionsText.trim() && partitions === null) {
    return { ok: false, error: "分区列表格式无效，请使用逗号分隔的非负整数，如 0,1,2" };
  }

  const startPos = buildStartPosition(form);
  if (!startPos.ok) {
    return startPos;
  }

  const parseBuilt = buildParseSectionFromIngressMapping(mapping);
  if (!parseBuilt.ok) return parseBuilt;
  const parse = parseBuilt.parse;

  const consumption: Record<string, unknown> = {
    batch_max_records: Math.max(1, Math.min(10_000, Number(form.batch_max_records) || 100)),
    poll_timeout_ms: Math.max(100, Math.min(60_000, Number(form.poll_timeout_ms) || 1000)),
    commit_policy: "on_success",
  };

  if (form.idempotencyEnabled) {
    const window_s = Math.max(1, Number(form.idempotency_window_s) || 86400);
    consumption.idempotency = { window_s };
  }

  const dlqProducer = form.dlq_producer_id.trim();
  if (dlqProducer) {
    consumption.dlq = { producer_id: dlqProducer };
  }

  const dispatch: Record<string, unknown> = {
    max_in_flight: Math.max(1, Math.min(500, Number(form.max_in_flight) || 8)),
  };
  const runTimeout = Number(form.run_timeout_s);
  if (runTimeout > 0) {
    dispatch.run_timeout_s = Math.max(1, runTimeout);
  }

  const subscription: Record<string, unknown> = {
    consumer_id: form.consumer_id.trim(),
  };
  subscription.start_position = startPos.value;
  if (partitions?.length) {
    subscription.partitions = partitions;
  }

  return {
    ok: true,
    config: {
      schema_version: 1,
      subscription,
      consumption,
      dispatch,
      parse,
      ingress_policy: {
        max_restarts: Math.max(0, Number(form.ingress_max_restarts) || 0),
        restart_backoff_s: Math.max(1, Number(form.ingress_restart_backoff_s) || 30),
      },
    },
  };
}
