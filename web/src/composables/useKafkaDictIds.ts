import { ref, watch, type Ref } from "vue";
import { fetchDictResolved } from "@/api/dict";
import { extractKafkaDictIds, type KafkaDictIds } from "@/operations/kafkaDictIds";

const cache = new Map<string, KafkaDictIds>();
const inflight = new Map<string, Promise<KafkaDictIds>>();

function cacheKey(profileCode: string): string {
  return profileCode.trim() || "__default__";
}

export async function loadKafkaDictIds(profileCode: string): Promise<KafkaDictIds> {
  const key = cacheKey(profileCode);
  const hit = cache.get(key);
  if (hit) return hit;

  let pending = inflight.get(key);
  if (!pending) {
    pending = (async () => {
      const profile = profileCode.trim();
      const res = await fetchDictResolved(profile);
      const ids = extractKafkaDictIds(res.resolved_dictionary ?? {});
      cache.set(key, ids);
      inflight.delete(key);
      return ids;
    })();
    inflight.set(key, pending);
  }
  return pending;
}

export function useKafkaDictIds(profileCode: Ref<string>) {
  const consumers = ref<string[]>([]);
  const producers = ref<string[]>([]);
  const loading = ref(false);
  const error = ref("");

  async function reload() {
    loading.value = true;
    error.value = "";
    try {
      const ids = await loadKafkaDictIds(profileCode.value);
      consumers.value = ids.consumers;
      producers.value = ids.producers;
    } catch (e) {
      consumers.value = [];
      producers.value = [];
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  }

  watch(profileCode, () => void reload(), { immediate: true });

  return { consumers, producers, loading, error, reload };
}
