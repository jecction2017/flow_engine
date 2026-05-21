/** Build / validate SubscriptionSpec JSON for deployment schedule_config. */

export type SubscriptionFormState = {
  consumer_id: string;
  producer_id: string;
  start_position: "latest" | "earliest";
  partitionsText: string;
  batch_max_records: number;
  poll_timeout_ms: number;
  max_in_flight: number;
  /** 0 = omit (backend default) */
  run_timeout_s: number;
  idempotencyEnabled: boolean;
  idempotency_window_s: number;
  dlq_producer_id: string;
  transform: "mapping" | "script";
  scriptText: string;
};

export type ContextMappingState =
  | { mode: "spread" }
  | { mode: "wrap"; wrap_key: string; wrap_as_list?: boolean }
  | { mode: "rules"; rules: Array<{ source: string; target: string }> };

export const DEFAULT_SUBSCRIPTION_FORM: SubscriptionFormState = {
  consumer_id: "memory.alerts.default",
  producer_id: "",
  start_position: "latest",
  partitionsText: "",
  batch_max_records: 100,
  poll_timeout_ms: 1000,
  max_in_flight: 8,
  run_timeout_s: 0,
  idempotencyEnabled: false,
  idempotency_window_s: 86400,
  dlq_producer_id: "",
  transform: "mapping",
  scriptText:
    'payload\n\n{\n  "alert": payload["alert"] if "alert" in payload else payload,\n}',
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

export function buildSubscriptionScheduleConfig(
  form: SubscriptionFormState,
  mapping: ContextMappingState,
  ingressPolicy: { max_restarts: number; restart_backoff_s: number },
): { ok: true; config: Record<string, unknown> } | { ok: false; error: string } {
  if (!form.consumer_id.trim()) {
    return { ok: false, error: "请填写 consumer_id（数据字典 cluster.topic.consumer）" };
  }

  const partitions = parsePartitionsText(form.partitionsText);
  if (form.partitionsText.trim() && partitions === null) {
    return { ok: false, error: "partitions 格式无效，请使用逗号分隔的非负整数，如 0,1,2" };
  }

  let parse: Record<string, unknown>;
  if (form.transform === "script") {
    if (!form.scriptText.trim()) {
      return { ok: false, error: "script 模式必须填写 Starlark 脚本" };
    }
    parse = { codec: "json", transform: "script", script: form.scriptText };
  } else {
    parse = {
      codec: "json",
      transform: "mapping",
      mapping: { ...mapping } as Record<string, unknown>,
    };
  }

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
    start_position: form.start_position,
  };
  const producerId = form.producer_id.trim();
  if (producerId) {
    subscription.producer_id = producerId;
  }
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
        max_restarts: Math.max(0, Number(ingressPolicy.max_restarts) || 0),
        restart_backoff_s: Math.max(1, Number(ingressPolicy.restart_backoff_s) || 30),
      },
    },
  };
}
