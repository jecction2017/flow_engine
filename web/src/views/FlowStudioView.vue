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
              {{ flowListItemLabel(f as any) }}
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
            class="btn trial-run"
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
              <button type="button" class="menu-item" @click="openImportWizardFromMenu">导入 YAML…</button>
              <button
                type="button"
                class="menu-item"
                :disabled="!canExportYaml || exportingYaml"
                :title="
                  exportingYaml
                    ? '正在从服务器拉取快照…'
                    : canExportYaml
                      ? '从服务器导出当前版本选择器中的草稿或已提交版本（不含编辑器内未保存的更改）'
                      : !store.activeFlowId || store.pendingNewFlowId
                        ? '仅已保存到服务器的流程可导出：请先保存草稿（新建流程首次保存后）或选择已有流程'
                        : '当前选择为草稿但服务器上尚无草稿，请切换到有内容的版本或先保存草稿'
                "
                @click="onDownloadFromMenu"
              >
                {{ exportingYaml ? "导出中…" : "导出 YAML" }}
              </button>
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

    <div v-if="importOpenGuardOpen" class="confirm-mask import-open-guard-mask" @click.self="cancelImportOpenGuard">
      <div class="confirm-dialog" role="dialog" aria-modal="true" aria-label="确认打开导入">
        <div class="confirm-title">打开导入</div>
        <p class="confirm-text">{{ importOpenGuardText }}</p>
        <div class="confirm-actions">
          <button type="button" class="btn ghost" @click="cancelImportOpenGuard">取消</button>
          <button type="button" class="btn primary" @click="confirmImportOpenGuard">确定</button>
        </div>
      </div>
    </div>

    <div
      v-if="importWizardOpen"
      class="confirm-mask import-wizard-mask"
      @click.self="onImportWizardBackdrop"
    >
      <div
        class="confirm-dialog import-wizard-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="import-wizard-title"
        @click.stop
      >
        <div class="import-wizard-head">
          <h2 id="import-wizard-title" class="import-wizard-title">导入流程</h2>
          <button
            v-if="importView !== 'working'"
            type="button"
            class="btn ghost import-wizard-close"
            aria-label="关闭导入"
            @click="closeImportWizard"
          >
            ×
          </button>
        </div>

        <!-- 选择文件 -->
        <div v-if="importView === 'form'" class="import-wizard-body">
          <p class="import-wizard-lead">
            选择本地 YAML 或 JSON 文件，点击「开始导入」后将在服务端校验流程定义。校验通过后需再点击「确认载入」才会写入编辑区（仍为未保存状态，请随后保存草稿）。
          </p>
          <div class="import-file-row">
            <input
              ref="importFileInputRef"
              type="file"
              class="import-file-input"
              accept=".yaml,.yml,.json,text/yaml,application/yaml,application/x-yaml,application/json"
              @change="onImportWizardFileChange"
            />
            <button type="button" class="btn ghost" @click="triggerImportFilePick">选择文件…</button>
            <span class="import-file-meta" :title="importSelectedFile?.name ?? ''">{{ importFileStatusLabel }}</span>
          </div>
          <p v-if="importFormError" class="import-inline-err">{{ importFormError }}</p>
          <div class="confirm-actions import-wizard-actions">
            <button type="button" class="btn ghost" @click="closeImportWizard">取消</button>
            <button type="button" class="btn primary" :disabled="!importSelectedFile" @click="onImportWizardStart">
              开始导入
            </button>
          </div>
        </div>

        <!-- 进行中 -->
        <div v-else-if="importView === 'working'" class="import-wizard-body import-working">
          <div class="import-spinner" aria-hidden="true" />
          <p class="import-progress-title">正在导入…</p>
          <ul class="import-step-list">
            <li v-for="(s, i) in importProgressSteps" :key="s.id" :class="importStepClass(i)">
              <span class="import-step-ix">{{ importStepMark(i) }}</span>
              {{ s.label }}
            </li>
          </ul>
          <p class="import-progress-hint">请稍候，完成前请勿关闭窗口。</p>
        </div>

        <!-- 成功 -->
        <div v-else-if="importView === 'success'" class="import-wizard-body">
          <div class="import-result-banner import-result-ok">
            <span class="import-result-icon" aria-hidden="true">✓</span>
            <div>
              <div class="import-result-title">校验通过</div>
              <p class="import-result-sub">流程定义已通过服务端解析与编译检查，尚未载入编辑器。</p>
            </div>
          </div>
          <dl class="import-result-dl">
            <div v-if="importResultMeta?.renamedFrom" class="import-dl-row">
              <dt>流程名称</dt>
              <dd>
                <strong>{{ importResultMeta.displayName }}</strong>
                <span class="import-rename-note">（已避免与已有流程重名，由「{{ importResultMeta.renamedFrom }}」调整）</span>
              </dd>
            </div>
            <div v-else class="import-dl-row">
              <dt>流程名称</dt>
              <dd>
                <strong>{{ importResultMeta?.displayName ?? "—" }}</strong>
              </dd>
            </div>
            <div class="import-dl-row">
              <dt>文档版本</dt>
              <dd>{{ importResultMeta?.docVersion ?? "—" }}</dd>
            </div>
            <div class="import-dl-row">
              <dt>节点数</dt>
              <dd>{{ importResultMeta?.nodeCount ?? 0 }}（含子流程 / 循环内节点）</dd>
            </div>
            <div class="import-dl-row">
              <dt>策略数</dt>
              <dd>{{ importResultMeta?.strategyCount ?? 0 }}</dd>
            </div>
            <div class="import-dl-row">
              <dt>源文件</dt>
              <dd class="import-mono">{{ importResultMeta?.sourceFileName ?? "—" }}</dd>
            </div>
          </dl>
          <p class="import-next-hint">
            点击下方<strong>确认载入到编辑器</strong>后，左侧拓扑与右侧配置将切换为导入内容；流程处于「未保存」状态，请再点击顶部<strong>保存草稿</strong>才会写入服务器。
          </p>
          <div class="confirm-actions import-wizard-actions">
            <button type="button" class="btn ghost" @click="closeImportWizardDiscardResult">关闭（不载入）</button>
            <button type="button" class="btn primary" @click="confirmApplyImportedFlow">确认载入到编辑器</button>
          </div>
        </div>

        <!-- 失败 -->
        <div v-else-if="importView === 'error'" class="import-wizard-body">
          <div class="import-result-banner import-result-err">
            <span class="import-result-icon" aria-hidden="true">!</span>
            <div>
              <div class="import-result-title">导入未成功</div>
              <p class="import-result-sub">{{ importErrorPhaseLabel }}</p>
            </div>
          </div>
          <div class="import-error-box">
            <pre class="import-error-pre">{{ importErrorDetail }}</pre>
          </div>
          <p class="import-error-hint">请根据上述说明修正 YAML/JSON 后重新选择文件，或取消导入。</p>
          <div class="confirm-actions import-wizard-actions">
            <button type="button" class="btn ghost" @click="closeImportWizard">取消导入</button>
            <button type="button" class="btn primary" @click="retryImportPickFile">重新选择文件</button>
          </div>
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
import { parse as parseYaml } from "yaml";
import { useFlowStudioStore } from "@/stores/flowStudio";
import {
  allocateUniqueFlowDisplayName,
  flowListItemLabel,
  type FlowDocument,
  type FlowNode,
  type Selection,
} from "@/types/flow";
import { validateFlowDefinition } from "@/api/flowDefinition";
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
const LAST_STUDIO_SESSION_KEY = "flowEngine:flowStudio:lastSession";
const UNSAVED_SENTINEL = "__unsaved_new__";

const store = useFlowStudioStore();
const selectedId = ref("");
const selectedVersion = ref("draft");
const saving = ref<false | "draft" | "version">(false);
/** 从服务器拉取快照导出 YAML 时的防重复点击 */
const exportingYaml = ref(false);
const runVisible = ref(false);
const moreMenuOpen = ref(false);
const moreMenuRef = ref<HTMLElement | null>(null);
const versionConfirmOpen = ref(false);
const pendingVersion = ref(0);

const discardConfirmOpen = ref(false);
const discardConfirmText = ref("");
let discardConfirmResolver: ((ok: boolean) => void) | null = null;

type ImportWizardView = "form" | "working" | "success" | "error";

const importWizardOpen = ref(false);
const importView = ref<ImportWizardView>("form");
/** 打开导入窗口前的覆盖风险提示（弹窗） */
const importOpenGuardOpen = ref(false);
const importOpenGuardText = ref("");
const importFileInputRef = ref<HTMLInputElement | null>(null);
const importSelectedFile = ref<File | null>(null);
const importFormError = ref("");
const importValidatedDoc = ref<FlowDocument | null>(null);

const importProgressSteps = [
  { id: "read", label: "读取本地文件" },
  { id: "parse", label: "解析 YAML / JSON" },
  { id: "list", label: "同步流程列表（用于名称去重）" },
  { id: "validate", label: "服务端校验与编译" },
  { id: "finish", label: "生成导入结果" },
] as const;

const importProgressIndex = ref(-1);

type ImportSuccessMeta = {
  displayName: string;
  renamedFrom: string | null;
  docVersion: string;
  nodeCount: number;
  strategyCount: number;
  sourceFileName: string;
};

const importResultMeta = ref<ImportSuccessMeta | null>(null);

const importErrorDetail = ref("");
const importErrorPhaseKey = ref<"read" | "parse" | "list" | "validate" | "unknown">("unknown");

const importErrorPhaseLabel = computed(() => {
  const m: Record<string, string> = {
    read: "阶段：读取文件",
    parse: "阶段：本地解析",
    list: "阶段：同步流程列表",
    validate: "阶段：服务端校验",
    unknown: "阶段：未知",
  };
  return m[importErrorPhaseKey.value] ?? m.unknown;
});

const importFileStatusLabel = computed(() => {
  const f = importSelectedFile.value;
  if (!f) return "未选择文件";
  const kb = f.size / 1024;
  const sz = kb < 1024 ? `${kb.toFixed(1)} KB` : `${(kb / 1024).toFixed(2)} MB`;
  return `已选：${f.name}（${sz}）`;
});

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

/** 仅已绑定服务端流程且无「未写库新建」时可导出；选中「草稿」时须服务器确有草稿。 */
const canExportYaml = computed(() => {
  if (!store.activeFlowId || store.pendingNewFlowId) return false;
  const ch = selectedVersion.value;
  if (ch === "draft") return hasDraft.value;
  return /^\d+$/.test(ch) && Number(ch) >= 1;
});

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

type PersistedStudioSession = {
  flowId: string;
  versionChannel: string;
  selection: Selection | null;
};

function normalizeSelection(raw: unknown): Selection | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  if (obj.kind === "flow") return { kind: "flow" };
  if (obj.kind === "strategy" && typeof obj.key === "string" && obj.key.trim()) {
    return { kind: "strategy", key: obj.key };
  }
  if (obj.kind === "node" && Array.isArray(obj.path)) {
    const nums = obj.path.map((x) => Number(x));
    if (nums.length > 0 && nums.every((x) => Number.isInteger(x) && x >= 0)) {
      return { kind: "node", path: nums };
    }
  }
  return null;
}

function readStoredStudioSession(): PersistedStudioSession | null {
  try {
    const raw = localStorage.getItem(LAST_STUDIO_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const flowId = typeof parsed.flowId === "string" ? parsed.flowId.trim() : "";
    if (!flowId) return null;
    const versionChannel =
      typeof parsed.versionChannel === "string" && parsed.versionChannel.trim()
        ? parsed.versionChannel.trim()
        : "draft";
    const selection = normalizeSelection(parsed.selection);
    return { flowId, versionChannel, selection };
  } catch {
    return null;
  }
}

function persistStudioSession() {
  try {
    const fid = store.activeFlowId;
    if (!fid) {
      localStorage.removeItem(LAST_STUDIO_SESSION_KEY);
      return;
    }
    const channel = selectedVersion.value.trim() || "draft";
    localStorage.setItem(
      LAST_STUDIO_SESSION_KEY,
      JSON.stringify({
        flowId: fid,
        versionChannel: channel,
        selection: store.selection,
      }),
    );
  } catch {
    /* ignore */
  }
}

function clearStudioSession() {
  try {
    localStorage.removeItem(LAST_STUDIO_SESSION_KEY);
  } catch {
    /* ignore */
  }
}

function restoreWorkspaceSelection(sel: Selection | null | undefined) {
  if (!sel) return;
  if (sel.kind === "flow") {
    store.select({ kind: "flow" });
    return;
  }
  if (sel.kind === "strategy") {
    const key = sel.key.trim();
    if (key && Object.prototype.hasOwnProperty.call(store.doc.strategies, key)) {
      store.select({ kind: "strategy", key });
    } else {
      store.select({ kind: "flow" });
    }
    return;
  }
  if (sel.kind === "node") {
    const path = sel.path.filter((x) => Number.isInteger(x) && x >= 0);
    if (path.length > 0 && store.getNode(path)) {
      store.select({ kind: "node", path });
    } else {
      store.select({ kind: "flow" });
    }
  }
}

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
      clearStudioSession();
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

function countFlowNodesDeep(nodes: FlowNode[]): number {
  let c = 0;
  const walk = (list: FlowNode[]) => {
    for (const n of list) {
      c++;
      if (n.type === "loop" || n.type === "subflow") walk(n.children);
    }
  };
  walk(nodes);
  return c;
}

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(new Error("读取文件失败（可能被浏览器拦截或文件不可读）"));
    r.readAsText(file);
  });
}

function resetImportWizardState() {
  importSelectedFile.value = null;
  importFormError.value = "";
  importValidatedDoc.value = null;
  importResultMeta.value = null;
  importErrorDetail.value = "";
  importErrorPhaseKey.value = "unknown";
  importProgressIndex.value = -1;
  if (importFileInputRef.value) importFileInputRef.value.value = "";
}

function closeImportWizard() {
  if (importView.value === "working") return;
  importWizardOpen.value = false;
  importView.value = "form";
  resetImportWizardState();
}

function onImportWizardBackdrop() {
  if (importView.value === "working") return;
  closeImportWizard();
}

function cancelImportOpenGuard() {
  importOpenGuardOpen.value = false;
  importOpenGuardText.value = "";
}

function confirmImportOpenGuard() {
  importOpenGuardOpen.value = false;
  importOpenGuardText.value = "";
  actuallyOpenImportWizard();
}

function actuallyOpenImportWizard() {
  importView.value = "form";
  resetImportWizardState();
  importWizardOpen.value = true;
}

function openImportWizardFromMenu() {
  closeMoreMenu();
  if (store.pendingNewFlowId) {
    importOpenGuardText.value =
      "导入将会覆盖当前未保存的编辑（新流程尚未写库）。确定要打开导入窗口吗？";
    importOpenGuardOpen.value = true;
    return;
  }
  if (store.activeFlowId && selectedVersion.value === "draft" && hasDraft.value) {
    importOpenGuardText.value = "导入将会覆盖当前未保存的草稿。确定要打开导入窗口吗？";
    importOpenGuardOpen.value = true;
    return;
  }
  actuallyOpenImportWizard();
}

function triggerImportFilePick() {
  importFileInputRef.value?.click();
}

function onImportWizardFileChange(ev: Event) {
  const input = ev.target as HTMLInputElement;
  importSelectedFile.value = input.files?.[0] ?? null;
  importFormError.value = "";
}

function importStepClass(i: number): string {
  const p = importProgressIndex.value;
  if (i < p) return "is-done";
  if (i === p && importView.value === "working") return "is-active";
  return "is-pending";
}

function importStepMark(i: number): string {
  const p = importProgressIndex.value;
  if (i < p) return "✓";
  if (i === p && importView.value === "working") return "●";
  return String(i + 1);
}

function onImportWizardStart() {
  if (!importSelectedFile.value) {
    importFormError.value = "请先选择要导入的文件";
    return;
  }
  void runImportPipeline();
}

async function runImportPipeline() {
  const file = importSelectedFile.value;
  if (!file) {
    importFormError.value = "请先选择要导入的文件";
    return;
  }

  importFormError.value = "";
  importView.value = "working";
  importProgressIndex.value = 0;
  importErrorPhaseKey.value = "unknown";

  try {
    importErrorPhaseKey.value = "read";
    const text = await readFileAsText(file);

    importProgressIndex.value = 1;
    importErrorPhaseKey.value = "parse";
    const raw = parseImportText(text);

    importProgressIndex.value = 2;
    importErrorPhaseKey.value = "list";
    await store.refreshFlowList();

    importProgressIndex.value = 3;
    importErrorPhaseKey.value = "validate";
    const validated = await validateFlowDefinition(raw);
    const taken = store.flowList.map((f) => (f as { display_name?: string }).display_name ?? "");
    const beforeName = (validated.display_name ?? "").trim();
    const uniqueName = allocateUniqueFlowDisplayName(taken, validated.display_name);
    validated.display_name = uniqueName;

    importProgressIndex.value = 4;
    importValidatedDoc.value = validated;
    importResultMeta.value = {
      displayName: uniqueName,
      renamedFrom: uniqueName !== beforeName ? (beforeName || "（未填写）") : null,
      docVersion: validated.version ?? "—",
      nodeCount: countFlowNodesDeep(validated.nodes),
      strategyCount: Object.keys(validated.strategies ?? {}).length,
      sourceFileName: file.name,
    };
    importView.value = "success";
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    importErrorDetail.value = msg;
    importView.value = "error";
  }
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
  if (importOpenGuardOpen.value) {
    cancelImportOpenGuard();
    return;
  }
  closeMoreMenu();
  closeVersionConfirm();
  closeDeleteFlowConfirm();
  if (importWizardOpen.value && importView.value !== "working") closeImportWizard();
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

watch(
  () => [store.activeFlowId, selectedVersion.value, store.selection] as const,
  () => {
    persistStudioSession();
  },
  { deep: true },
);

onMounted(async () => {
  window.addEventListener("mousedown", onWindowMouseDown);
  window.addEventListener("keydown", onWindowKeydown);
  await store.refreshFlowList();
  try {
    const session = readStoredStudioSession();
    let last: string | null = null;
    try {
      last = localStorage.getItem(LAST_FLOW_STORAGE_KEY);
    } catch {
      last = null;
    }
    if (session?.flowId && store.flowList.some((f) => (f as { id: string }).id === session.flowId)) {
      await loadFlowWithVersions(session.flowId, {
        preferredVersion: session.versionChannel,
        preferredSelection: session.selection,
      });
    } else if (session?.flowId) {
      // 索引里缺失时仍尝试直连（例如列表延迟同步）；失败后回退到旧逻辑。
      try {
        await loadFlowWithVersions(session.flowId, {
          preferredVersion: session.versionChannel,
          preferredSelection: session.selection,
        });
        await store.refreshFlowList();
      } catch {
        clearStudioSession();
        if (last && store.flowList.some((f) => (f as { id: string }).id === last)) {
          await loadFlowWithVersions(last);
        } else if (store.flowList.some((f) => (f as { id: string }).id === "demo_flow")) {
          await loadFlowWithVersions("demo_flow");
        } else if (store.flowList.length > 0) {
          await loadFlowWithVersions((store.flowList[0] as { id: string }).id);
        }
      }
    } else if (last && store.flowList.some((f) => (f as { id: string }).id === last)) {
      await loadFlowWithVersions(last);
    } else if (last) {
      // localStorage 有上次 id 但列表索引未命中时仍尝试直连加载（成功后补刷列表，避免下拉空白）
      try {
        await loadFlowWithVersions(last);
        await store.refreshFlowList();
      } catch {
        try {
          localStorage.removeItem(LAST_FLOW_STORAGE_KEY);
        } catch {
          /* ignore */
        }
        if (store.flowList.some((f) => (f as { id: string }).id === "demo_flow")) {
          await loadFlowWithVersions("demo_flow");
        } else if (store.flowList.length > 0) {
          await loadFlowWithVersions((store.flowList[0] as { id: string }).id);
        }
      }
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

function resolvePreferredVersionChannel(preferredVersion: string | null | undefined): string {
  const preferred = (preferredVersion ?? "").trim();
  if (preferred === "draft") {
    return hasDraft.value ? "draft" : latestVersion.value > 0 ? String(latestVersion.value) : "draft";
  }
  if (/^\d+$/.test(preferred) && versionList.value.some((v) => String(v.version) === preferred)) {
    return preferred;
  }
  if (hasDraft.value) return "draft";
  if (latestVersion.value > 0) return String(latestVersion.value);
  return "draft";
}

async function loadFlowWithVersions(
  flowId: string,
  opts?: { preferredVersion?: string | null; preferredSelection?: Selection | null },
) {
  await store.loadFlowFromServer(flowId);
  await refreshVersionList(flowId);
  persistLastFlowId(flowId);
  selectedVersion.value = resolvePreferredVersionChannel(opts?.preferredVersion);
  await onSelectVersion();
  restoreWorkspaceSelection(opts?.preferredSelection);
  persistStudioSession();
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
  const selectionBeforeSave = store.selection;
  flushActiveInput();
  store.flushNodeDraftsToDocument();
  saving.value = "draft";
  const wasUnpersistedNew = !!store.pendingNewFlowId;
  try {
    await putFlowDraft(fid, store.doc as unknown as Record<string, unknown>);
    // 新流程首次写库后必须把索引同步进 flowList，否则顶部 <select> 的 value 无对应 option 会显示空白
    await store.refreshFlowList();
    await store.loadFlowFromServer(fid);
    await refreshVersionList(fid);
    selectedVersion.value = "draft";
    await onSelectVersion();
    restoreWorkspaceSelection(selectionBeforeSave);
    persistStudioSession();
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
  const selectionBeforeSave = store.selection;
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
    restoreWorkspaceSelection(selectionBeforeSave);
    persistStudioSession();
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

async function onDownloadFromMenu() {
  closeMoreMenu();
  if (!canExportYaml.value || exportingYaml.value) return;
  await downloadPersistedSnapshot();
}

async function downloadPersistedSnapshot() {
  const fid = store.activeFlowId;
  if (!fid || !canExportYaml.value) return;
  exportingYaml.value = true;
  try {
    let data: Record<string, unknown>;
    if (selectedVersion.value === "draft") {
      data = await fetchDraft(fid);
    } else {
      data = await fetchVersion(fid, Number(selectedVersion.value));
    }
    const yaml = store.snapshotToYaml(data);
    const blob = new Blob([yaml], { type: "text/yaml;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const base = ((data.display_name as string | undefined) ?? "").trim() || "flow";
    const suffix = selectedVersion.value === "draft" ? "draft" : `V${selectedVersion.value}`;
    a.download = `${base}_${suffix}.yaml`;
    a.click();
    URL.revokeObjectURL(a.href);
    showMsg("ok", "已从服务器导出当前所选快照（不含未保存编辑）");
  } catch (e) {
    showMsg("err", e instanceof Error ? e.message : String(e));
  } finally {
    exportingYaml.value = false;
  }
}

function retryImportPickFile() {
  importErrorDetail.value = "";
  importErrorPhaseKey.value = "unknown";
  importView.value = "form";
  importSelectedFile.value = null;
  if (importFileInputRef.value) importFileInputRef.value.value = "";
}

function closeImportWizardDiscardResult() {
  importValidatedDoc.value = null;
  importResultMeta.value = null;
  closeImportWizard();
}

function confirmApplyImportedFlow() {
  const doc = importValidatedDoc.value;
  if (!doc) return;
  store.applyImportAsUnpersistedNewFlow(doc);
  selectedVersion.value = "draft";
  versionList.value = [];
  latestVersion.value = 0;
  hasDraft.value = false;
  closeImportWizard();
  showMsg("ok", "已载入编辑区；请保存草稿以写入服务器");
}

function parseImportText(text: string): Record<string, unknown> {
  const trimmed = text.trim();
  if (!trimmed) {
    throw new Error("文件为空");
  }
  let parsed: unknown;
  try {
    parsed = parseYaml(text);
  } catch {
    try {
      parsed = JSON.parse(text) as unknown;
    } catch {
      throw new Error("YAML/JSON 解析失败");
    }
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("流程文件格式无效：根必须是对象");
  }
  return parsed as Record<string, unknown>;
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

/** 试运行：与主按钮（实心）和草稿（灰底）区分 */
.btn.trial-run {
  border-color: color-mix(in srgb, var(--accent) 42%, transparent);
  background: color-mix(in srgb, var(--accent) 14%, var(--surface));
  color: color-mix(in srgb, var(--accent) 25%, #1e293b);
  font-weight: 600;
}

.btn.trial-run:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--accent) 55%, transparent);
  background: color-mix(in srgb, var(--accent) 22%, var(--surface));
}

.btn.trial-run:disabled {
  color: var(--muted);
  background: var(--surface);
  border-color: var(--border);
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

.menu-item:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.menu-item:disabled:hover {
  border-color: transparent;
  background: transparent;
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

/* —— 导入向导 —— */
.import-open-guard-mask {
  z-index: 43;
}

.import-wizard-mask {
  z-index: 42;
}

.import-wizard-dialog {
  width: min(560px, calc(100vw - 32px));
  max-height: min(90vh, 720px);
  overflow: auto;
  padding: 18px 18px 16px;
}

.import-wizard-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
}

.import-wizard-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.import-wizard-close {
  flex-shrink: 0;
  padding: 2px 10px;
  font-size: 18px;
  line-height: 1;
}

.import-wizard-body {
  margin-top: 10px;
}

.import-wizard-lead {
  margin: 0 0 14px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--muted);
}

.import-file-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.import-file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.import-file-meta {
  font-size: 12px;
  color: var(--text);
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.import-inline-err {
  margin: 0 0 10px;
  font-size: 12px;
  color: #b45309;
}

.import-wizard-actions {
  margin-top: 16px;
  flex-wrap: wrap;
}

.import-working {
  text-align: center;
  padding: 8px 0 4px;
}

.import-spinner {
  width: 42px;
  height: 42px;
  margin: 0 auto 14px;
  border-radius: 50%;
  border: 3px solid color-mix(in srgb, var(--border) 80%, transparent);
  border-top-color: var(--accent);
  animation: import-spin 0.85s linear infinite;
}

@keyframes import-spin {
  to {
    transform: rotate(360deg);
  }
}

.import-progress-title {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
}

.import-step-list {
  list-style: none;
  padding: 0;
  margin: 12px 0 0;
  text-align: left;
  font-size: 13px;
}

.import-step-list li {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 7px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  color: var(--muted);
}

.import-step-list li.is-done {
  color: var(--muted);
  opacity: 0.85;
}

.import-step-list li.is-active {
  color: var(--accent);
  font-weight: 600;
  opacity: 1;
}

.import-step-list li.is-pending {
  opacity: 0.65;
}

.import-step-ix {
  width: 1.35rem;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, monospace;
  text-align: right;
}

.import-progress-hint {
  margin: 14px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.import-result-banner {
  display: flex;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  align-items: flex-start;
}

.import-result-ok {
  background: color-mix(in srgb, #ecfdf5 92%, var(--surface));
  border: 1px solid color-mix(in srgb, #6ee7b7 40%, var(--border));
}

.import-result-err {
  background: color-mix(in srgb, #fef2f2 92%, var(--surface));
  border: 1px solid color-mix(in srgb, #fecaca 85%, var(--border));
}

.import-result-icon {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  font-weight: 700;
  font-size: 14px;
}

.import-result-ok .import-result-icon {
  background: color-mix(in srgb, #10b981 22%, transparent);
  color: #047857;
}

.import-result-err .import-result-icon {
  background: color-mix(in srgb, #f87171 22%, transparent);
  color: #b91c1c;
}

.import-result-title {
  font-size: 14px;
  font-weight: 700;
}

.import-result-sub {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--muted);
}

.import-result-dl {
  margin: 14px 0 0;
  padding: 0;
}

.import-dl-row {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 8px 12px;
  padding: 8px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 65%, transparent);
  font-size: 13px;
}

.import-dl-row dt {
  margin: 0;
  color: var(--muted);
  font-weight: 500;
}

.import-dl-row dd {
  margin: 0;
  min-width: 0;
}

.import-mono {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  word-break: break-all;
}

.import-rename-note {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  font-weight: 400;
  color: var(--muted);
}

.import-next-hint {
  margin: 14px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text);
}

.import-error-box {
  margin-top: 12px;
  max-height: 260px;
  overflow: auto;
  background: color-mix(in srgb, #fff7ed 88%, var(--surface));
  border: 1px solid color-mix(in srgb, #fdba74 45%, var(--border));
  border-radius: 8px;
  padding: 10px 12px;
}

.import-error-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.45;
  color: #7c2d12;
}

.import-error-hint {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
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
