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
          <select class="sel" :value="flowSelectBoundValue" @change="onFlowSelectChange">
            <option value="" disabled>选择流程…</option>
            <option v-if="store.pendingNewFlowId" :value="UNSAVED_SENTINEL">新流程（未保存）</option>
            <option
              v-for="f in store.flowList"
              :key="(f as any).id"
              :value="(f as any).id"
            >
              {{ flowListItemLabel(f as { id: string; display_name?: string }) }}
            </option>
          </select>

          <!-- Version selector -->
          <select v-if="store.activeFlowId" v-model="selectedVersion" class="sel-ver" @change="onSelectVersion">
            <option value="draft" :disabled="!hasDraft">草稿{{ hasDraft ? "" : "（无）" }}</option>
            <option v-for="(v, i) in versionList" :key="`${v.version}-${i}`" :value="String(v.version)">
              V{{ v.version }}{{ v.version === latestVersion ? " · 最新" : "" }}
            </option>
          </select>

          <span v-if="store.activeFlowId && !store.pendingNewFlowId" class="hint-text">先保存草稿，再保存为新版本</span>

          <!-- Save draft -->
          <button
            type="button"
            class="btn ghost"
            :disabled="(!store.activeFlowId && !store.pendingNewFlowId) || !!saving"
            title="保存为草稿（不创建新版本）；未写库的新流程首次点击将创建并写入草稿"
            @click="saveDraft"
          >
            {{ saving === "draft" ? "保存中…" : "保存草稿" }}
          </button>

          <!-- Commit new version -->
          <button
            type="button"
            class="btn primary"
            :disabled="!store.activeFlowId || store.pendingNewFlowId !== null || saving !== false"
            title="将当前草稿保存为新版本（V+1）"
            @click="saveNewVersion"
          >
            {{ saving === "version" ? "保存中…" : "保存为新版本" }}
          </button>

          <button
            type="button"
            class="btn ghost"
            :disabled="!store.activeFlowId || store.pendingNewFlowId !== null"
            :title="
              !store.activeFlowId || store.pendingNewFlowId
                ? '请先保存流程后再试运行'
                : '临时仿真执行当前流程：固定调试模式，副作用默认抑制'
            "
            @click="openTrialRun"
          >
            流程试运行
          </button>
        </div>
        <div class="grp menu-wrap" ref="moreMenuRef">
          <button type="button" class="btn ghost" :aria-expanded="moreMenuOpen" aria-haspopup="menu" @click="toggleMoreMenu">
            更多{{ moreMenuOpen ? " ▴" : " ▾" }}
          </button>
          <div v-if="moreMenuOpen" class="menu-panel">
            <div class="menu-group">
              <button type="button" class="menu-item" @click="onNewFlowFromMenu">新建流程</button>
            </div>
            <div class="menu-group">
              <label class="menu-item">
                导入 YAML
                <input
                  hidden
                  type="file"
                  accept=".yaml,.yml,text/yaml,application/yaml,application/x-yaml,application/json"
                  @change="onImport"
                />
              </label>
              <button type="button" class="menu-item" @click="onDownloadFromMenu">导出 YAML</button>
            </div>
            <div class="menu-group">
              <button
                type="button"
                class="menu-item danger"
                :disabled="!store.activeFlowId || store.pendingNewFlowId !== null || !flowDeleteMeta.deletable"
                :title="deleteFlowMenuTitle"
                @click="onDeleteFlowFromMenu"
              >
                删除流程…
              </button>
            </div>
          </div>
        </div>
      </div>
    </header>

    <!-- Save message -->
    <div v-if="saveMsg" class="save-msg" :class="saveMsg.type">{{ saveMsg.text }}</div>
    <div v-if="versionConfirmOpen" class="confirm-mask" @click.self="closeVersionConfirm">
      <div class="confirm-dialog" role="dialog" aria-modal="true" aria-label="确认保存新版本">
        <div class="confirm-title">确认保存为新版本</div>
        <p class="confirm-text">确认将当前草稿保存为 V{{ pendingVersion }} 吗？</p>
        <div class="confirm-actions">
          <button type="button" class="btn ghost" @click="closeVersionConfirm">取消</button>
          <button type="button" class="btn primary" @click="confirmSaveNewVersion">确认保存</button>
        </div>
      </div>
    </div>

    <div v-if="discardConfirmOpen" class="confirm-mask" @click.self="resolveDiscardConfirm(false)">
      <div class="confirm-dialog" role="dialog" aria-modal="true" aria-label="放弃未保存的新流程">
        <div class="confirm-title">放弃未保存的更改？</div>
        <p class="confirm-text">{{ discardConfirmText }}</p>
        <div class="confirm-actions">
          <button type="button" class="btn ghost" @click="resolveDiscardConfirm(false)">取消</button>
          <button type="button" class="btn danger" @click="resolveDiscardConfirm(true)">放弃</button>
        </div>
      </div>
    </div>

    <div v-if="deleteFlowConfirmOpen" class="confirm-mask" @click.self="closeDeleteFlowConfirm">
      <div class="confirm-dialog" role="dialog" aria-modal="true" aria-label="确认删除流程">
        <div class="confirm-title">删除流程</div>
        <p class="confirm-text">
          将永久删除当前流程及其草稿与版本文件，不可恢复。确定删除「{{ flowDeleteDisplayName }}」吗？
        </p>
        <div class="confirm-actions">
          <button type="button" class="btn ghost" :disabled="deletingFlow" @click="closeDeleteFlowConfirm">取消</button>
          <button type="button" class="btn danger" :disabled="deletingFlow" @click="confirmDeleteFlow">
            {{ deletingFlow ? "删除中…" : "确认删除" }}
          </button>
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
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useFlowStudioStore } from "@/stores/flowStudio";
import { flowListItemLabel, type FlowDocument } from "@/types/flow";
import LeftPanel from "@/components/LeftPanel.vue";
import RightPanel from "@/components/RightPanel.vue";
import FlowRunPanel from "@/components/FlowRunPanel.vue";
import { fetchFlowDeletable, type FlowDeletableResponse } from "@/api/flows";
import {
  commitVersion,
  fetchDraft,
  fetchVersion,
  fetchVersionList,
  saveDraft as putFlowDraft,
  sortFlowVersionsDesc,
  type FlowVersionMeta,
} from "@/api/flowVersions";

const LAST_FLOW_STORAGE_KEY = "flowEngine:flowStudio:lastFlowId";
const UNSAVED_SENTINEL = "__unsaved_new__";

const store = useFlowStudioStore();
const selectedId = ref("");
const selectedVersion = ref("draft");
const saving = ref<false | "draft" | "version">(false);
const runVisible = ref(false);
const moreMenuOpen = ref(false);
const moreMenuRef = ref<HTMLElement | null>(null);
const versionConfirmOpen = ref(false);
const pendingVersion = ref(0);

const discardConfirmOpen = ref(false);
const discardConfirmText = ref("");
let discardConfirmResolver: ((ok: boolean) => void) | null = null;

const deleteFlowConfirmOpen = ref(false);
const deletingFlow = ref(false);
const flowDeleteMeta = ref<FlowDeletableResponse>({ deletable: false, reasons: [] });

const versionList = ref<FlowVersionMeta[]>([]);
const latestVersion = ref(0);
const hasDraft = ref(false);

const flowSelectBoundValue = computed(() => {
  if (store.pendingNewFlowId) return UNSAVED_SENTINEL;
  return selectedId.value;
});

const flowDeleteDisplayName = computed(() => (store.doc.display_name ?? "").trim() || "该流程");

const deleteFlowMenuTitle = computed(() => {
  if (!store.activeFlowId || store.pendingNewFlowId) return "请先保存流程";
  if (!flowDeleteMeta.value.deletable && flowDeleteMeta.value.reasons.length > 0) {
    return flowDeleteMeta.value.reasons.join("；");
  }
  return "删除流程文件（不可恢复）；须无部署运行与测试运行记录";
});

type SaveMsg = { type: "ok" | "err"; text: string };
const saveMsg = ref<SaveMsg | null>(null);
let saveMsgTimer: ReturnType<typeof setTimeout> | null = null;

function persistLastFlowId(id: string) {
  try {
    localStorage.setItem(LAST_FLOW_STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
}

function showMsg(type: "ok" | "err", text: string) {
  saveMsg.value = { type, text };
  if (saveMsgTimer) clearTimeout(saveMsgTimer);
  saveMsgTimer = setTimeout(() => (saveMsg.value = null), 3000);
}

function flowNameOk(): boolean {
  if (!(store.doc.display_name ?? "").trim()) {
    showMsg("err", "请填写流程名称");
    store.select({ kind: "flow" });
    return false;
  }
  return true;
}

async function refreshFlowDeletable() {
  const fid = store.activeFlowId;
  if (!fid || store.pendingNewFlowId) {
    flowDeleteMeta.value = { deletable: false, reasons: [] };
    return;
  }
  try {
    flowDeleteMeta.value = await fetchFlowDeletable(fid);
  } catch {
    flowDeleteMeta.value = { deletable: false, reasons: ["无法查询是否可删除"] };
  }
}

function closeDeleteFlowConfirm() {
  deleteFlowConfirmOpen.value = false;
}

function onDeleteFlowFromMenu() {
  closeMoreMenu();
  if (!store.activeFlowId || store.pendingNewFlowId) return;
  if (!flowDeleteMeta.value.deletable) return;
  deleteFlowConfirmOpen.value = true;
}

async function confirmDeleteFlow() {
  const fid = store.activeFlowId;
  if (!fid) return;
  deletingFlow.value = true;
  try {
    await store.deleteFlowOnServer(fid);
    closeDeleteFlowConfirm();
    showMsg("ok", "流程已删除");
    try {
      localStorage.removeItem(LAST_FLOW_STORAGE_KEY);
    } catch {
      /* ignore */
    }
    await store.refreshFlowList();
    if (store.flowList.length > 0) {
      const next = (store.flowList[0] as { id: string }).id;
      await loadFlowWithVersions(next);
    } else {
      store.beginLocalNewFlow();
    }
  } catch (e) {
    showMsg("err", e instanceof Error ? e.message : String(e));
  } finally {
    deletingFlow.value = false;
  }
}

function flushActiveInput() {
  const el = document.activeElement;
  if (el instanceof HTMLElement) el.blur();
}

function toggleRun() {
  runVisible.value = !runVisible.value;
}

function openTrialRun() {
  if (!store.activeFlowId || store.pendingNewFlowId) return;
  toggleRun();
}

function toggleMoreMenu() {
  moreMenuOpen.value = !moreMenuOpen.value;
  if (moreMenuOpen.value) void refreshFlowDeletable();
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

function openDiscardConfirm(message: string): Promise<boolean> {
  discardConfirmText.value = message;
  discardConfirmOpen.value = true;
  return new Promise((resolve) => {
    discardConfirmResolver = resolve;
  });
}

function resolveDiscardConfirm(ok: boolean) {
  discardConfirmOpen.value = false;
  discardConfirmResolver?.(ok);
  discardConfirmResolver = null;
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
  closeDeleteFlowConfirm();
  if (discardConfirmOpen.value) resolveDiscardConfirm(false);
}

watch(
  () => [store.activeFlowId, store.pendingNewFlowId] as const,
  ([aid, pend]) => {
    if (pend) return;
    selectedId.value = aid ?? "";
    void refreshFlowDeletable();
  },
  { immediate: true },
);

watch(
  () => ({
    id: store.activeFlowId,
    pending: store.pendingNewFlowId,
    ver: selectedVersion.value,
  }),
  ({ id, pending, ver }) => {
    if (id) {
      store.setStudioPickerVersionChannel(ver);
      return;
    }
    if (pending) {
      store.setStudioPickerVersionChannel("draft");
      return;
    }
    store.clearStudioPickerVersionChannel();
  },
  { immediate: true },
);

onMounted(async () => {
  window.addEventListener("mousedown", onWindowMouseDown);
  window.addEventListener("keydown", onWindowKeydown);
  await store.refreshFlowList();
  try {
    let last: string | null = null;
    try {
      last = localStorage.getItem(LAST_FLOW_STORAGE_KEY);
    } catch {
      last = null;
    }
    if (last && store.flowList.some((f) => (f as { id: string }).id === last)) {
      await loadFlowWithVersions(last);
    } else if (store.flowList.some((f) => (f as { id: string }).id === "demo_flow")) {
      await loadFlowWithVersions("demo_flow");
    } else if (store.flowList.length > 0) {
      await loadFlowWithVersions((store.flowList[0] as { id: string }).id);
    }
  } catch {
    /* offline – use built-in sample */
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("mousedown", onWindowMouseDown);
  window.removeEventListener("keydown", onWindowKeydown);
});

function normalizeVersionListItem(raw: unknown): FlowVersionMeta | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const vn = o.version ?? o.ver_no;
  const ver = typeof vn === "number" && Number.isFinite(vn) ? vn : Number(vn);
  if (!Number.isFinite(ver) || ver < 1) return null;
  const ca = o.created_at;
  const createdAt =
    typeof ca === "number" && Number.isFinite(ca) ? ca : typeof ca === "string" ? Number(ca) || 0 : 0;
  const desc = o.description;
  return {
    version: ver,
    created_at: createdAt,
    description: desc == null || desc === "" ? null : String(desc),
    display_name: typeof o.display_name === "string" ? o.display_name : String(o.display_name ?? ""),
  };
}

async function refreshVersionList(flowId: string) {
  try {
    const vl = await fetchVersionList(flowId);
    const raw = vl.versions;
    const arr = Array.isArray(raw) ? raw : [];
    versionList.value = sortFlowVersionsDesc(
      arr.map(normalizeVersionListItem).filter((x): x is FlowVersionMeta => x != null),
    );
    latestVersion.value =
      typeof vl.latest_version === "number" && Number.isFinite(vl.latest_version)
        ? vl.latest_version
        : Number(vl.latest_version) || 0;
    hasDraft.value = Boolean(vl.has_draft);
  } catch (e) {
    versionList.value = [];
    latestVersion.value = 0;
    hasDraft.value = false;
    showMsg("err", e instanceof Error ? e.message : String(e));
  }
}

async function loadFlowWithVersions(flowId: string) {
  await store.loadFlowFromServer(flowId);
  await refreshVersionList(flowId);
  persistLastFlowId(flowId);
  // Show draft if it exists, otherwise latest version
  if (hasDraft.value) {
    selectedVersion.value = "draft";
  } else if (latestVersion.value > 0) {
    selectedVersion.value = String(latestVersion.value);
  } else {
    selectedVersion.value = "draft";
  }
}

async function onFlowSelectChange(ev: Event) {
  const el = ev.target as HTMLSelectElement;
  const next = el.value;
  if (!next || next === UNSAVED_SENTINEL) return;
  if (store.pendingNewFlowId) {
    const ok = await openDiscardConfirm("当前新流程尚未保存，确定放弃并切换流程吗？");
    if (!ok) {
      el.value = UNSAVED_SENTINEL;
      return;
    }
    store.abandonUnpersistedNewFlow();
  }
  selectedId.value = next;
  try {
    await loadFlowWithVersions(next);
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
  const fid = store.activeFlowId ?? store.pendingNewFlowId;
  if (!fid) return;
  if (!flowNameOk()) return;
  flushActiveInput();
  store.flushNodeDraftsToDocument();
  saving.value = "draft";
  const wasUnpersistedNew = !!store.pendingNewFlowId;
  try {
    await putFlowDraft(fid, store.doc as unknown as Record<string, unknown>);
    await store.loadFlowFromServer(fid);
    await refreshVersionList(fid);
    selectedVersion.value = "draft";
    await onSelectVersion();
    persistLastFlowId(fid);
    showMsg("ok", wasUnpersistedNew ? "流程已创建，草稿已保存" : "草稿已保存");
  } catch (e) {
    showMsg("err", e instanceof Error ? e.message : String(e));
  } finally {
    saving.value = false;
  }
}

async function saveNewVersion() {
  const fid = store.activeFlowId;
  if (!fid) return;
  if (!flowNameOk()) return;
  openVersionConfirm();
}

async function confirmSaveNewVersion() {
  const fid = store.activeFlowId;
  if (!fid) return;
  if (!flowNameOk()) return;
  closeVersionConfirm();
  flushActiveInput();
  store.flushNodeDraftsToDocument();
  saving.value = "version";
  try {
    // Save current doc to draft first, then commit
    await putFlowDraft(fid, store.doc as unknown as Record<string, unknown>);
    const res = await commitVersion(fid);
    await refreshVersionList(fid);
    selectedVersion.value = String(res.version);
    await onSelectVersion();
    persistLastFlowId(fid);
    showMsg("ok", `已保存为新版本 V${res.version}`);
  } catch (e) {
    showMsg("err", e instanceof Error ? e.message : String(e));
  } finally {
    saving.value = false;
  }
}

async function onNewFlowFromMenu() {
  closeMoreMenu();
  store.beginLocalNewFlow();
  selectedVersion.value = "draft";
  versionList.value = [];
  latestVersion.value = 0;
  hasDraft.value = false;
}

function onDownloadFromMenu() {
  closeMoreMenu();
  download();
}

function download() {
  const blob = new Blob([store.exportYaml()], { type: "text/yaml;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  const base = (store.doc.display_name ?? "").trim() || "flow";
  a.download = `${base}.yaml`;
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
      store.importYaml(String(reader.result));
      selectedVersion.value = "draft";
    } catch (e) {
      alert(e instanceof Error ? e.message : "YAML 解析失败");
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
  /* 不透明背景：避免 backdrop-filter 在部分浏览器下裁剪原生 <select> 下拉层，导致只能看到「草稿」一项 */
  background: color-mix(in srgb, var(--surface) 96%, #f1f5f9);
  flex-wrap: wrap;
  overflow: visible;
  position: relative;
  z-index: 5;
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
  overflow: visible;
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
  min-width: 140px;
  max-width: 220px;
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

.btn.danger {
  border-color: color-mix(in srgb, #ef4444 45%, transparent);
  color: #b91c1c;
  background: #fff;
}

.btn.danger:hover {
  background: #fef2f2;
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
  display: flex;
  flex-direction: column;
  gap: 0;
  z-index: 5;
}

.menu-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.menu-group + .menu-group {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--border);
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

.menu-item.danger {
  color: #b91c1c;
}

.menu-item.danger:disabled {
  color: var(--muted);
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
