<template>
  <div class="profile-page">
    <header class="top">
      <div>
        <div class="title">全局环境 Profile</div>
        <div class="subtitle">管理 dev / sit / prod 等环境，并设置运行默认值</div>
      </div>
      <button type="button" class="btn ghost" :disabled="loading" @click="reload">刷新</button>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="panel">
      <label class="field">
        <span>默认 Profile</span>
        <select v-model="defaultProfile" class="inp" :disabled="loading || savingDefault">
          <option v-for="p in profiles" :key="p" :value="p">{{ p }}</option>
        </select>
      </label>
      <button type="button" class="btn primary" :disabled="savingDefault || !defaultProfile" @click="saveDefault">
        {{ savingDefault ? "保存中…" : "保存默认值" }}
      </button>
    </div>

    <div class="panel">
      <div class="field">
        <span>新增 Profile</span>
        <div class="row">
          <input v-model="newProfile" class="inp mono" placeholder="dev / sit / prod" />
          <button type="button" class="btn ghost" :disabled="savingCreate || !newProfile.trim()" @click="create">
            {{ savingCreate ? "创建中…" : "创建" }}
          </button>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="field"><span>Profiles</span></div>
      <ul class="list">
        <li
          v-for="p in profiles"
          :key="p"
          :class="{ active: p === defaultProfile, selected: p === policyProfile }"
          @click="loadPolicyFor(p)"
        >
          <span class="mono">{{ p }}</span>
          <span v-if="p === defaultProfile" class="tag">default</span>
          <span v-if="p === policyProfile" class="tag tag-edit">编辑中</span>
        </li>
      </ul>
    </div>

    <div class="panel">
      <div class="row sec-title">
        <div>
          <div class="title">环境能力策略</div>
          <div class="subtitle">
            按 RunMode（debug / shadow / production）分别配置规则列表。优先级低于「部署附加策略」「本次附加策略」「节点能力策略」，高于进程内置默认。
            保存后对本环境（Profile）下的部署、试运行、测试、调试（选用该 Profile 时）均生效。
          </div>
        </div>
        <div class="row">
          <select v-model="policyProfile" class="inp mono" @change="loadPolicyFor(policyProfile)">
            <option v-for="p in profiles" :key="p" :value="p">{{ p }}</option>
          </select>
          <button
            type="button"
            class="btn ghost"
            :disabled="loading || !systemDefaultPolicy"
            title="将进程内置的 debug / shadow / production 默认规则分别填入下方三个编辑框，便于在此基础上修改"
            @click="fillFromSystemDefault"
          >
            用系统默认填充
          </button>
          <button
            type="button"
            class="btn ghost"
            :disabled="loading"
            title="清空环境覆盖层，回到仅使用系统内置默认策略"
            @click="clearOverride"
          >
            清空覆盖
          </button>
          <button
            type="button"
            class="btn primary"
            :disabled="savingPolicy || !policyProfile"
            @click="savePolicy"
          >
            {{ savingPolicy ? "保存中…" : "保存策略" }}
          </button>
        </div>
      </div>

      <details class="sys-default" :open="false">
        <summary class="sys-default-sum">
          查看系统内置默认策略（只读）
          <span class="muted small">debug/shadow 默认抑制 integration/db_write/mq_publish；production 默认放行</span>
        </summary>
        <div v-if="systemDefaultPolicy" class="sys-default-body">
          <div class="sys-col">
            <div class="sys-title">debug</div>
            <pre class="sys-json mono">{{ JSON.stringify(systemDefaultPolicy.debug, null, 2) }}</pre>
          </div>
          <div class="sys-col">
            <div class="sys-title">shadow</div>
            <pre class="sys-json mono">{{ JSON.stringify(systemDefaultPolicy.shadow, null, 2) }}</pre>
          </div>
          <div class="sys-col">
            <div class="sys-title">production</div>
            <pre class="sys-json mono">{{ JSON.stringify(systemDefaultPolicy.production, null, 2) }}</pre>
          </div>
        </div>
        <p v-else class="muted small">
          系统默认策略加载失败或未就绪。可先刷新页面重试。
        </p>
      </details>

      <div class="json-editor-section">
        <div class="json-section-hint muted small">
          以下三套分别对应 RunMode：<strong>debug</strong>（调试/试运行/测试）、<strong>shadow</strong>、<strong>production</strong>（部署）。
          若页面被裁切，请在本区域内向下滚动。
        </div>
        <div class="json-grid">
          <div class="json-card">
            <label class="field full">
              <span class="json-card-title">debug · 调试 / 试运行 / 测试</span>
              <span class="json-card-sub muted small">JSON 数组（技术类型 CapabilityRule[]）</span>
              <textarea v-model="policyJsonDebug" class="ta mono" rows="8" spellcheck="false" />
            </label>
          </div>
          <div class="json-card">
            <label class="field full">
              <span class="json-card-title">shadow · 影子 / 预发类运行</span>
              <span class="json-card-sub muted small">JSON 数组（技术类型 CapabilityRule[]）</span>
              <textarea v-model="policyJsonShadow" class="ta mono" rows="8" spellcheck="false" />
            </label>
          </div>
          <div class="json-card">
            <label class="field full">
              <span class="json-card-title">production · 生产部署</span>
              <span class="json-card-sub muted small">JSON 数组（技术类型 CapabilityRule[]）</span>
              <textarea v-model="policyJsonProduction" class="ta mono" rows="8" spellcheck="false" />
            </label>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import {
  createProfile,
  fetchProfileConfig,
  fetchProfileSystemPolicy,
  fetchSystemDefaultCapabilityPolicy,
  saveDefaultProfile,
  saveProfileSystemPolicy,
} from "@/api/profiles";

const profiles = ref<string[]>(["default"]);
const defaultProfile = ref("default");
const newProfile = ref("");
const loading = ref(false);
const savingDefault = ref(false);
const savingCreate = ref(false);
const error = ref("");

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

async function reload() {
  error.value = "";
  loading.value = true;
  try {
    const res = await fetchProfileConfig();
    profiles.value = res.profiles.length ? res.profiles : ["default"];
    defaultProfile.value = res.default_profile || profiles.value[0] || "default";
    if (!policyProfile.value || !profiles.value.includes(policyProfile.value)) {
      // 默认编辑当前默认 profile，避免空白页观感。
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
    // server returns map shape: {debug,shadow,production}; legacy list is normalized server-side
    const m = (res.system_capability_policy || {}) as any;
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
    const res = await saveProfileSystemPolicy(policyProfile.value, payload as any);
    const m = (res.system_capability_policy || {}) as any;
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

async function saveDefault() {
  savingDefault.value = true;
  error.value = "";
  try {
    await saveDefaultProfile(defaultProfile.value);
    await reload();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    savingDefault.value = false;
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
/* 父级 main-fill 为 flex 子项时，必须允许本页内部滚动，否则长内容（三套 JSON）会被裁切，只能看到第一个框 */
.profile-page {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}
.top { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.title { font-size: 16px; font-weight: 700; }
.subtitle { font-size: 12px; color: var(--muted); }
.panel { border: 1px solid var(--border); border-radius: 10px; background: var(--surface); padding: 12px; }
.field { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--muted); }
.row { display: flex; gap: 8px; align-items: center; }
.inp { border: 1px solid var(--border); border-radius: 8px; padding: 7px 9px; background: #fff; font-size: 12px; }
.btn { border: 1px solid var(--border); background: var(--surface); border-radius: 8px; padding: 7px 10px; font-size: 12px; cursor: pointer; }
.btn.primary { background: var(--accent); color: #fff; border-color: color-mix(in srgb, var(--accent) 40%, transparent); }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.err { margin: 0; padding: 8px 10px; border-radius: 8px; background: color-mix(in srgb, #fecaca 30%, transparent); color: #b91c1c; font-size: 12px; }
.list { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.list li { display: flex; justify-content: space-between; align-items: center; border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; background: #fff; }
.list li.active { border-color: color-mix(in srgb, var(--accent) 40%, transparent); background: var(--accent-soft); }
.list li.selected { box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 30%, transparent); cursor: pointer; }
.list li:not(.selected):hover { cursor: pointer; border-color: color-mix(in srgb, var(--accent) 25%, transparent); }
.tag { font-size: 10px; border: 1px solid var(--border); border-radius: 999px; padding: 1px 6px; color: var(--muted); }
.tag-edit { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 40%, transparent); }
.sec-title { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; }
.sec-title .title { font-size: 13px; font-weight: 700; }
.sec-title .subtitle { font-size: 11.5px; color: var(--muted); }

.sys-default { margin: 6px 0 10px; border-top: 1px dashed var(--border); padding-top: 8px; }
.sys-default-sum { cursor: pointer; color: var(--muted); font-size: 12px; font-weight: 600; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.sys-default-body { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 8px; }
.sys-col { border: 1px solid var(--border); border-radius: 10px; background: #fff; padding: 8px 10px; min-width: 0; }
.sys-title { font-size: 11px; font-weight: 700; color: var(--text); margin-bottom: 6px; }
.sys-json { margin: 0; padding: 8px; border-radius: 8px; border: 1px dashed var(--border); background: #0b1220; color: #e2e8f0; font-size: 11px; overflow: auto; max-height: 240px; }
.small { font-size: 11px; }

.json-editor-section { margin-top: 4px; }
.json-section-hint { margin-bottom: 10px; line-height: 1.5; }
.json-section-hint strong { color: var(--text); font-weight: 600; }

.json-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

@media (min-width: 1100px) {
  .json-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    align-items: start;
  }
}

.json-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  background: color-mix(in srgb, var(--surface) 92%, #fff);
  min-width: 0;
}

.field.full { min-width: 0; width: 100%; }

.json-card-title {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
}

.json-card-sub {
  display: block;
  margin-bottom: 6px;
}

.ta {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px;
  background: #fbfdff;
  font-size: 12px;
  outline: none;
  resize: vertical;
  min-height: 140px;
}
.ta:focus { border-color: color-mix(in srgb, var(--accent) 35%, transparent); box-shadow: 0 0 0 3px var(--accent-soft); }
</style>
