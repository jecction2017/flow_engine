<template>
  <div class="dict-page">
    <header class="top">
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
      <div class="actions">
        <label class="profile-row">
          <span>Profile</span>
          <select v-model="selectedProfile" class="inp-mini" :disabled="loading" @change="reloadProfile">
            <option v-for="p in profiles" :key="p" :value="p">{{ p }}</option>
          </select>
        </label>
        <button type="button" class="btn ghost" :disabled="loading" @click="reload">刷新</button>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="hint-bar">
      模块文件按 dot 命名展开为字典树路径，如 <code class="mono">middleware.kafka</code> 对应
      <code class="mono">$.global.dictionary.middleware.kafka</code>。运行时 <code class="mono">dict_get()</code>
      与上下文快照读取同一份 resolved dictionary。
    </div>

    <div class="body">
      <aside class="left">
        <div class="search-box">
          <input
            v-model="searchQuery"
            class="search-input mono"
            type="text"
            placeholder="搜索模块ID或内容..."
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
          <span>base 命中 {{ filteredBaseModules.length }}</span>
          <span>profile 命中 {{ filteredProfileModules.length }}</span>
        </div>
        <div class="section-title">
          <span>Base Modules</span>
          <button type="button" class="link" @click="startNew('base')">新增</button>
        </div>
        <button
          v-for="m in filteredBaseModules"
          :key="`base:${m.module_id}`"
          type="button"
          class="module-btn"
          :class="{ active: selected?.layer === 'base' && selected.module_id === m.module_id }"
          @click="selectModule('base', m.module_id)"
        >
          <span class="mono">{{ m.module_id }}</span>
          <span v-if="m.module_id === 'core'" class="module-lock" title="核心模块（固定）" aria-label="core-locked">🔒</span>
        </button>
        <p v-if="filteredBaseModules.length === 0" class="empty">未找到匹配的 base 模块。</p>

        <div class="section-title profile-title">
          <span>Profile Overrides</span>
          <button type="button" class="link" @click="startNew('profile')">新增</button>
        </div>
        <button
          v-for="m in filteredProfileModules"
          :key="`profile:${m.module_id}`"
          type="button"
          class="module-btn"
          :class="{ active: selected?.layer === 'profile' && selected.module_id === m.module_id }"
          @click="selectModule('profile', m.module_id)"
        >
          <span class="mono">{{ m.module_id }}</span>
        </button>
        <p v-if="!debouncedSearch && profileModules.length === 0" class="empty">当前 profile 暂无覆盖模块。</p>
        <p v-if="debouncedSearch && filteredProfileModules.length === 0" class="empty">未找到匹配的 profile 模块。</p>
      </aside>

      <div class="right">
        <div class="meta">
          <span class="lbl">当前模块</span>
          <select v-model="editorLayer" class="inp-mini">
            <option value="base">base</option>
            <option value="profile">profile</option>
          </select>
          <input v-model="editorModuleId" class="inp-mini mono module-input" placeholder="app.feature" />
          <button type="button" class="btn primary" :disabled="saving || !editorModuleId.trim()" @click="saveModule">
            {{ saving ? "保存中…" : "保存模块" }}
          </button>
          <button
            type="button"
            class="btn ghost danger"
            :disabled="loading || !selected || (selected.layer === 'base' && selected.module_id === 'core')"
            @click="removeModule"
          >
            删除
          </button>
        </div>
        <CodeEditor v-model="editorYaml" language="yaml" :height="280" />

        <div class="preview-head">
          <span class="lbl">Resolved Preview</span>
          <span v-if="resolved" class="mono hash">{{ resolved.resolved_hash }}</span>
        </div>
        <CodeEditor v-model="resolvedText" language="json" :height="280" read-only />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CodeEditor from "@/components/CodeEditor.vue";
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

const dictDir = ref("");
const profiles = ref<string[]>(["default"]);
const selectedProfile = ref("default");
const baseModules = ref<DictModuleInfo[]>([]);
const profileModules = ref<DictModuleInfo[]>([]);
const resolved = ref<DictResolveResponse | null>(null);
const selected = ref<{ layer: DictLayer; module_id: string } | null>(null);
const editorLayer = ref<DictLayer>("base");
const editorModuleId = ref("");
const editorYaml = ref("{}\n");
const loading = ref(false);
const saving = ref(false);
const error = ref("");
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

const resolvedText = computed({
  get: () => (resolved.value ? JSON.stringify(resolved.value.resolved_dictionary, null, 2) : "{}"),
  set: () => {},
});

async function reload() {
  error.value = "";
  loading.value = true;
  try {
    const summary = await fetchDictSummary();
    dictDir.value = summary.dict_dir;
    profiles.value = summary.profiles.length ? summary.profiles : ["default"];
    if (!profiles.value.includes(selectedProfile.value)) selectedProfile.value = profiles.value[0] ?? "default";
    await reloadProfile();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

async function reloadProfile() {
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
  if (!selected.value && base.modules.length) {
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
  try {
    const mod = await fetchDictModule(layer, moduleId, layer === "profile" ? selectedProfile.value : undefined);
    selected.value = { layer, module_id: moduleId };
    editorLayer.value = layer;
    editorModuleId.value = moduleId;
    editorYaml.value = mod.yaml || "{}\n";
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

function startNew(layer: DictLayer) {
  selected.value = null;
  editorLayer.value = layer;
  editorModuleId.value = "";
  editorYaml.value = "{}\n";
}

async function saveModule() {
  const moduleId = editorModuleId.value.trim();
  if (!moduleId) return;
  saving.value = true;
  error.value = "";
  try {
    await saveDictModule(
      editorLayer.value,
      moduleId,
      editorYaml.value,
      editorLayer.value === "profile" ? selectedProfile.value : undefined,
    );
    selected.value = { layer: editorLayer.value, module_id: moduleId };
    moduleContentCache.value = {};
    modulePathHintsCache.value = {};
    await reloadProfile();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}

async function removeModule() {
  if (!selected.value) return;
  if (!confirm(`删除 ${selected.value.layer}:${selected.value.module_id}？`)) return;
  error.value = "";
  loading.value = true;
  try {
    await deleteDictModule(
      selected.value.layer,
      selected.value.module_id,
      selected.value.layer === "profile" ? selectedProfile.value : undefined,
    );
    selected.value = null;
    editorModuleId.value = "";
    editorYaml.value = "{}\n";
    moduleContentCache.value = {};
    modulePathHintsCache.value = {};
    await reloadProfile();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
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
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 86%, transparent);
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

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.profile-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
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

.module-btn {
  width: 100%;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.module-btn:hover {
  background: color-mix(in srgb, var(--accent-soft) 50%, transparent);
}

.module-btn.active {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: var(--accent-soft);
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
  padding: 12px 16px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
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

.meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.module-input {
  min-width: 220px;
}

.preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.hash {
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--muted);
  font-size: 11px;
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
}
</style>
