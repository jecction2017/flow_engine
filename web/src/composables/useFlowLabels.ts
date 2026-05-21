import { ref } from "vue";
import { fetchFlowList, type FlowListItem } from "@/api/flows";
import { flowCodeDisplayLabel, flowListItemLabel } from "@/types/flow";

const flowOptions = ref<FlowListItem[]>([]);
let inflight: Promise<void> | null = null;

/** Shared flow list + display_name labels for Operations / Test centers. */
export function useFlowLabels() {
  async function ensureFlowList(): Promise<void> {
    if (flowOptions.value.length > 0) return;
    if (!inflight) {
      inflight = fetchFlowList()
        .then((r) => {
          flowOptions.value = r.flows;
        })
        .finally(() => {
          inflight = null;
        });
    }
    await inflight;
  }

  function flowLabelById(flowId: string): string {
    return flowCodeDisplayLabel(flowId, flowOptions.value);
  }

  return {
    flowOptions,
    ensureFlowList,
    flowLabelById,
    flowListItemLabel,
  };
}
