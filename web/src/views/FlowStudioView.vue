<template>
  <div class="studio">
    <header class="top">
      <div class="brand">
        <span class="logo">◇</span>
        <div>
          <div class="title">Flow Studio</div>
          <div class="subtitle">
            流程拓扑 · 策略 · 节点调试
            <span v-if="store.serverFlowsDir" class="dir-hint" :title="store.serverFlowsDir"> · YAML 目录已连接</span>
          </div>
        </div>
      </div>
      <div class="actions">
        <div class="grp" title="对应服务端 flows 目录下的流程版本">
          <!-- Flow selector -->
          <select v-model="selectedId" class="sel" @change="onSelectFlow">
            <option value="" disabled>选择流程…</option>
            <option v-for="f in store.flowList" :key="(f as any).id" :value="(f as any).id">
              {{ (f as any).name }} ({{ (f as any).id }})
            </option>
          </select>

          <!-- Version selector -->
          <select v-if="store.activeFlowId" v-model="selectedVersion" class="sel-ver" @change="onSelectVersion">
            <option value="draft" :disabled="!hasDraft">草稿{{ hasDraft ? "" : "（无）" }}</option>
            <option v-for="v in versionList" :key="v.version" :value="String(v.version)">
              V{{ v.version }}{{ v.version === latestVersion ? " (最新)" : "" }}
            </option>
          </select>

          <!-- Version badge -->
          <span v-if="currentVersionBadge" class="ver-badge">{{ currentVersionBadge }}</span>

          <button type="button" class="btn ghost" title="重新扫描 flows 目录" @click="refresh">刷新</button>

          <!-- Save draft -->
          <button
            type="button"
            class="btn ghost"
            :disabled="!store.activeFlowId || saving"
            title="保存为草稿（不创建新版本）"
            @click="saveDraft"
          >
            {{ saving === "draft" ? "保存中…" : "保存草稿" }}
          </button>

          <!-- Commit new version -->
          <button
            type="button"
            class="btn primary"
            :disabled="!store.activeFlowId || saving !== false"
            title="将当前草稿提交为新版本（V+1）"
            @click="saveNewVersion"
          >
            {{ saving === "version" ? "提交中…" : `提交 V${latestVersion + 1}` }}
          </button>

          <button
            type="button"
            class="btn accent"
            :disabled="!store.activeFlowId"
            title="执行当前流程（需先保存）"
            @click="toggleRun"
          >
            ▶ 运行流程
          </button>
          <button type="button" class="btn ghost" @click="newFlow">新建流程</button>
        </div>
        <div class="grp">
          <button type="button" class="btn ghost" @click="download">导出 JSON</button>
          <label class="btn ghost">
            导入
            <input hidden type="file" accept="application/json" @change="onImport" />
          </label>
        </div>
      </div>
    </header>

    <!-- Save message -->
    <div v-if="saveMsg" class="save-msg" :class="saveMsg.type">{{ saveMsg.text }}</div>

    <FlowRunPanel
      :flow-id="store.activeFlowId"
      :visible="runVisible"
      :initial-context="store.doc.initial_context"
      @close="runVisible = false"
    />
    <p v-if="store.apiError" class="api-err">API: {{ store.apiError }}（请先执行 <code>flow-api</code> 或 <code>python -m flow_engine.http_api</code>）</p>

    <div class="body">
      <aside class="left">
        <LeftPanel />
      </aside>
      <main class="right">
        <RightPanel />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useFlowStudioStore } from "@/stores/flowStudio";
import type { FlowDocument } from "@/types/flow";
import LeftPanel from "@/components/LeftPanel.vue";
import RightPanel from "@/components/RightPanel.vue";
import FlowRunPanel from "@/components/FlowRunPanel.vue";
import { fetchVersionList, commitVersion, saveDraft as apiSaveDraft, fetchVersion, fetchDraft } from "@/api/publish";
import type { FlowVersionMeta } from "@/api/publish";

const store = useFlowStudioStore();
const selectedId = ref("");
const selectedVersion = ref("draft");
const saving = ref<false | "draft" | "version">(false);
const runVisible = ref(false);

const versionList = ref<FlowVersionMeta[]>([]);
const latestVersion = ref(0);
const hasDraft = ref(false);

type SaveMsg = { type: "ok" | "err"; text: string };
const saveMsg = ref<SaveMsg | null>(null);
let saveMsgTimer: ReturnType<typeof setTimeout> | null = null;

function showMsg(type: "ok" | "err", text: string) {
  saveMsg.value = { type, text };
  if (saveMsgTimer) clearTimeout(saveMsgTimer);
  saveMsgTimer = setTimeout(() => (saveMsg.value = null), 3000);
}

function flushActiveInput() {
  const el = document.activeElement;
  if (el instanceof HTMLElement) el.blur();
}

const currentVersionBadge = computed(() => {
  if (!store.activeFlowId) return "";
  if (selectedVersion.value === "draft") return hasDraft.value ? "草稿" : "";
  return `V${selectedVersion.value}`;
});

function toggleRun() {
  runVisible.value = !runVisible.value;
}

watch(
  () => store.activeFlowId,
  (v) => {
    selectedId.value = v ?? "";
  },
  { immediate: true },
);

onMounted(async () => {
  await store.refreshFlowList();
  try {
    if (store.flowList.some((f) => (f as any).id === "demo_flow")) {
      await loadFlowWithVersions("demo_flow");
    } else if (store.flowList.length > 0) {
      await loadFlowWithVersions((store.flowList[0] as any).id);
    }
  } catch {
    /* offline – use built-in sample */
  }
});

async function refresh() {
  store.clearAllNodeDrafts();
  await store.refreshFlowList();
  const fid = store.activeFlowId;
  if (!fid) return;
  await refreshVersionList(fid);
  await onSelectVersion();
}

async function refreshVersionList(flowId: string) {
  try {
    const vl = await fetchVersionList(flowId);
    versionList.value = vl.versions;
    latestVersion.value = vl.latest_version;
    hasDraft.value = vl.has_draft;
  } catch {
    versionList.value = [];
    latestVersion.value = 0;
    hasDraft.value = false;
  }
}

async function loadFlowWithVersions(flowId: string) {
  await store.loadFlowFromServer(flowId);
  await refreshVersionList(flowId);
  // Show draft if it exists, otherwise latest version
  selectedVersion.value = hasDraft.value ? "draft" : String(latestVersion.value || "draft");
}

async function onSelectFlow() {
  if (!selectedId.value) return;
  try {
    await loadFlowWithVersions(selectedId.value);
  } catch (e) {
    alert(e instanceof Error ? e.message : String(e));
  }
}

async function onSelectVersion() {
  const fid = store.activeFlowId;
  if (!fid) return;
  try {
    store.clearAllNodeDrafts();
    let data: Record<string, unknown>;
    if (selectedVersion.value === "draft") {
      data = await fetchDraft(fid);
    } else {
      data = await fetchVersion(fid, Number(selectedVersion.value));
    }
    store.loadDocument(data as unknown as FlowDocument, fid);
  } catch (e) {
    showMsg("err", e instanceof Error ? e.message : String(e));
  }
}

async function saveDraft() {
  const fid = store.activeFlowId;
  if (!fid) return;
  flushActiveInput();
  store.flushNodeDraftsToDocument();
  saving.value = "draft";
  try {
    await apiSaveDraft(fid, store.doc as unknown as Record<string, unknown>);
    await refreshVersionList(fid);
    selectedVersion.value = "draft";
    await onSelectVersion();
    showMsg("ok", "草稿已保存");
  } catch (e) {
    showMsg("err", e instanceof Error ? e.message : String(e));
  } finally {
    saving.value = false;
  }
}

async function saveNewVersion() {
  const fid = store.activeFlowId;
  if (!fid) return;
  flushActiveInput();
  store.flushNodeDraftsToDocument();
  saving.value = "version";
  try {
    // Save current doc to draft first, then commit
    await apiSaveDraft(fid, store.doc as unknown as Record<string, unknown>);
    const res = await commitVersion(fid);
    await refreshVersionList(fid);
    selectedVersion.value = String(res.version);
    await onSelectVersion();
    showMsg("ok", `版本 V${res.version} 已提交`);
  } catch (e) {
    showMsg("err", e instanceof Error ? e.message : String(e));
  } finally {
    saving.value = false;
  }
}

async function newFlow() {
  const id = prompt("新流程 id（字母、数字、下划线、短横线）", `flow_${Date.now()}`);
  if (!id?.trim()) return;
  try {
    await store.createFlowOnServer(id.trim());
    await refreshVersionList(id.trim());
    selectedVersion.value = "draft";
  } catch (e) {
    alert(e instanceof Error ? e.message : String(e));
  }
}

function download() {
  const blob = new Blob([store.exportJson()], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${store.doc.name || "flow"}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function onImport(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      store.importJson(String(reader.result));
      selectedVersion.value = "draft";
    } catch {
      alert("JSON 解析失败");
    }
  };
  reader.readAsText(file);
  input.value = "";
}
</script>

<style scoped>
.studio {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 640px;
}

.top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 86%, transparent);
  backdrop-filter: blur(10px);
  flex-wrap: wrap;
}

.brand {
  display: flex;
  gap: 10px;
  align-items: center;
}

.logo {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: linear-gradient(145deg, var(--accent-soft), #fff);
  border: 1px solid var(--border);
  color: var(--accent);
  font-size: 16px;
}

.title {
  font-weight: 700;
  letter-spacing: -0.02em;
  font-size: 15px;
}

.subtitle {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}

.dir-hint {
  color: var(--success);
  font-size: 11px;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  justify-content: flex-end;
}

.grp {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.sel {
  min-width: 200px;
  max-width: 260px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 12px;
  background: #fff;
}

.sel-ver {
  min-width: 110px;
  max-width: 160px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 12px;
  background: #fff;
}

.ver-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  background: var(--accent-soft);
  color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 25%, transparent);
}

.btn {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 12px;
  cursor: pointer;
  box-shadow: var(--shadow);
  white-space: nowrap;
}

.btn.primary {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: var(--accent);
  color: #fff;
}

.btn.primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn.accent {
  border-color: color-mix(in srgb, #10b981 35%, transparent);
  background: #10b981;
  color: #fff;
}

.btn.accent:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn.accent:hover:not(:disabled) {
  background: #059669;
}

.btn.ghost:hover {
  border-color: var(--border-strong);
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.save-msg {
  padding: 5px 16px;
  font-size: 12px;
  border-bottom: 1px solid transparent;
}

.save-msg.ok {
  color: #065f46;
  background: color-mix(in srgb, #10b981 12%, transparent);
  border-color: color-mix(in srgb, #10b981 25%, transparent);
}

.save-msg.err {
  color: #b45309;
  background: color-mix(in srgb, #fbbf24 12%, transparent);
  border-color: color-mix(in srgb, #f59e0b 25%, transparent);
}

.api-err {
  margin: 0;
  padding: 6px 16px;
  font-size: 11px;
  color: #b45309;
  background: color-mix(in srgb, #fbbf24 12%, transparent);
  border-bottom: 1px solid color-mix(in srgb, #f59e0b 25%, transparent);
}

.api-err code {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 4px;
  background: #fff8;
}

.body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 0;
}

.left {
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  min-width: 280px;
}

.right {
  min-width: 0;
  background: linear-gradient(180deg, #fbfcff 0%, #f6f8fc 100%);
}

@media (max-width: 960px) {
  .body {
    grid-template-columns: 1fr;
  }
  .left {
    border-right: none;
    border-bottom: 1px solid var(--border);
    max-height: 42vh;
  }
}
</style>
