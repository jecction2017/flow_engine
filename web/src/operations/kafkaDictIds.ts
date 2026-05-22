/** Extract Kafka consumer/producer IDs from a resolved data dictionary tree. */

export type KafkaDictIds = {
  consumers: string[];
  producers: string[];
};

function collectIds(
  resolved: Record<string, unknown>,
  bucketKey: "consumers" | "producers",
): string[] {
  const middleware = resolved.middleware;
  if (!middleware || typeof middleware !== "object") return [];
  const kafka = (middleware as Record<string, unknown>).kafka;
  if (!kafka || typeof kafka !== "object") return [];
  const instances = (kafka as Record<string, unknown>).instances;
  if (!instances || typeof instances !== "object") return [];

  const ids: string[] = [];
  for (const [clusterId, cluster] of Object.entries(instances as Record<string, unknown>)) {
    if (!cluster || typeof cluster !== "object") continue;
    const topics = (cluster as Record<string, unknown>).topics;
    if (!topics || typeof topics !== "object") continue;
    for (const [topicName, topic] of Object.entries(topics as Record<string, unknown>)) {
      if (!topic || typeof topic !== "object") continue;
      const bucket = (topic as Record<string, unknown>)[bucketKey];
      if (!bucket || typeof bucket !== "object") continue;
      for (const name of Object.keys(bucket)) {
        ids.push(`${clusterId}.${topicName}.${name}`);
      }
    }
  }
  return ids.sort((a, b) => a.localeCompare(b));
}

export function extractKafkaDictIds(resolved: Record<string, unknown>): KafkaDictIds {
  return {
    consumers: collectIds(resolved, "consumers"),
    producers: collectIds(resolved, "producers"),
  };
}

export function filterKafkaIds(ids: string[], query: string, limit = 80): string[] {
  const q = query.trim().toLowerCase();
  if (!q) return ids.slice(0, limit);
  const matched = ids.filter((id) => id.toLowerCase().includes(q));
  return matched.slice(0, limit);
}
