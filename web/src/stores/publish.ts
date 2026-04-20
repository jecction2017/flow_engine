import { defineStore } from "pinia";
import { ref, computed } from "vue";
import {
  fetchPublishState,
  fetchVersionList,
  fetchInstances,
  publishVersion,
  stopPublish,
  commitVersion,
  saveDraft,
  openEventStream,
  type FlowPublishState,
  type FlowInstance,
  type FlowVersionMeta,
  type ChannelState,
} from "@/api/publish";

export type { FlowPublishState, FlowInstance, FlowVersionMeta, ChannelState };

export const usePublishStore = defineStore("publish", () => {
  const selectedFlowId = ref<string | null>(null);

  const publishState = ref<FlowPublishState | null>(null);
  const instances = ref<FlowInstance[]>([]);
  const versions = ref<FlowVersionMeta[]>([]);
  const latestVersion = ref<number>(0);
  const hasDraft = ref<boolean>(false);

  const loading = ref(false);
  const error = ref<string | null>(null);

  let _closeSse: (() => void) | null = null;

  // ---------------------------------------------------------------------------
  // SSE management
  // ---------------------------------------------------------------------------

  function _openSse(flowId: string) {
    _closeSse?.();
    _closeSse = openEventStream(flowId, (ev) => {
      if (ev.type === "snapshot") {
        if (ev.publish) publishState.value = ev.publish;
        if (ev.instances) instances.value = ev.instances;
      } else if (ev.type === "publish.state_changed" && ev.data) {
        publishState.value = ev.data as unknown as FlowPublishState;
      } else if (ev.type === "instance.registered" && ev.data) {
        const inst = ev.data as unknown as FlowInstance;
        const idx = instances.value.findIndex((i) => i.instance_id === inst.instance_id);
        if (idx >= 0) instances.value[idx] = inst;
        else instances.value = [...instances.value, inst];
      } else if (ev.type === "instance.stopped" && ev.data) {
        const id = (ev.data as { instance_id?: string }).instance_id;
        if (id) instances.value = instances.value.filter((i) => i.instance_id !== id);
      } else if (ev.type === "instance.heartbeat" && ev.data) {
        const hb = ev.data as { instance_id?: string; status?: string };
        if (hb.instance_id) {
          instances.value = instances.value.map((i) =>
            i.instance_id === hb.instance_id
              ? { ...i, last_heartbeat: Date.now() / 1000, status: (hb.status ?? i.status) as FlowInstance["status"] }
              : i,
          );
        }
      }
    });
  }

  function closeSse() {
    _closeSse?.();
    _closeSse = null;
  }

  // ---------------------------------------------------------------------------
  // Flow selection
  // ---------------------------------------------------------------------------

  async function selectFlow(flowId: string) {
    if (selectedFlowId.value === flowId) return;
    selectedFlowId.value = flowId;
    publishState.value = null;
    instances.value = [];
    versions.value = [];
    error.value = null;
    await refresh();
    _openSse(flowId);
  }

  function clearFlow() {
    closeSse();
    selectedFlowId.value = null;
    publishState.value = null;
    instances.value = [];
    versions.value = [];
  }

  // ---------------------------------------------------------------------------
  // Data refresh
  // ---------------------------------------------------------------------------

  async function refresh() {
    const fid = selectedFlowId.value;
    if (!fid) return;
    loading.value = true;
    error.value = null;
    try {
      const [ps, vl, inst] = await Promise.all([
        fetchPublishState(fid),
        fetchVersionList(fid),
        fetchInstances(fid),
      ]);
      publishState.value = ps;
      versions.value = vl.versions;
      latestVersion.value = vl.latest_version;
      hasDraft.value = vl.has_draft;
      instances.value = inst;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  }

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  async function publish(version: number, channel: "production" | "gray") {
    const fid = selectedFlowId.value;
    if (!fid) return;
    loading.value = true;
    error.value = null;
    try {
      await publishVersion(fid, version, channel);
      await refresh();
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function stop(channel: "production" | "gray") {
    const fid = selectedFlowId.value;
    if (!fid) return;
    loading.value = true;
    error.value = null;
    try {
      await stopPublish(fid, channel);
      await refresh();
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function doCommitVersion(opts: { description?: string } = {}) {
    const fid = selectedFlowId.value;
    if (!fid) return 0;
    loading.value = true;
    error.value = null;
    try {
      const res = await commitVersion(fid, opts);
      await refresh();
      return res.version;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function doSaveDraft(data: Record<string, unknown>) {
    const fid = selectedFlowId.value;
    if (!fid) return;
    loading.value = true;
    error.value = null;
    try {
      await saveDraft(fid, data);
      await refresh();
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  // ---------------------------------------------------------------------------
  // Computed
  // ---------------------------------------------------------------------------

  const runningInstances = computed(() => instances.value.filter((i) => i.status === "running"));

  return {
    selectedFlowId,
    publishState,
    instances,
    versions,
    latestVersion,
    hasDraft,
    loading,
    error,
    runningInstances,
    selectFlow,
    clearFlow,
    refresh,
    publish,
    stop,
    doCommitVersion,
    doSaveDraft,
    closeSse,
  };
});
