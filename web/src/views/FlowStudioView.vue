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
            <option
              v-for="f in store.flowList"
              :key="(f as any).id"
              :value="(f as any).id"
              :title="(f as any).id"
            >
              {{ flowOptionLabel(f) }}
            </option>
          </select>

          <!-- Version selector -->
          <select v-if="store.activeFlowId" v-model="selectedVersion" class="sel-ver" @change="onSelectVersion">
            <option value="draft" :disabled="!hasDraft">草稿{{ hasDraft ? "（可编辑）" : "（无）" }}</option>
            <option v-for="v in versionList" :key="v.version" :value="String(v.version)">
              V{{ v.version }}{{ v.version === latestVersion ? "（已发布，最新）" : "（已发布）" }}
            </option>
          </select>

          <span v-if="store.activeFlowId" class="hint-text">先保存草稿，再提交新版本</span>

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
            {{ saving === "version" ? "提交中…" : `提交为 V${latestVersion + 1}` }}
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
        </div>
        <div class="grp menu-wrap" ref="moreMenuRef">
          <button type="button" class="btn ghost" :aria-expanded="moreMenuOpen" aria-haspopup="menu" @click="toggleMoreMenu">
            更多{{ moreMenuOpen ? " ▴" : " ▾" }}
          </button>
          <div v-if="moreMenuOpen" class="menu-panel">
            <button type="button" class="menu-item" @click="onNewFlowFromMenu">新建流程</button>
            <label class="menu-item">
              导入 JSON
              <input hidden type="file" accept="application/json" @change="onImport" />
            </label>
            <button type="button" class="menu-item" @click="onDownloadFromMenu">导出 JSON</button>
          </div>
        </div>
      </div>
    </header>

    <!-- Save message -->
    <div v-if="saveMsg" class="save-msg" :class="saveMsg.type">{{ saveMsg.text }}</div>
    <div v-if="versionConfirmOpen" class="confirm-mask" @click.self="closeVersionConfirm">
      <div class="confirm-dialog" role="dialog" aria-modal="true" aria-label="确认提交版本">
        <div class="confirm-title">确认提交新版本</div>
        <p class="confirm-text">确认将当前草稿提交为 V{{ pendingVersion }} 吗？</p>
        <div class="confirm-actions">
          <button type="button" class="btn ghost" @click="closeVersionConfirm">取消</button>
          <button type="button" class="btn primary" @click="confirmSaveNewVersion">确认提交</button>
        </div>
      </div>
    </div>

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
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useFlowStudioStore } from "@/stores/flowStudio";
import type { FlowDocument } from "@/types/flow";
import LeftPanel from "@/components/LeftPanel.vue";
import RightPanel from "@/components/RightPanel.vue";
import FlowRunPanel from "@/components/FlowRunPanel.vue";
import { fetchVersionList, commitVersion, saveDraft as apiSaveDraft, fetchVersion, fetchDraft } from "@/api/flowVersions";
import type { FlowVersionMeta } from "@/api/flowVersions";

const store = useFlowStudioStore();
const selectedId = ref("");
const selectedVersion = ref("draft");
const saving = ref<false | "draft" | "version">(false);
const runVisible = ref(false);
const moreMenuOpen = ref(false);
const moreMenuRef = ref<HTMLElement | null>(null);
const versionConfirmOpen = ref(false);
const pendingVersion = ref(0);

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

function toggleRun() {
  runVisible.value = !runVisible.value;
}

function toggleMoreMenu() {
  moreMenuOpen.value = !moreMenuOpen.value;
}

function closeMoreMenu() {
  moreMenuOpen.value = false;
}

function openVersionConfirm() {
  pendingVersion.value = latestVersion.value + 1;
  versionConfirmOpen.value = true;
}

function closeVersionConfirm() {
  versionConfirmOpen.value = false;
}

function onWindowMouseDown(ev: MouseEvent) {
  if (!moreMenuOpen.value) return;
  const el = moreMenuRef.value;
  if (!el) return;
  const target = ev.target;
  if (target instanceof Node && !el.contains(target)) closeMoreMenu();
}

function onWindowKeydown(ev: KeyboardEvent) {
  if (ev.key !== "Escape") return;
  closeMoreMenu();
  closeVersionConfirm();
}

watch(
  () => store.activeFlowId,
  (v) => {
    selectedId.value = v ?? "";
  },
  { immediate: true },
);

onMounted(async () => {
  window.addEventListener("mousedown", onWindowMouseDown);
  window.addEventListener("keydown", onWindowKeydown);
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

onBeforeUnmount(() => {
  window.removeEventListener("mousedown", onWindowMouseDown);
  window.removeEventListener("keydown", onWindowKeydown);
});

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
  if (hasDraft.value) {
    selectedVersion.value = "draft";
  } else if (latestVersion.value > 0) {
    selectedVersion.value = String(latestVersion.value);
  } else {
    selectedVersion.value = "draft";
  }
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
  openVersionConfirm();
}

async function confirmSaveNewVersion() {
  const fid = store.activeFlowId;
  if (!fid) return;
  closeVersionConfirm();
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

async function onNewFlowFromMenu() {
  closeMoreMenu();
  await newFlow();
}

function onDownloadFromMenu() {
  closeMoreMenu();
  download();
}

function flowOptionLabel(f: unknown): string {
  const item = f as { id: string; display_name?: string };
  const dn = (item.display_name ?? "").trim();
  // 当显示名与 id 相同（或缺失）时只显示一个值；否则 "显示名 (id)"。
  if (!dn || dn === item.id) return item.id;
  return `${dn} (${item.id})`;
}

function download() {
  const blob = new Blob([store.exportJson()], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  const base = (store.doc.display_name ?? "").trim() || store.activeFlowId || "flow";
  a.download = `${base}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function onImport(ev: Event) {
  closeMoreMenu();
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
  min-height: 0;
  overflow: hidden;
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

.hint-text {
  font-size: 11px;
  color: var(--muted);
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

.menu-wrap {
  position: relative;
}

.menu-panel {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  min-width: 140px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow);
  padding: 6px;
  display: grid;
  gap: 4px;
  z-index: 5;
}

.menu-item {
  border: 1px solid transparent;
  background: transparent;
  color: var(--text);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  white-space: nowrap;
  display: block;
}

.menu-item:hover {
  border-color: var(--border);
  background: color-mix(in srgb, var(--accent-soft) 35%, transparent);
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

.confirm-mask {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, #0f172a 32%, transparent);
  z-index: 40;
  display: grid;
  place-items: center;
  padding: 16px;
}

.confirm-dialog {
  width: min(460px, calc(100vw - 32px));
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow);
  padding: 16px;
}

.confirm-title {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 8px;
}

.confirm-text {
  margin: 0;
  font-size: 13px;
  color: var(--text);
}

.confirm-actions {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
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
  grid-template-rows: minmax(0, 1fr);
  gap: 0;
  overflow: hidden;
}

.left {
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  min-width: 280px;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.left > * {
  flex: 1;
  min-height: 0;
}

.right {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #fbfcff 0%, #f6f8fc 100%);
}

.right > * {
  flex: 1;
  min-height: 0;
}

@media (max-width: 960px) {
  .body {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(0, 1fr);
  }
  .left {
    border-right: none;
    border-bottom: 1px solid var(--border);
    max-height: 42vh;
  }
}
</style>
