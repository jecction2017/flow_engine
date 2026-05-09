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
          <div class="title">系统能力策略</div>
          <div class="subtitle">
            环境级 CapabilityRule，优先级介于「部署/批次显式策略」与 RunMode 内置默认之间。
            修改后对所有使用本环境的部署 / 试运行 / 测试批次 / 调试入口立即生效。
          </div>
        </div>
        <div class="row">
          <select v-model="policyProfile" class="inp mono" @change="loadPolicyFor(policyProfile)">
            <option v-for="p in profiles" :key="p" :value="p">{{ p }}</option>
          </select>
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
      <CapabilityRulesEditor v-model="policyRules" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import {
  createProfile,
  fetchProfileConfig,
  fetchProfileSystemPolicy,
  saveDefaultProfile,
  saveProfileSystemPolicy,
} from "@/api/profiles";
import CapabilityRulesEditor from "@/components/CapabilityRulesEditor.vue";
import type { CapabilityRule } from "@/types/flow";

const profiles = ref<string[]>(["default"]);
const defaultProfile = ref("default");
const newProfile = ref("");
const loading = ref(false);
const savingDefault = ref(false);
const savingCreate = ref(false);
const error = ref("");

const policyProfile = ref<string>("");
const policyRules = ref<CapabilityRule[]>([]);
const savingPolicy = ref(false);

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
    policyRules.value = (res.system_capability_policy || []) as unknown as CapabilityRule[];
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function savePolicy() {
  if (!policyProfile.value) return;
  savingPolicy.value = true;
  error.value = "";
  try {
    const payload = policyRules.value.map((r) => ({ ...r })) as Record<string, unknown>[];
    const res = await saveProfileSystemPolicy(policyProfile.value, payload);
    policyRules.value = (res.system_capability_policy || []) as unknown as CapabilityRule[];
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    savingPolicy.value = false;
  }
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
.profile-page { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
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
</style>
