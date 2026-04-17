import { ref, type Ref } from "vue";
import { fetchStarlarkRegistry, type RegistryDoc } from "@/api/starlark";

const registryRef = ref<RegistryDoc | null>(null);
let inflight: Promise<RegistryDoc> | null = null;

/** Shared lazy-loaded registry for editors (e.g. Flow Studio task script). */
export function useStarlarkRegistryCache(): {
  registry: Ref<RegistryDoc | null>;
  ensureRegistry: () => Promise<RegistryDoc | null>;
} {
  async function ensureRegistry(): Promise<RegistryDoc | null> {
    if (registryRef.value) return registryRef.value;
    if (!inflight) {
      inflight = fetchStarlarkRegistry()
        .then((r) => {
          registryRef.value = r;
          return r;
        })
        .finally(() => {
          inflight = null;
        });
    }
    try {
      return await inflight;
    } catch {
      return null;
    }
  }

  return { registry: registryRef, ensureRegistry };
}
