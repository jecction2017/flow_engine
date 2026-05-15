<template>
  <div class="dict-page">
    <header class="top">
      <div class="top-primary">
      <div class="brand">
        <span class="logo">◇</span>
        <div>
          <div class="title">数据字典</div>
          <div class="subtitle">
            <span v-if="dictDir" class="mono dir" :title="dictDir">{{ dictDir }}</span>
            <span v-else class="muted">加载中…</span>
          </div>
        </div>
      </div>
      <label class="env-block">
        <span class="env-label">当前环境</span>
        <select
          v-model="selectedProfile"
          class="inp-mini env-select mono"
          :disabled="loading"
          @change="onProfileChange"
        >
          <option v-for="p in profiles" :key="p" :value="p">{{ p }}</option>
        </select>
      </label>
      </div>
      <nav class="top-nav" aria-label="数据字典功能">
        <button
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === 'modules' }"
          @click="activeTab = 'modules'"
        >
          字典模块
        </button>
        <button
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === 'secrets' }"
          @click="activeTab = 'secrets'"
        >
          密钥管理
        </button>
      </nav>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <div v-if="activeTab === 'modules'" class="hint-bar">
      模块以点分 ID 挂载到字典树；环境覆盖会深度合并到基础模块之上。敏感项写
      <code class="mono">secret://密钥名</code>（YAML 中无需引号）。
      <code class="mono">dict_get()</code> 在脚本中取得引用字符串，明文须在 Python 集成模块内显式解密。
    </div>
    <div v-else class="hint-bar">
      密钥按环境隔离存储；在字典 YAML 中用 <code class="mono">secret://密钥名</code> 引用。
      加密依赖服务端 <code class="mono">FLOW_SECRET_MASTER_KEY</code>；页面不提供解密，避免明文经接口传出。
    </div>

    <SecretManagerPanel
      v-if="activeTab === 'secrets'"
      :key="selectedProfile"
      :profile="selectedProfile"
      @error="onSecretError"
    />

    <div v-if="confirmOpen" class="confirm-mask" @click.self="closeConfirmDialog">
      <div class="confirm-dialog" role="dialog" aria-modal="true" aria-label="删除模块">
        <div class="confirm-title">删除模块</div>
        <p class="confirm-text">{{ confirmText }}</p>
        <div class="confirm-actions">
          <button type="button" class="btn ghost" @click="closeConfirmDialog">取消</button>
          <button type="button" class="btn ghost danger" :disabled="deletingModule" @click="confirmRemoveModule">
            {{ deletingModule ? "删除中…" : "确认删除" }}
          </button>
        </div>
      </div>
    </div>

    <div v-show="activeTab === 'modules'" class="body">
      <aside class="left">
        <div class="search-box">
          <input
            v-model="searchQuery"
            class="search-input mono"
            type="text"
            placeholder="搜索模块 ID 或 YAML 内容…"
          />
          <button
            v-if="searchQuery.trim()"
            type="button"
            class="search-clear"
            title="清空搜索"
            @click="searchQuery = ''"
          >
            ×
          </button>
        </div>
        <div class="search-meta">
          <span>基础模块 {{ filteredBaseModules.length }}</span>
          <span>环境覆盖 {{ filteredProfileModules.length }}</span>
        </div>
        <div class="section-title">
          <span>基础模块</span>
          <button type="button" class="link" @click="startNew('base')">新增</button>
        </div>
        <div
          v-for="m in filteredBaseModules"
          :key="`base:${m.module_id}`"
          class="module-item"
          :class="{ active: selected?.layer === 'base' && selected.module_id === m.module_id }"
          @click="selectModule('base', m.module_id)"
        >
          <span class="mono module-name">{{ m.module_id }}</span>
          <div class="module-item-tail">
            <span v-if="m.module_id === 'core'" class="module-lock" title="系统内置模块，不可删除" aria-label="core-locked">🔒</span>
            <button
              v-else
              type="button"
              class="delete-module-btn"
              :class="{ 'is-revealed': deletingModuleKey === moduleItemKey('base', m.module_id) }"
              :disabled="loading || !!deletingModuleKey"
              aria-label="删除模块"
              @click.stop="requestRemoveModule('base', m.module_id)"
            >
              {{ deletingModuleKey === moduleItemKey('base', m.module_id) ? "…" : "删除" }}
            </button>
          </div>
        </div>
        <p v-if="filteredBaseModules.length === 0" class="empty">未找到匹配的基础模块。</p>

        <div class="section-title profile-title">
          <span>环境覆盖</span>
          <button type="button" class="link" @click="startNew('profile')">新增</button>
        </div>
        <div
          v-for="m in filteredProfileModules"
          :key="`profile:${m.module_id}`"
          class="module-item"
          :class="{ active: selected?.layer === 'profile' && selected.module_id === m.module_id }"
          @click="selectModule('profile', m.module_id)"
        >
          <span class="mono module-name">{{ m.module_id }}</span>
          <div class="module-item-tail">
            <button
              type="button"
              class="delete-module-btn"
              :class="{ 'is-revealed': deletingModuleKey === moduleItemKey('profile', m.module_id) }"
              :disabled="loading || !!deletingModuleKey"
              aria-label="删除模块"
              @click.stop="requestRemoveModule('profile', m.module_id)"
            >
              {{ deletingModuleKey === moduleItemKey('profile', m.module_id) ? "…" : "删除" }}
            </button>
          </div>
        </div>
        <p v-if="!debouncedSearch && profileModules.length === 0" class="empty">当前环境暂无覆盖模块。</p>
        <p v-if="debouncedSearch && filteredProfileModules.length === 0" class="empty">未找到匹配的环境覆盖模块。</p>
      </aside>

      <div class="right">
        <template v-if="isEditing">
          <header class="module-focus">
            <span class="layer-pill">{{ layerLabel(displayLayer) }}</span>
            <label class="module-id-field">
              <span class="lbl">模块 ID</span>
              <input
                v-model="editorModuleId"
                class="inp-mini mono module-id-inp"
                :readonly="!creatingNew"
                :placeholder="creatingNew ? '例如 app.http' : undefined"
                spellcheck="false"
              />
            </label>
            <button
              type="button"
              class="btn primary"
              :disabled="saving || (creatingNew && !editorModuleId.trim())"
              @click="saveModule"
            >
              {{ saving ? "保存中…" : "保存模块" }}
            </button>
          </header>
          <div class="editors-row">
          <div class="editor-pane">
            <div class="pane-head">
              <span class="lbl">模块配置（YAML）</span>
            </div>
            <CodeEditor v-model="editorYaml" language="yaml" fill />
          </div>
          <div class="editor-pane preview-pane">
            <div class="pane-head">
              <span class="lbl">合并结果（只读）</span>
            </div>
            <CodeEditor v-model="resolvedText" language="yaml" fill read-only />
          </div>
          </div>
        </template>
        <p v-else class="right-empty">从左侧选择模块，或点击「新增」创建。</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { stringify } from "yaml";
import CodeEditor from "@/components/CodeEditor.vue";
import SecretManagerPanel from "@/components/SecretManagerPanel.vue";
import {
  deleteDictModule,
  fetchDictModule,
  fetchDictModules,
  fetchDictResolved,
  fetchDictSummary,
  saveDictModule,
  type DictLayer,
  type DictModuleInfo,
  type DictResolveResponse,
} from "@/api/dict";

/** 新建/空模块编辑区占位（服务端仍解析为空映射，不在 UI 展示 `{}`）。 */
const EMPTY_MODULE_YAML =
  "# 根须为映射（对象），在此填写本模块配置项，例如：\n# timeout_sec: 30\n";

function isEmptyModuleYaml(yaml: string): boolean {
  const t = yaml.trim();
  return t === "" || t === "{}";
}

function moduleYamlForEditor(yaml: string | undefined | null): string {
  const raw = yaml ?? "";
  if (isEmptyModuleYaml(raw)) return EMPTY_MODULE_YAML;
  return raw.endsWith("\n") ? raw : `${raw}\n`;
}

const activeTab = ref<"modules" | "secrets">("modules");
const dictDir = ref("");
const profiles = ref<string[]>(["default"]);
const selectedProfile = ref("default");
const baseModules = ref<DictModuleInfo[]>([]);
const profileModules = ref<DictModuleInfo[]>([]);
const resolved = ref<DictResolveResponse | null>(null);
const selected = ref<{ layer: DictLayer; module_id: string } | null>(null);
const editorLayer = ref<DictLayer>("base");
const editorModuleId = ref("");
const editorYaml = ref(EMPTY_MODULE_YAML);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const creatingNew = ref(false);
const confirmOpen = ref(false);
const confirmText = ref("");
const deletingModule = ref(false);
const deletingModuleKey = ref<string | null>(null);
const pendingDelete = ref<{ layer: DictLayer; module_id: string } | null>(null);

function onSecretError(msg: string) {
  error.value = msg;
}
const searchQuery = ref("");
const debouncedSearch = ref("");
const moduleContentCache = ref<Record<string, string>>({});
const modulePathHintsCache = ref<Record<string, string>>({});

let searchTimer: ReturnType<typeof setTimeout> | null = null;
watch(
  () => searchQuery.value,
  (q) => {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      debouncedSearch.value = q.trim().toLowerCase();
    }, 160);
  },
);

watch(
  () => debouncedSearch.value,
  () => {
    void hydrateSearchCache();
  },
);
const sortedBaseModules = computed(() => {
  const arr = [...baseModules.value];
  arr.sort((a, b) => {
    if (a.module_id === "core" && b.module_id !== "core") return -1;
    if (a.module_id !== "core" && b.module_id === "core") return 1;
    return a.module_id.localeCompare(b.module_id);
  });
  return arr;
});
const filteredBaseModules = computed(() => filterModules(sortedBaseModules.value, "base"));
const filteredProfileModules = computed(() => filterModules(profileModules.value, "profile"));

const isEditing = computed(() => creatingNew.value || selected.value !== null);
const displayLayer = computed<DictLayer>(() => selected.value?.layer ?? editorLayer.value);

const resolvedText = computed({
  get: () => {
    if (!resolved.value) return "{}\n";
    try {
      return stringify(resolved.value.resolved_dictionary, { lineWidth: 0 });
    } catch {
      return "{}\n";
    }
  },
  set: () => {},
});

function layerLabel(layer: DictLayer): string {
  return layer === "base" ? "基础模块" : "环境覆盖";
}

function moduleItemKey(layer: DictLayer, moduleId: string): string {
  return `${layer}:${moduleId}`;
}

function canDeleteModule(layer: DictLayer, moduleId: string): boolean {
  return !(layer === "base" && moduleId === "core");
}

async function reload() {
  error.value = "";
  loading.value = true;
  try {
    const summary = await fetchDictSummary();
    dictDir.value = summary.dict_dir;
    profiles.value = summary.profiles.length ? summary.profiles : ["default"];
    if (!profiles.value.includes(selectedProfile.value)) selectedProfile.value = profiles.value[0] ?? "default";
    await reloadProfile(true);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function onProfileChange() {
  if (activeTab.value === "modules") {
    creatingNew.value = false;
    selected.value = null;
    void reloadProfile(false);
  }
}

async function reloadProfile(selectFirstIfNone = false) {
  const [base, prof, res] = await Promise.all([
    fetchDictModules("base"),
    fetchDictModules("profile", selectedProfile.value),
    fetchDictResolved(selectedProfile.value),
  ]);
  baseModules.value = base.modules;
  profileModules.value = prof.modules;
  resolved.value = res;
  moduleContentCache.value = {};
  modulePathHintsCache.value = {};
  await hydrateSearchCache();
  if (selectFirstIfNone && !selected.value && !creatingNew.value && base.modules.length) {
    await selectModule("base", base.modules[0].module_id);
  }
}

function moduleCacheKey(layer: DictLayer, moduleId: string): string {
  return layer === "profile" ? `${layer}:${selectedProfile.value}:${moduleId}` : `${layer}:${moduleId}`;
}

function filterModules(modules: DictModuleInfo[], layer: DictLayer): DictModuleInfo[] {
  const q = debouncedSearch.value;
  if (!q) return modules;
  return modules.filter((m) => {
    const idHit = m.module_id.toLowerCase().includes(q);
    if (idHit) return true;
    const key = moduleCacheKey(layer, m.module_id);
    const content = moduleContentCache.value[key] ?? "";
    if (content.toLowerCase().includes(q)) return true;
    // Support dot-path queries like `app.http.timeout_sec`.
    if (q.includes(".")) {
      const hints = modulePathHintsCache.value[key] ?? "";
      return hints.includes(q);
    }
    return false;
  });
}

function extractYamlPathHints(moduleId: string, yamlText: string): string {
  const out = new Set<string>();
  const base = moduleId.trim().toLowerCase();
  if (base) out.add(base);

  const lines = yamlText.split(/\r?\n/);
  const stack: Array<{ indent: number; key: string }> = [];
  for (const raw of lines) {
    const line = raw.replace(/\t/g, "  ");
    if (!line.trim() || line.trimStart().startsWith("#")) continue;
    const m = /^(\s*)([A-Za-z0-9_-]+)\s*:/.exec(line);
    if (!m) continue;
    const indent = m[1]?.length ?? 0;
    const key = (m[2] ?? "").trim().toLowerCase();
    while (stack.length && indent <= stack[stack.length - 1]!.indent) {
      stack.pop();
    }
    stack.push({ indent, key });
    const relPath = stack.map((s) => s.key).join(".");
    out.add(relPath);
    if (base) out.add(`${base}.${relPath}`);
  }
  return Array.from(out).join("\n");
}

async function hydrateSearchCache(): Promise<void> {
  const q = debouncedSearch.value;
  if (!q) return;
  const tasks: Array<Promise<void>> = [];
  for (const m of baseModules.value) {
    const key = moduleCacheKey("base", m.module_id);
    if (!(key in moduleContentCache.value)) {
      tasks.push(
        fetchDictModule("base", m.module_id)
          .then((mod) => {
            const yaml = mod.yaml || "";
            moduleContentCache.value[key] = yaml;
            modulePathHintsCache.value[key] = extractYamlPathHints(m.module_id, yaml);
          })
          .catch(() => {
            moduleContentCache.value[key] = "";
            modulePathHintsCache.value[key] = m.module_id.toLowerCase();
          }),
      );
    }
  }
  for (const m of profileModules.value) {
    const key = moduleCacheKey("profile", m.module_id);
    if (!(key in moduleContentCache.value)) {
      tasks.push(
        fetchDictModule("profile", m.module_id, selectedProfile.value)
          .then((mod) => {
            const yaml = mod.yaml || "";
            moduleContentCache.value[key] = yaml;
            modulePathHintsCache.value[key] = extractYamlPathHints(m.module_id, yaml);
          })
          .catch(() => {
            moduleContentCache.value[key] = "";
            modulePathHintsCache.value[key] = m.module_id.toLowerCase();
          }),
      );
    }
  }
  if (tasks.length) await Promise.all(tasks);
}

async function selectModule(layer: DictLayer, moduleId: string) {
  error.value = "";
  creatingNew.value = false;
  try {
    const mod = await fetchDictModule(layer, moduleId, layer === "profile" ? selectedProfile.value : undefined);
    selected.value = { layer, module_id: moduleId };
    editorLayer.value = layer;
    editorModuleId.value = moduleId;
    editorYaml.value = moduleYamlForEditor(mod.yaml);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

function startNew(layer: DictLayer) {
  selected.value = null;
  creatingNew.value = true;
  editorLayer.value = layer;
  editorModuleId.value = "";
  editorYaml.value = EMPTY_MODULE_YAML;
}

async function saveModule() {
  const layer = selected.value?.layer ?? editorLayer.value;
  const moduleId = (selected.value?.module_id ?? editorModuleId.value).trim();
  if (!moduleId) return;
  saving.value = true;
  error.value = "";
  try {
    await saveDictModule(
      layer,
      moduleId,
      editorYaml.value,
      layer === "profile" ? selectedProfile.value : undefined,
    );
    creatingNew.value = false;
    selected.value = { layer, module_id: moduleId };
    moduleContentCache.value = {};
    modulePathHintsCache.value = {};
    await reloadProfile();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}

function requestRemoveModule(layer: DictLayer, moduleId: string) {
  if (!canDeleteModule(layer, moduleId)) return;
  pendingDelete.value = { layer, module_id: moduleId };
  confirmText.value = `确定删除${layerLabel(layer)}「${moduleId}」？此操作不可恢复。`;
  confirmOpen.value = true;
}

function closeConfirmDialog() {
  if (deletingModule.value) return;
  confirmOpen.value = false;
  pendingDelete.value = null;
}

async function confirmRemoveModule() {
  const target = pendingDelete.value;
  if (!target) return;
  deletingModule.value = true;
  deletingModuleKey.value = moduleItemKey(target.layer, target.module_id);
  error.value = "";
  try {
    await deleteDictModule(
      target.layer,
      target.module_id,
      target.layer === "profile" ? selectedProfile.value : undefined,
    );
    confirmOpen.value = false;
    pendingDelete.value = null;
    if (selected.value?.layer === target.layer && selected.value.module_id === target.module_id) {
      selected.value = null;
      creatingNew.value = false;
      editorModuleId.value = "";
      editorYaml.value = EMPTY_MODULE_YAML;
    }
    moduleContentCache.value = {};
    modulePathHintsCache.value = {};
    await reloadProfile();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    deletingModule.value = false;
    deletingModuleKey.value = null;
  }
}

void reload();
</script>

<style scoped>
.dict-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: linear-gradient(180deg, #fbfcff 0%, #f6f8fc 100%);
}

.top {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 16px 0;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 86%, transparent);
}

.top-primary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
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
  font-size: 15px;
}

.subtitle {
  font-size: 11px;
  color: var(--muted);
  margin-top: 2px;
}

.dir {
  word-break: break-all;
}

.env-block {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.env-label {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

.env-select {
  min-width: 120px;
}

.top-nav {
  display: flex;
  align-items: stretch;
  gap: 4px;
  margin: 0 -16px;
  padding: 0 16px;
  border-top: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
}

.tab-btn {
  border: none;
  background: transparent;
  color: var(--muted);
  padding: 10px 16px;
  font-size: 13px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition:
    color 0.14s ease,
    border-color 0.14s ease,
    background 0.14s ease;
}

.tab-btn:hover {
  color: var(--text);
  background: color-mix(in srgb, var(--accent-soft) 35%, transparent);
}

.tab-btn.active {
  color: var(--accent);
  font-weight: 600;
  border-bottom-color: var(--accent);
  background: color-mix(in srgb, var(--accent-soft) 45%, transparent);
}

.inp-mini {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  padding: 6px 8px;
  font-size: 12px;
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
}

.hint-bar {
  margin: 0;
  padding: 8px 16px;
  font-size: 11px;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 94%, transparent);
}

.hint-bar code {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 4px;
  background: #fff8;
}

.body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 0;
}

.left {
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  overflow: auto;
  padding: 10px 12px;
}

.search-box {
  position: relative;
  margin-bottom: 6px;
}

.search-input {
  width: 100%;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 8px;
  padding: 7px 28px 7px 10px;
  font-size: 12px;
  color: var(--text);
}

.search-input:focus {
  outline: none;
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.search-clear {
  position: absolute;
  right: 7px;
  top: 50%;
  transform: translateY(-50%);
  border: 0;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0;
}

.search-meta {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 11px;
  color: var(--muted);
  margin: 0 2px 10px;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 2px 8px;
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
}

.profile-title {
  margin-top: 14px;
}

.link {
  border: 0;
  background: transparent;
  color: var(--accent);
  cursor: pointer;
  font-size: 12px;
  padding: 0;
}

.module-item {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 8px 10px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  font-size: 12px;
}

.module-item:hover {
  background: color-mix(in srgb, var(--accent-soft) 50%, transparent);
}

.module-item.active {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: var(--accent-soft);
}

.module-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.module-item-tail {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  margin-left: auto;
}

.delete-module-btn {
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

.module-item:hover .delete-module-btn,
.module-item:focus-within .delete-module-btn,
.delete-module-btn.is-revealed {
  opacity: 1;
  pointer-events: auto;
}

.delete-module-btn:hover:not(:disabled) {
  border-color: color-mix(in srgb, #dc2626 45%, var(--border));
  color: #b91c1c;
  background: #fef2f2;
}

.delete-module-btn:disabled {
  cursor: not-allowed;
}

.delete-module-btn.is-revealed:disabled {
  opacity: 1;
  pointer-events: none;
}

.module-lock {
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
  display: inline-grid;
  place-items: center;
  font-size: 11px;
  line-height: 1;
  color: var(--muted);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  border: 1px solid color-mix(in srgb, var(--border) 85%, transparent);
  border-radius: 999px;
  opacity: 0.85;
}

.right {
  min-width: 0;
  min-height: 0;
  padding: 12px 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.editors-row {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

.editor-pane {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pane-head {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.root-btn {
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
  cursor: pointer;
  margin-bottom: 8px;
}

.root-btn.active {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: var(--accent-soft);
}

.empty {
  font-size: 12px;
  color: var(--muted);
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

.module-focus {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.layer-pill {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border));
  background: var(--accent-soft);
  color: var(--accent);
}

.module-id-field {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.module-id-inp {
  width: 200px;
  max-width: min(200px, 100%);
}

.module-id-inp:read-only {
  cursor: default;
  color: var(--text);
  background: color-mix(in srgb, var(--surface) 88%, transparent);
}

.right-empty {
  margin: auto;
  text-align: center;
  font-size: 13px;
  color: var(--muted);
  padding: 24px 16px;
}

.lbl {
  font-size: 11px;
  color: var(--muted);
}

.path {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid var(--border);
}

@media (max-width: 900px) {
  .body {
    grid-template-columns: 1fr;
  }
  .left {
    border-right: none;
    border-bottom: 1px solid var(--border);
    max-height: 38vh;
  }
  .editors-row {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);
  }
}
</style>
