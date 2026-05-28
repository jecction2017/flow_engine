<template>
  <div class="profile-page">
    <header class="top">
      <div class="brand">
        <span class="logo">◇</span>
        <div>
          <div class="title">环境配置</div>
          <div class="subtitle">环境列表 · 默认项 · 副作用函数抑制规则</div>
        </div>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <div v-if="activeDialog" class="confirm-mask" @click.self="closeDialog">
      <div
        class="confirm-dialog"
        role="dialog"
        aria-modal="true"
        :aria-label="dialogAriaLabel"
      >
        <template v-if="activeDialog.type === 'clear'">
          <div class="confirm-title">清空该环境的抑制规则覆盖？</div>
          <p class="confirm-text">
            将当前环境在 debug / shadow / production 三处 JSON 置为 <code class="mono">[]</code>。未保存的编辑会丢失；保存后沿用进程内置默认。
          </p>
          <div class="confirm-actions">
            <button type="button" class="btn ghost" @click="closeDialog">取消</button>
            <button type="button" class="btn ghost danger" @click="submitClear">确认清空</button>
          </div>
        </template>
        <template v-else-if="activeDialog.type === 'setDefault'">
          <div class="confirm-title">设为默认环境？</div>
          <p class="confirm-text">
            将 <code class="mono">{{ activeDialog.code }}</code> 设为全局默认；未显式指定环境时将使用该编码。
          </p>
          <div class="confirm-actions">
            <button type="button" class="btn ghost" @click="closeDialog">取消</button>
            <button
              type="button"
              class="btn small primary"
              :disabled="!!defaultingEnv"
              @click="submitSetDefault"
            >
              {{ defaultingEnv ? "保存中…" : "确认" }}
            </button>
          </div>
        </template>
        <template v-else>
          <div class="confirm-title">删除环境？</div>
          <p class="confirm-text">
            将删除环境 <code class="mono">{{ activeDialog.code }}</code>（软删除）。服务端会校验：若部署、测试、数据字典、Lookup
            或流程定义中仍引用该环境编码，将拒绝删除。
          </p>
          <div class="confirm-actions">
            <button type="button" class="btn ghost" @click="closeDialog">取消</button>
            <button
              type="button"
              class="btn ghost danger"
              :disabled="!!deletingEnv"
              @click="submitDelete"
            >
              {{ deletingEnv ? "删除中…" : "删除" }}
            </button>
          </div>
        </template>
      </div>
    </div>

    <p class="hint-bar">
      流程在不同环境下使用不同的副作用函数抑制规则；字段 <code class="mono">system_capability_policy</code>。
    </p>

    <div class="body">
      <aside class="left" aria-label="环境列表与默认项">
        <div class="side-head">
          <div class="side-title">环境</div>
          <div class="muted small">{{ profiles.length }} 个</div>
        </div>

        <div class="side-block">
          <div class="lbl-row">
            <span class="lbl">新增环境</span>
          </div>
          <div class="add-row">
            <input v-model="newProfile" class="inp sm mono" placeholder="dev、sit、prod" spellcheck="false" />
            <button type="button" class="btn small ghost" :disabled="savingCreate || !newProfile.trim()" @click="create">
              {{ savingCreate ? "…" : "创建" }}
            </button>
          </div>
        </div>

        <div class="section-title">
          <span>已有环境</span>
        </div>
        <ul class="profile-list" role="listbox" aria-label="环境列表">
          <li
            v-for="p in profiles"
            :key="p"
            role="option"
            :aria-selected="p === policyProfile"
            :class="['profile-item', { active: p === policyProfile, 'is-default': p === defaultProfile }]"
            @click="loadPolicyFor(p)"
          >
            <span class="mono name">{{ p }}</span>
            <div class="profile-item-tail">
              <span class="badges">
                <span v-if="p === defaultProfile" class="pill">默认</span>
              </span>
              <button
                v-if="p !== defaultProfile"
                type="button"
                class="set-default-btn"
                :class="{ 'is-revealed': defaultingEnv === p }"
                :disabled="loading || !!defaultingEnv || !!deletingEnv"
                aria-label="设为默认环境"
                @click.stop="openSetDefaultConfirm(p)"
              >
                {{ defaultingEnv === p ? "…" : "设为默认" }}
              </button>
              <button
                v-if="p !== 'default'"
                type="button"
                class="delete-env-btn"
                :class="{ 'is-revealed': deletingEnv === p }"
                :disabled="loading || !!defaultingEnv || !!deletingEnv || p === defaultProfile"
                :title="p === defaultProfile ? '请先将其他环境设为默认后再删除' : undefined"
                aria-label="删除环境"
                @click.stop="openDeleteConfirm(p)"
              >
                {{ deletingEnv === p ? "…" : "删除" }}
              </button>
            </div>
          </li>
        </ul>
      </aside>

      <main class="right" aria-label="当前环境配置">
        <header v-if="policyProfile" class="env-focus">
          <div class="env-focus-top">
            <h2 class="env-focus-name mono">{{ policyProfile }}</h2>
            <span v-if="policyProfile === defaultProfile" class="pill">默认</span>
          </div>
          <p class="muted small env-focus-line">环境编码 · 本区为该环境下的相关设置（当前可编辑抑制规则）。</p>
        </header>

        <section class="panel">
          <header class="panel-head">
            <div class="panel-intro">
              <div class="panel-title-row">
                <span class="panel-title">副作用函数抑制规则</span>
                <InfoTip
                  wide
                  align-end
                  text="流程运行模式（调试、灰度、生产）与 所选环境决定应用的规则。副作用函数规则匹配优先级：节点配置 → 运行时配置 → 环境配置 → 内置默认，先命中先生效；都无则放行。"
                />
              </div>
            </div>
            <div class="panel-actions">
              <button
                type="button"
                class="btn small ghost"
                :disabled="loading || !systemDefaultPolicy"
                title="用内置默认填入三处编辑框"
                @click="fillFromSystemDefault"
              >
                用内置默认填充
              </button>
              <button
                type="button"
                class="btn small ghost danger"
                :disabled="loading"
                title="三处均置为 []"
                @click="askClearOverride"
              >
                清空覆盖
              </button>
              <button type="button" class="btn small primary" :disabled="savingPolicy || !policyProfile" @click="savePolicy">
                {{ savingPolicy ? "保存中…" : "保存规则" }}
              </button>
            </div>
          </header>

          <div class="json-grid">
            <div class="json-card">
              <label class="field full">
                <span class="json-card-title">debug</span>
                <span class="json-card-sub muted small">调试 / 试运行 / 测试</span>
                <JsonEditor v-model="policyJsonDebug" :height="240" />
              </label>
            </div>
            <div class="json-card">
              <label class="field full">
                <span class="json-card-title">shadow</span>
                <span class="json-card-sub muted small">影子 / 预发</span>
                <JsonEditor v-model="policyJsonShadow" :height="240" />
              </label>
            </div>
            <div class="json-card">
              <label class="field full">
                <span class="json-card-title">production</span>
                <span class="json-card-sub muted small">生产</span>
                <JsonEditor v-model="policyJsonProduction" :height="240" />
              </label>
            </div>
          </div>

          <details class="sys-default">
            <summary>内置默认规则</summary>
            <p class="muted small sys-sum">debug/shadow 抑制 integration、db_write、mq_publish；production 放行。</p>
            <div v-if="systemDefaultPolicy" class="sys-default-body">
              <div class="sys-col">
                <div class="sys-title">debug</div>
                <ReadonlyJsonEditor :model-value="systemDefaultJson.debug" :default-height="200" :min-height="120" />
              </div>
              <div class="sys-col">
                <div class="sys-title">shadow</div>
                <ReadonlyJsonEditor :model-value="systemDefaultJson.shadow" :default-height="200" :min-height="120" />
              </div>
              <div class="sys-col">
                <div class="sys-title">production</div>
                <ReadonlyJsonEditor :model-value="systemDefaultJson.production" :default-height="200" :min-height="120" />
              </div>
            </div>
            <p v-else class="muted small">内置默认未加载；离开本页再进入将重新请求。</p>
          </details>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import JsonEditor from "@/components/JsonEditor.vue";
import ReadonlyJsonEditor from "@/components/ReadonlyJsonEditor.vue";
import {
  createProfile,
  deleteProfile,
  fetchProfileConfig,
  fetchProfileSystemPolicy,
  fetchSystemDefaultCapabilityPolicy,
  saveDefaultProfile,
  saveProfileSystemPolicy,
} from "@/api/profiles";

type ActiveDialog =
  | { type: "clear" }
  | { type: "setDefault"; code: string }
  | { type: "delete"; code: string };

const profiles = ref<string[]>(["default"]);
const defaultProfile = ref("default");
const newProfile = ref("");
const loading = ref(false);
const defaultingEnv = ref<string | null>(null);
const deletingEnv = ref<string | null>(null);
const savingCreate = ref(false);
const error = ref("");

const activeDialog = ref<ActiveDialog | null>(null);

const dialogAriaLabel = computed(() => {
  const d = activeDialog.value;
  if (!d) return "确认";
  if (d.type === "clear") return "确认清空规则覆盖";
  if (d.type === "setDefault") return "确认设为默认环境";
  return "确认删除环境";
});

const policyProfile = ref<string>("");
const policyJsonDebug = ref("[]");
const policyJsonShadow = ref("[]");
const policyJsonProduction = ref("[]");
const savingPolicy = ref(false);

type SysDefaultPolicy = {
  debug: Record<string, unknown>[];
  shadow: Record<string, unknown>[];
  production: Record<string, unknown>[];
};
const systemDefaultPolicy = ref<SysDefaultPolicy | null>(null);
const systemDefaultJson = computed(() => ({
  debug: JSON.stringify(systemDefaultPolicy.value?.debug ?? [], null, 2),
  shadow: JSON.stringify(systemDefaultPolicy.value?.shadow ?? [], null, 2),
  production: JSON.stringify(systemDefaultPolicy.value?.production ?? [], null, 2),
}));

function closeDialog() {
  activeDialog.value = null;
}

function askClearOverride() {
  activeDialog.value = { type: "clear" };
}

function submitClear() {
  if (activeDialog.value?.type !== "clear") return;
  clearOverride();
  closeDialog();
}

async function submitSetDefault() {
  if (activeDialog.value?.type !== "setDefault") return;
  const code = activeDialog.value.code;
  closeDialog();
  await doSetDefault(code);
}

async function submitDelete() {
  if (activeDialog.value?.type !== "delete") return;
  const code = activeDialog.value.code;
  closeDialog();
  await doDelete(code);
}

function openSetDefaultConfirm(code: string) {
  if (!code || code === defaultProfile.value) return;
  activeDialog.value = { type: "setDefault", code };
}

function openDeleteConfirm(code: string) {
  if (!code || code === "default") return;
  activeDialog.value = { type: "delete", code };
}

async function reload() {
  error.value = "";
  loading.value = true;
  try {
    const res = await fetchProfileConfig();
    profiles.value = res.profiles.length ? res.profiles : ["default"];
    defaultProfile.value = res.default_profile || profiles.value[0] || "default";
    if (!policyProfile.value || !profiles.value.includes(policyProfile.value)) {
      policyProfile.value = defaultProfile.value;
      await loadPolicyFor(policyProfile.value);
    }
    if (!systemDefaultPolicy.value) {
      systemDefaultPolicy.value = await fetchSystemDefaultCapabilityPolicy();
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

async function loadPolicyFor(profile: string) {
  if (!profile) return;
  policyProfile.value = profile;
  error.value = "";
  try {
    const res = await fetchProfileSystemPolicy(profile);
    const m = (res.system_capability_policy || {}) as Record<string, unknown>;
    policyJsonDebug.value = JSON.stringify(m.debug ?? [], null, 2);
    policyJsonShadow.value = JSON.stringify(m.shadow ?? [], null, 2);
    policyJsonProduction.value = JSON.stringify(m.production ?? [], null, 2);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function savePolicy() {
  if (!policyProfile.value) return;
  savingPolicy.value = true;
  error.value = "";
  try {
    const parseList = (raw: string, label: string): Record<string, unknown>[] => {
      const v = JSON.parse(raw || "[]") as unknown;
      if (!Array.isArray(v)) throw new Error(`${label} 必须是 JSON 数组`);
      return v as Record<string, unknown>[];
    };
    const payload = {
      debug: parseList(policyJsonDebug.value, "debug"),
      shadow: parseList(policyJsonShadow.value, "shadow"),
      production: parseList(policyJsonProduction.value, "production"),
    };
    const res = await saveProfileSystemPolicy(policyProfile.value, payload as Record<string, unknown>);
    const m = (res.system_capability_policy || {}) as Record<string, unknown>;
    policyJsonDebug.value = JSON.stringify(m.debug ?? [], null, 2);
    policyJsonShadow.value = JSON.stringify(m.shadow ?? [], null, 2);
    policyJsonProduction.value = JSON.stringify(m.production ?? [], null, 2);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    savingPolicy.value = false;
  }
}

function fillFromSystemDefault() {
  if (!systemDefaultPolicy.value) return;
  policyJsonDebug.value = JSON.stringify(systemDefaultPolicy.value.debug || [], null, 2);
  policyJsonShadow.value = JSON.stringify(systemDefaultPolicy.value.shadow || [], null, 2);
  policyJsonProduction.value = JSON.stringify(systemDefaultPolicy.value.production || [], null, 2);
}

function clearOverride() {
  policyJsonDebug.value = "[]";
  policyJsonShadow.value = "[]";
  policyJsonProduction.value = "[]";
}

async function doSetDefault(code: string) {
  if (!code || code === defaultProfile.value || defaultingEnv.value) return;
  defaultingEnv.value = code;
  error.value = "";
  try {
    await saveDefaultProfile(code);
    await reload();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    defaultingEnv.value = null;
  }
}

async function doDelete(code: string) {
  if (!code || code === "default" || deletingEnv.value) return;
  deletingEnv.value = code;
  error.value = "";
  try {
    await deleteProfile(code);
    await reload();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    deletingEnv.value = null;
  }
}

async function create() {
  const pid = newProfile.value.trim();
  if (!pid) return;
  savingCreate.value = true;
  error.value = "";
  try {
    await createProfile(pid);
    newProfile.value = "";
    await reload();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    savingCreate.value = false;
  }
}

void reload();
</script>

<style scoped>
.profile-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: linear-gradient(180deg, #fbfcff 0%, #f6f8fc 100%);
}

.top {
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 86%, transparent);
  flex-wrap: wrap;
  flex-shrink: 0;
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
  font-size: 15px;
}

.subtitle {
  font-size: 11px;
  color: var(--muted);
  margin-top: 2px;
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
}

.btn.small {
  padding: 4px 8px;
  font-size: 11px;
}

.btn.primary {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: var(--accent);
  color: #fff;
}

.btn.danger {
  border-color: color-mix(in srgb, #dc2626 35%, var(--border));
  color: #b91c1c;
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.err {
  margin: 0;
  padding: 8px 16px;
  font-size: 12px;
  color: #b91c1c;
  background: color-mix(in srgb, #fecaca 35%, transparent);
  border-bottom: 1px solid color-mix(in srgb, #f87171 30%, transparent);
  flex-shrink: 0;
}

.hint-bar {
  margin: 0;
  padding: 8px 16px;
  font-size: 11px;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 94%, transparent);
  line-height: 1.5;
  flex-shrink: 0;
}

.hint-bar code {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 4px;
  background: #fff8;
}

.confirm-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  z-index: 50;
}

.confirm-dialog {
  width: min(520px, 100%);
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: var(--shadow);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.confirm-title {
  font-weight: 800;
  font-size: 14px;
}

.confirm-text {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(260px, 300px) minmax(0, 1fr);
  gap: 0;
  overflow: hidden;
}

.left {
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  overflow: auto;
  padding: 10px 12px;
  min-width: 0;
}

.right {
  min-width: 0;
  overflow: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.env-focus {
  flex-shrink: 0;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: color-mix(in srgb, var(--surface) 94%, transparent);
}

.env-focus-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.env-focus-name {
  margin: 0;
  font-size: 16px;
  font-weight: 800;
  color: var(--text);
  letter-spacing: -0.02em;
}

.env-focus-line {
  margin: 6px 0 0;
  line-height: 1.45;
}

.side-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.side-title {
  font-weight: 800;
  font-size: 13px;
}

.side-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}

.lbl-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.lbl {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  font-weight: 700;
  color: var(--text);
  margin: 4px 0 8px;
  padding-top: 4px;
  border-top: 1px dashed var(--border);
}

.inp {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 12px;
  background: #fff;
  min-width: 0;
}

.inp.sm {
  padding: 5px 7px;
  font-size: 11px;
}

.inp:focus {
  outline: none;
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.add-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.add-row .inp {
  flex: 1;
}

.btn.full {
  width: 100%;
  box-sizing: border-box;
}

.profile-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.profile-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 8px 10px;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
}

.profile-item:hover {
  background: color-mix(in srgb, var(--accent-soft) 50%, transparent);
}

.profile-item.active {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: var(--accent-soft);
}

.profile-item .name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.profile-item-tail {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  margin-left: auto;
}

.set-default-btn {
  flex-shrink: 0;
  white-space: nowrap;
  margin: 0;
  font: inherit;
  font-size: 10px;
  line-height: 1.2;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: #fbfdff;
  color: var(--muted);
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transition:
    opacity 0.14s ease,
    border-color 0.14s ease,
    color 0.14s ease,
    background 0.14s ease;
}

.profile-item:hover .set-default-btn,
.profile-item:focus-within .set-default-btn,
.set-default-btn.is-revealed,
.profile-item:hover .delete-env-btn,
.profile-item:focus-within .delete-env-btn,
.delete-env-btn.is-revealed {
  opacity: 1;
  pointer-events: auto;
}

.set-default-btn:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  color: var(--text);
  background: color-mix(in srgb, var(--accent-soft) 55%, #fbfdff);
}

.set-default-btn:disabled {
  cursor: not-allowed;
}

.set-default-btn.is-revealed:disabled {
  opacity: 1;
  pointer-events: none;
}

.set-default-btn:disabled:not(.is-revealed) {
  opacity: 0.45;
}

.profile-item:hover .set-default-btn:disabled:not(.is-revealed),
.profile-item:focus-within .set-default-btn:disabled:not(.is-revealed) {
  opacity: 0;
  pointer-events: none;
}

.delete-env-btn {
  flex-shrink: 0;
  white-space: nowrap;
  margin: 0;
  font: inherit;
  font-size: 10px;
  line-height: 1.2;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, #fecaca 55%, var(--border));
  background: color-mix(in srgb, #fef2f2 75%, #fbfdff);
  color: var(--muted);
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transition:
    opacity 0.14s ease,
    border-color 0.14s ease,
    color 0.14s ease,
    background 0.14s ease;
}

.delete-env-btn:hover:not(:disabled) {
  border-color: color-mix(in srgb, #dc2626 45%, var(--border));
  color: #b91c1c;
  background: #fef2f2;
}

.delete-env-btn:disabled {
  cursor: not-allowed;
}

.delete-env-btn.is-revealed:disabled {
  opacity: 1;
  pointer-events: none;
}

.delete-env-btn:disabled:not(.is-revealed) {
  opacity: 0.45;
}

.profile-item:hover .delete-env-btn:disabled:not(.is-revealed),
.profile-item:focus-within .delete-env-btn:disabled:not(.is-revealed) {
  opacity: 0;
  pointer-events: none;
}

.badges {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.pill {
  font-size: 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 1px 6px;
  color: var(--muted);
  background: #fbfdff;
}

.panel {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow: auto;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.panel-intro {
  min-width: 0;
  flex: 1;
}

.panel-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.panel-title {
  font-weight: 800;
  font-size: 14px;
}

.panel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  justify-content: flex-end;
}

.muted {
  color: var(--muted);
}

.small {
  font-size: 11px;
}

.sys-default {
  border: 1px dashed var(--border);
  border-radius: 10px;
  padding: 8px 10px;
  background: color-mix(in srgb, var(--surface) 88%, #fff);
  min-width: 0;
  max-width: 100%;
}

.sys-default summary {
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
}

.sys-sum {
  margin: 6px 0 8px;
}

.sys-default-body {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 4px;
  min-width: 0;
}

.sys-col {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  padding: 8px 10px;
  min-width: 0;
}

.sys-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 6px;
}

.sys-json {
  margin: 0;
  padding: 8px;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--border) 85%, #94a3b8);
  background: color-mix(in srgb, #f1f5f9 92%, var(--surface));
  color: #334155;
  font-size: 11px;
  overflow: auto;
  max-height: 200px;
  max-width: 100%;
  min-width: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.json-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  min-width: 0;
}

@media (min-width: 1100px) {
  .json-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    align-items: start;
  }
}

@media (max-width: 900px) {
  .body {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(0, 1fr);
    overflow: auto;
  }

  .left {
    border-right: none;
    border-bottom: 1px solid var(--border);
    max-height: 320px;
  }

  .right {
    min-height: 0;
    overflow: auto;
  }

  .sys-default-body {
    grid-template-columns: 1fr;
  }
}

.json-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  background: #fbfdff;
  min-width: 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field.full {
  min-width: 0;
  width: 100%;
}

.json-card-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
}

.json-card-sub {
  margin-bottom: 4px;
}

.ta {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px;
  background: #fff;
  font-size: 12px;
  outline: none;
  resize: vertical;
  min-height: 160px;
}

.ta:focus {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}
</style>
