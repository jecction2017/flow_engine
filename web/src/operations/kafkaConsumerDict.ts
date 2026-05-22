/** Resolve Kafka consumer specs from a data-dictionary tree (middleware.kafka). */

import type { StartPositionMode, SubscriptionFormState } from "@/operations/subscriptionScheduleConfig";

export type DictKafkaConsumerSpec = {
  group_id: string;
  strategy: unknown;
  partitions: number[] | null;
  params: Record<string, unknown>;
};

function findConsumerNode(
  resolved: Record<string, unknown>,
  consumerId: string,
): Record<string, unknown> | null {
  const parts = consumerId.split(".");
  if (parts.length !== 3) return null;
  const [clusterId, topicName, consumerName] = parts;
  const middleware = resolved.middleware;
  if (!middleware || typeof middleware !== "object") return null;
  const kafka = (middleware as Record<string, unknown>).kafka;
  if (!kafka || typeof kafka !== "object") return null;
  const instances = (kafka as Record<string, unknown>).instances;
  if (!instances || typeof instances !== "object") return null;
  const cluster = (instances as Record<string, unknown>)[clusterId];
  if (!cluster || typeof cluster !== "object") return null;
  const topics = (cluster as Record<string, unknown>).topics;
  if (!topics || typeof topics !== "object") return null;
  const topic = (topics as Record<string, unknown>)[topicName];
  if (!topic || typeof topic !== "object") return null;
  const consumers = (topic as Record<string, unknown>).consumers;
  if (!consumers || typeof consumers !== "object") return null;
  const node = (consumers as Record<string, unknown>)[consumerName];
  if (!node || typeof node !== "object") return null;
  return node as Record<string, unknown>;
}

export function getKafkaConsumerFromDict(
  resolved: Record<string, unknown>,
  consumerId: string,
): DictKafkaConsumerSpec | null {
  const node = findConsumerNode(resolved, consumerId.trim());
  if (!node) return null;
  const groupId = String(node.group_id ?? "").trim();
  if (!groupId) return null;
  const partitionsRaw = node.partitions;
  let partitions: number[] | null = null;
  if (Array.isArray(partitionsRaw) && partitionsRaw.length > 0) {
    const parsed = partitionsRaw
      .map((x) => Number(x))
      .filter((n) => Number.isInteger(n) && n >= 0);
    partitions = parsed.length ? parsed : null;
  }
  const params =
    node.params && typeof node.params === "object"
      ? (node.params as Record<string, unknown>)
      : {};
  return {
    group_id: groupId,
    strategy: node.strategy ?? "default",
    partitions,
    params,
  };
}

/** Map dictionary consumer.strategy → deployment form start_position fields. */
export function strategyToStartPositionFields(strategy: unknown): {
  start_position_mode: StartPositionMode;
  offsetsText: string;
  timestamp_ms: number;
} {
  if (typeof strategy === "string") {
    const mode = strategy.trim() as StartPositionMode;
    if (mode === "default" || mode === "earliest" || mode === "latest") {
      return { start_position_mode: mode, offsetsText: "", timestamp_ms: 0 };
    }
  }
  if (strategy && typeof strategy === "object") {
    const obj = strategy as Record<string, unknown>;
    const mode = String(obj.mode ?? obj.strategy ?? "default").trim();
    if (mode === "offset") {
      const offsets = obj.offsets;
      const text =
        offsets && typeof offsets === "object"
          ? Object.entries(offsets as Record<string, number>)
              .map(([p, o]) => `${p}:${o}`)
              .join(", ")
          : "";
      return { start_position_mode: "offset", offsetsText: text, timestamp_ms: 0 };
    }
    if (mode === "timestamp") {
      const ts = Number(obj.timestamp_ms);
      return {
        start_position_mode: "timestamp",
        offsetsText: "",
        timestamp_ms: Number.isFinite(ts) && ts > 0 ? Math.floor(ts) : 0,
      };
    }
    if (mode === "earliest" || mode === "latest" || mode === "default") {
      return { start_position_mode: mode, offsetsText: "", timestamp_ms: 0 };
    }
  }
  return { start_position_mode: "default", offsetsText: "", timestamp_ms: 0 };
}

export function formatPartitionsText(partitions: number[] | null | undefined): string {
  if (!partitions?.length) return "";
  return partitions.join(", ");
}

/** Apply dictionary consumer spec into subscription deployment form (overwrites derived fields). */
export function applyDictConsumerToForm(
  form: SubscriptionFormState,
  spec: DictKafkaConsumerSpec,
): void {
  const pos = strategyToStartPositionFields(spec.strategy);
  form.start_position_mode = pos.start_position_mode;
  form.offsetsText = pos.offsetsText;
  form.timestamp_ms = pos.timestamp_ms;
  // 指定分区 offset 时与「只监听部分分区」冲突，不填 partitions
  form.partitionsText =
    pos.start_position_mode === "offset" ? "" : formatPartitionsText(spec.partitions);
}

export function clearConsumerDerivedFormFields(form: SubscriptionFormState): void {
  form.start_position_mode = "";
  form.offsetsText = "";
  form.timestamp_ms = 0;
  form.partitionsText = "";
}
