<template>
  <div class="cap">
    <header class="top">
      <div class="brand">
        <span class="logo">◇</span>
        <div>
          <div class="title">能力与脚本</div>
          <div class="subtitle">Python 内置函数 · 包内 Starlark 模块 · 自定义脚本</div>
        </div>
      </div>
      <nav class="segments" aria-label="主分区">
        <button
          type="button"
          class="seg"
          :class="{ active: activeSegment === 'python' }"
          @click="setSegment('python')"
        >
          <span class="seg-badge py">Py</span>
          Python 内置
        </button>
        <button
          type="button"
          class="seg"
          :class="{ active: activeSegment === 'internal' }"
          @click="setSegment('internal')"
        >
          <span class="seg-badge int">内置</span>
          Starlark 内置
        </button>
        <button
          type="button"
          class="seg"
          :class="{ active: activeSegment === 'user' }"
          @click="setSegment('user')"
        >
          <span class="seg-badge usr">自定义</span>
          用户脚本
        </button>
      </nav>
      <div class="actions">
        <button type="button" class="btn ghost" :disabled="loading" @click="refreshAll">刷新</button>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <div v-if="moduleDialogOpen" class="confirm-mask" @click.self="closeModuleDialog">
      <form class="confirm-dialog" role="dialog" aria-modal="true" aria-label="添加模块" @submit.prevent="confirmAddModule">
        <div class="confirm-title">添加模块</div>
        <p class="confirm-text muted">模块对应路径第一段，脚本保存在 <code class="mono">模块/名称.star</code> 下。</p>
        <label class="form-lbl" for="new-module-name">模块名</label>
        <input
          id="new-module-name"
          v-model="newModuleName"
          class="inp mono"
          placeholder="default"
          spellcheck="false"
          autocomplete="off"
        />
        <p v-if="newModuleError" class="field-err">{{ newModuleError }}</p>
        <div class="confirm-actions">
          <button type="button" class="btn ghost" @click="closeModuleDialog">取消</button>
          <button type="submit" class="btn primary">添加</button>
        </div>
      </form>
    </div>

    <!-- Python 内置 -->
    <div v-show="activeSegment === 'python'" class="body">
      <aside class="side">
        <label class="sr-only" for="py-search">搜索模块或函数</label>
        <input
          id="py-search"
          v-model="pythonSearch"
          type="search"
          class="search-inp"
          placeholder="搜索模块、函数名、说明…"
          autocomplete="off"
        />
        <div class="mod-list">
          <div v-for="g in filteredPythonGroups" :key="g.module" class="mod-block">
            <button
              type="button"
              class="mod-head"
              :class="{ open: expandedModules.has(g.module) }"
              @click="toggleModule(g.module)"
            >
              <span class="chev">{{ expandedModules.has(g.module) ? "▼" : "▶" }}</span>
              <span class="mod-name mono">{{ g.module }}</span>
              <span class="mod-count">{{ g.functions.length }}</span>
            </button>
            <ul v-show="expandedModules.has(g.module)" class="fn-list">
              <li
                v-for="f in g.functions"
                :key="f.id"
                class="fn-item"
                :class="{ active: selectedPythonFn?.id === f.id }"
                role="button"
                tabindex="0"
                @click="selectPythonFn(f)"
                @keydown.enter="selectPythonFn(f)"
              >
                <span class="mono fn-name">{{ f.starlark_name }}</span>
                <span class="fn-sum">{{ f.summary }}</span>
              </li>
            </ul>
          </div>
        </div>
        <p v-if="filteredPythonGroups.length === 0" class="empty-hint">无匹配项，请调整搜索词。</p>
      </aside>
      <main class="main-detail">
        <div v-if="!selectedPythonFn" class="placeholder">
          <p>从左侧选择函数，查看参数说明与调用示例。</p>
          <p class="muted">Python 内置由注册表提供；任务脚本中可直接调用函数名，无需 <code>load</code>。</p>
        </div>
        <article v-else class="detail-card">
          <header class="detail-card-head">
            <h2 class="detail-title mono">{{ selectedPythonFn.starlark_name }}</h2>
            <span class="chip chip-mod">{{ pythonModuleKey(selectedPythonFn) }}</span>
          </header>
          <p class="detail-desc">{{ selectedPythonFn.summary }}</p>
          <section class="detail-sec">
            <h3>参数</h3>
            <table class="sig-table">
              <thead>
                <tr>
                  <th>名称</th>
                  <th>类型</th>
                  <th>必填</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in selectedPythonFn.signature" :key="p.name">
                  <td class="mono">{{ p.name }}</td>
                  <td>{{ p.type }}</td>
                  <td>{{ p.required !== false ? "是" : "否" }}</td>
                </tr>
                <tr v-if="!selectedPythonFn.signature.length">
                  <td colspan="3" class="muted">无参数</td>
                </tr>
              </tbody>
            </table>
          </section>
          <section class="detail-sec">
            <h3>返回值</h3>
            <p class="mono ret">{{ selectedPythonFn.returns }}</p>
          </section>
          <section v-if="selectedPythonFn.side_effects" class="detail-sec">
            <h3>副作用</h3>
            <p>{{ selectedPythonFn.side_effects }}</p>
          </section>
          <section class="detail-sec">
            <h3>调用示例</h3>
            <div class="code-row">
              <pre class="code-block mono">{{ pythonExampleCall }}</pre>
              <button type="button" class="btn ghost sm" @click="copyExample">复制</button>
            </div>
          </section>
          <p class="id-ref mono muted">id: {{ selectedPythonFn.id }}</p>
        </article>
      </main>
    </div>

    <!-- Starlark 内置 -->
    <div v-show="activeSegment === 'internal'" class="body">
      <aside class="side">
        <label class="sr-only" for="int-search">搜索模块或脚本</label>
        <input
          id="int-search"
          v-model="internalSearch"
          type="search"
          class="search-inp"
          placeholder="搜索模块、脚本名、说明、导出符号…"
          autocomplete="off"
        />
        <div class="mod-list">
          <div v-for="g in filteredInternalGroups" :key="g.module" class="mod-block">
            <button
              type="button"
              class="mod-head"
              :class="{ open: expandedInternalModules.has(g.module) }"
              @click="toggleInternalModule(g.module)"
            >
              <span class="chev">{{ expandedInternalModules.has(g.module) ? "▼" : "▶" }}</span>
              <span class="mod-name mono">{{ g.module }}</span>
              <span class="mod-count">{{ g.scripts.length }}</span>
            </button>
            <ul v-show="expandedInternalModules.has(g.module)" class="fn-list">
              <li
                v-for="s in g.scripts"
                :key="s.uri"
                class="fn-item"
                :class="{ active: selectedInternalUri === s.uri }"
                role="button"
                tabindex="0"
                @click="selectInternal(s)"
                @keydown.enter="selectInternal(s)"
              >
                <span class="mono fn-name">{{ internalScriptName(s) }}</span>
                <span class="fn-sum">{{ s.summary }}</span>
              </li>
            </ul>
          </div>
        </div>
        <p v-if="filteredInternalGroups.length === 0" class="empty-hint">无匹配项，请调整搜索词。</p>
      </aside>
      <main class="main-detail">
        <div v-if="!selectedInternal" class="placeholder">
          <p>从左侧选择模块与脚本，查看 <code>load</code> 写法与源码。</p>
          <p class="muted">包内脚本为只读；在任务中通过 <code class="mono">load("internal://模块/脚本.star", …)</code> 引入。</p>
        </div>
        <article v-else class="detail-card detail-card--wide">
          <header class="detail-card-head">
            <h2 class="detail-title mono">{{ internalScriptName(selectedInternal) }}</h2>
            <span class="chip chip-mod">{{ internalModuleKey(selectedInternal) }}</span>
          </header>
          <p class="detail-desc">{{ selectedInternal.summary }}</p>
          <section class="detail-sec">
            <h3>引入</h3>
            <div class="code-row">
              <pre class="code-block mono">{{ internalLoadExample }}</pre>
              <button type="button" class="btn ghost sm" @click="copyInternalLoad">复制</button>
            </div>
          </section>
          <section class="detail-sec">
            <h3>导出符号</h3>
            <p v-if="!selectedInternal.exports.length" class="muted">无</p>
            <span v-for="ex in selectedInternal.exports" :key="ex" class="chip chip-ex">{{ ex }}</span>
          </section>
          <section class="script-card script-card--dark script-card-readonly">
            <div class="script-sec-head">
              <span class="script-sec-title">源码（只读）</span>
              <span v-if="internalLoading" class="muted loading-hint">加载中…</span>
            </div>
            <div class="script-body">
              <CodeEditor
                :model-value="internalReadonlyContent"
                :read-only="true"
                fill
                appearance="code-dark"
                language="python"
                :registry="registry"
              />
            </div>
          </section>
          <p class="id-ref mono muted">id: {{ selectedInternal.uri }}</p>
        </article>
      </main>
    </div>

    <!-- 用户脚本 -->
    <div v-show="activeSegment === 'user'" class="body body-user">
      <aside class="side user-nav">
        <div class="side-head">
          <span class="side-title">脚本列表</span>
          <span class="muted small">{{ userScriptCount }} 个</span>
        </div>

        <div class="side-block">
          <button type="button" class="btn ghost sm full" @click="openModuleDialog">+ 添加模块</button>
        </div>
        <label class="sr-only" for="user-search">搜索模块或脚本</label>
        <input
          id="user-search"
          v-model="userSearch"
          type="search"
          class="search-inp"
          placeholder="搜索模块、脚本名…"
          autocomplete="off"
        />
        <div class="section-title">
          <span>模块与脚本</span>
        </div>

        <div class="mod-list user-mod-list">
          <div v-for="g in filteredUserGroups" :key="g.module" class="mod-block">
            <div class="mod-row">
              <button
                type="button"
                class="mod-head"
                :class="{ open: expandedUserModules.has(g.module) }"
                @click="toggleUserModule(g.module)"
              >
                <span class="chev">{{ expandedUserModules.has(g.module) ? "▼" : "▶" }}</span>
                <span class="mod-name mono">{{ g.module }}</span>
                <span class="mod-count">{{ g.scripts.length + (userDraftModule === g.module ? 1 : 0) }}</span>
              </button>
              <button
                type="button"
                class="mod-add-btn"
                title="在此模块下添加脚本"
                aria-label="添加脚本"
                @click.stop="startNewUserScript(g.module)"
              >
                +
              </button>
            </div>
            <ul v-show="expandedUserModules.has(g.module)" class="fn-list">
              <li v-if="userDraftModule === g.module" class="fn-item active draft-item">
                <span class="mono fn-name">新建脚本…</span>
                <span class="fn-sum">未保存</span>
              </li>
              <li
                v-for="p in g.scripts"
                :key="p"
                class="fn-item"
                :class="{ active: !userDraftModule && scriptPath === p }"
                role="button"
                tabindex="0"
                @click="selectUserScript(g.module, p)"
                @keydown.enter="selectUserScript(g.module, p)"
              >
                <span class="mono fn-name">{{ userScriptFileName(p) }}</span>
              </li>
              <li v-if="!g.scripts.length && userDraftModule !== g.module" class="fn-empty muted">暂无脚本</li>
            </ul>
          </div>
        </div>
        <p v-if="filteredUserGroups.length === 0" class="empty-hint">无匹配项；请先添加模块。</p>
      </aside>
      <main class="main-detail user-workspace">
        <div v-if="!hasUserWorkspace" class="placeholder user-placeholder">
          <p>从左侧选择脚本，或点击模块旁的 <strong>+</strong> 添加脚本。</p>
          <p class="muted">路径 <code class="mono">模块/名称.star</code> · id <code class="mono">user://…</code></p>
        </div>
        <article v-else class="user-panel">
          <header class="user-focus">
            <div class="user-focus-top">
              <h2 v-if="userIsNew" class="user-focus-name">
                <span class="name-suffix-row name-suffix-row--inline">
                  <input
                    v-model="newScriptBase"
                    class="inp mono user-name-inp"
                    placeholder="hello"
                    spellcheck="false"
                    autocomplete="off"
                    aria-label="脚本名"
                  />
                  <span class="name-suffix mono">.star</span>
                </span>
              </h2>
              <h2 v-else class="user-focus-name mono">{{ userScriptFileName(scriptPath) }}</h2>
              <span class="pill" :data-mode="userIsNew ? 'new' : 'edit'">{{ userIsNew ? "新建" : "编辑" }}</span>
            </div>
            <p class="muted small user-focus-line">
              模块 <span class="mono">{{ effectiveUserModule }}</span>
              <template v-if="userScriptId">
                · id <span class="mono">{{ userScriptId }}</span>
              </template>
            </p>
            <p v-if="newScriptError" class="field-err user-focus-err">{{ newScriptError }}</p>
          </header>

          <section class="user-meta-card">
            <label class="field full" for="user-script-desc">
              <span class="field-lbl">描述</span>
              <span class="field-hint muted small">可选，便于识别脚本用途</span>
              <textarea
                id="user-script-desc"
                v-model="userScriptDescription"
                class="inp user-desc-inp"
                rows="2"
                placeholder="说明此脚本的用途…"
              />
            </label>

            <div class="user-exports-block">
              <div class="field-lbl-row">
                <span class="field-lbl">导出符号</span>
                <span class="field-hint muted small">顶层 <code>def</code> 自动提取，保存时写入</span>
              </div>
              <div v-if="liveExportFunctions.length" class="user-export-chips">
                <span v-for="ex in liveExportFunctions" :key="ex" class="chip chip-ex">{{ ex }}</span>
              </div>
              <p v-else class="muted small user-exports-empty">暂无导出（在脚本中定义 <code>def</code> 函数）</p>
            </div>
          </section>

          <section class="script-card script-card--dark script-card-editable user-script-editor">
            <div class="script-sec-head">
              <span class="script-sec-title">Starlark 源码</span>
            </div>
            <div class="script-body">
              <CodeEditor
                v-model="userScriptContent"
                :read-only="false"
                fill
                appearance="code-dark"
                language="python"
                :registry="registry"
              />
            </div>
          </section>

          <footer class="user-panel-foot">
            <button
              type="button"
              class="btn ghost sm"
              :disabled="!canDebugUserScript"
              title="调试当前脚本：配置 Profile、抑制规则并执行"
              @click="openUserDebugDrawer"
            >
              调试
            </button>
            <button
              type="button"
              class="btn primary sm"
              :disabled="!canSaveUserScript || saving"
              @click="save"
            >
              {{ saving ? "保存中…" : "保存" }}
            </button>
          </footer>
        </article>
      </main>
    </div>
    <DebugDrawer
      v-if="activeSegment === 'user' && canDebugUserScript"
      v-model:open="userDebugDrawerOpen"
      title="脚本调试"
      :pending="userDebugPending"
      @run="runUserDebug"
    >
      <DebugPanel
        ref="userDebugPanelRef"
        :user-script-path="effectiveUserScriptPath"
        :user-script-content="userScriptContent"
        embedded
        hide-toolbar
      />
    </DebugDrawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, shallowRef, watch } from "vue";
import CodeEditor from "@/components/CodeEditor.vue";
import DebugDrawer from "@/components/DebugDrawer.vue";
import DebugPanel from "@/components/DebugPanel.vue";
import {
  fetchStarlarkRegistry,
  fetchUserScripts,
  getInternalScript,
  getUserScript,
  internalRelFromRegistryPath,
  putUserScript,
  type RegistryDoc,
  type RegistryInternalModule,
  type RegistryPythonFn,
} from "@/api/starlark";
import {
  filterInternalModuleGroups,
  filterPythonModuleGroups,
  filterUserScriptGroups,
  formatPythonExampleCall,
  groupInternalModulesByModule,
  groupPythonFunctionsByModule,
  groupUserScriptsByModule,
  internalModuleKey,
  internalScriptName,
  pythonModuleKey,
  userScriptFileName,
  userScriptModuleKey,
} from "@/utils/registryGroup";
import { extractStarlarkExportFunctions } from "@/utils/starlarkExports";

const USER_SCRIPT_PATH_RE = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\/[a-zA-Z0-9][a-zA-Z0-9_./-]*\.star$/;
const USER_MODULE_RE = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/;
const USER_SCRIPT_BASE_RE = /^[a-zA-Z0-9][a-zA-Z0-9_-]*$/;

const USER_SCRIPT_DRAFT_TEMPLATE = `load("internal://lib/helpers.star", "double_int")

{"demo": double_int(21)}
`;

type Segment = "python" | "internal" | "user";

const activeSegment = ref<Segment>("python");
const registry = ref<RegistryDoc | null>(null);
const scripts = ref<string[]>([]);
const scriptsRoot = ref("");

const pythonSearch = ref("");
const expandedModules = ref<Set<string>>(new Set());
const selectedPythonFn = ref<RegistryPythonFn | null>(null);

const internalSearch = ref("");
const expandedInternalModules = ref<Set<string>>(new Set());
const selectedInternalUri = ref<string | null>(null);
const selectedInternal = ref<RegistryInternalModule | null>(null);
const internalReadonlyContent = ref("# 请选择内置脚本\n");
const internalLoading = ref(false);

const userSearch = ref("");
const expandedUserModules = ref<Set<string>>(new Set());
const extraUserModules = ref<Set<string>>(new Set());
const selectedUserModule = ref<string | null>(null);
const moduleDialogOpen = ref(false);
const userDraftModule = ref<string | null>(null);
const newModuleName = ref("");
const newModuleError = ref("");
const newScriptBase = ref("");
const newScriptError = ref("");

const scriptPath = ref("default/hello.star");
const userScriptDescription = ref("");
const userScriptContent = ref(`load("internal://lib/helpers.star", "double_int")

{"demo": double_int(21)}
`);
const userDebugDrawerOpen = ref(false);
const userDebugPanelRef = shallowRef<InstanceType<typeof DebugPanel> | null>(null);

const loading = ref(false);
const saving = ref(false);
const error = ref("");

const scriptPathValid = computed(() => USER_SCRIPT_PATH_RE.test(scriptPath.value.trim()));

const draftScriptPath = computed(() => {
  const mod = userDraftModule.value;
  const base = newScriptBase.value.trim();
  if (!mod || !USER_SCRIPT_BASE_RE.test(base)) return "";
  return `${mod}/${base}.star`;
});

const draftScriptPathValid = computed(() => USER_SCRIPT_PATH_RE.test(draftScriptPath.value));

const canSaveUserScript = computed(() => {
  if (userDraftModule.value) {
    return draftScriptPathValid.value && !scripts.value.includes(draftScriptPath.value);
  }
  return scriptPathValid.value;
});

const canDebugUserScript = computed(() =>
  userDraftModule.value ? draftScriptPathValid.value : scriptPathValid.value,
);

const effectiveUserScriptPath = computed(() =>
  userDraftModule.value ? draftScriptPath.value : scriptPath.value.trim(),
);

const userIsNew = computed(() => userDraftModule.value !== null);

const hasUserWorkspace = computed(() => userIsNew.value || scriptPathValid.value);

const effectiveUserModule = computed(
  () => userDraftModule.value ?? selectedUserModule.value ?? userScriptModuleKey(scriptPath.value.trim()) ?? "",
);

const liveExportFunctions = computed(() => extractStarlarkExportFunctions(userScriptContent.value));

const userScriptId = computed(() => {
  const p = effectiveUserScriptPath.value;
  if (!p || !USER_SCRIPT_PATH_RE.test(p)) return "";
  return `user://${p}`;
});

const userDebugPending = computed(() => {
  const inst = userDebugPanelRef.value as unknown as { pending?: { value?: boolean } | boolean } | null;
  if (!inst?.pending) return false;
  return typeof inst.pending === "object" && inst.pending !== null && "value" in inst.pending
    ? !!inst.pending.value
    : !!inst.pending;
});

function openUserDebugDrawer() {
  if (!canDebugUserScript.value) return;
  userDebugDrawerOpen.value = true;
}

function runUserDebug() {
  const inst = userDebugPanelRef.value as unknown as { run?: () => void | Promise<void> } | null;
  void inst?.run?.();
}

watch([scriptPath, userDraftModule, newScriptBase], () => {
  userDebugDrawerOpen.value = false;
  if (!userDraftModule.value) {
    const mod = userScriptModuleKey(scriptPath.value.trim());
    if (mod) selectedUserModule.value = mod;
  }
});

watch(newScriptBase, () => {
  newScriptError.value = "";
});

watch(activeSegment, (seg) => {
  if (seg !== "user") userDebugDrawerOpen.value = false;
});

const pythonGroups = computed(() => groupPythonFunctionsByModule(registry.value?.python_functions ?? []));
const filteredPythonGroups = computed(() => filterPythonModuleGroups(pythonGroups.value, pythonSearch.value));

const internalGroups = computed(() =>
  groupInternalModulesByModule(registry.value?.internal_modules ?? []),
);
const filteredInternalGroups = computed(() =>
  filterInternalModuleGroups(internalGroups.value, internalSearch.value),
);

const userGroups = computed(() => groupUserScriptsByModule(scripts.value, extraUserModules.value));
const filteredUserGroups = computed(() => filterUserScriptGroups(userGroups.value, userSearch.value));

const userScriptCount = computed(() => scripts.value.length);

const pythonExampleCall = computed(() =>
  selectedPythonFn.value ? formatPythonExampleCall(selectedPythonFn.value) : "",
);

const internalLoadExample = computed(() => {
  const m = selectedInternal.value;
  if (!m?.exports.length) return `load("${m?.uri ?? ""}")`;
  const syms = m.exports.map((s) => `"${s}"`).join(", ");
  return `load("${m.uri}", ${syms})`;
});

function setSegment(s: Segment) {
  activeSegment.value = s;
  error.value = "";
}

function toggleModule(mod: string) {
  const next = new Set(expandedModules.value);
  if (next.has(mod)) next.delete(mod);
  else next.add(mod);
  expandedModules.value = next;
}

function toggleInternalModule(mod: string) {
  const next = new Set(expandedInternalModules.value);
  if (next.has(mod)) next.delete(mod);
  else next.add(mod);
  expandedInternalModules.value = next;
}

function toggleUserModule(mod: string) {
  selectedUserModule.value = mod;
  const next = new Set(expandedUserModules.value);
  if (next.has(mod)) next.delete(mod);
  else next.add(mod);
  expandedUserModules.value = next;
}

function selectPythonFn(f: RegistryPythonFn) {
  selectedPythonFn.value = f;
}

async function selectInternal(m: RegistryInternalModule) {
  selectedInternalUri.value = m.uri;
  selectedInternal.value = m;
  internalLoading.value = true;
  error.value = "";
  const rel = internalRelFromRegistryPath(m.path);
  try {
    const f = await getInternalScript(rel);
    internalReadonlyContent.value = f.content;
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    error.value = msg;
    internalReadonlyContent.value = `# 加载失败：${msg}\n# 路径：${rel}`;
  } finally {
    internalLoading.value = false;
  }
}

function selectUserScript(mod: string, path: string) {
  userDraftModule.value = null;
  newScriptBase.value = "";
  newScriptError.value = "";
  selectedUserModule.value = mod;
  scriptPath.value = path;
  void loadFromPath();
}

function resetUserWorkspaceDraft(mod: string) {
  userDraftModule.value = mod;
  selectedUserModule.value = mod;
  scriptPath.value = "";
  newScriptBase.value = "";
  newScriptError.value = "";
  userScriptDescription.value = "";
  userScriptContent.value = USER_SCRIPT_DRAFT_TEMPLATE;
  error.value = "";
}

function openModuleDialog() {
  newModuleName.value = "";
  newModuleError.value = "";
  moduleDialogOpen.value = true;
}

function closeModuleDialog() {
  moduleDialogOpen.value = false;
  newModuleError.value = "";
}

function confirmAddModule() {
  newModuleError.value = "";
  const name = newModuleName.value.trim();
  if (!USER_MODULE_RE.test(name)) {
    newModuleError.value = "模块名：字母数字开头，可含 _、-，最长 64 字符";
    return;
  }
  const key = name.toLowerCase();
  extraUserModules.value = new Set([...extraUserModules.value, key]);
  expandedUserModules.value = new Set([...expandedUserModules.value, key]);
  selectedUserModule.value = key;
  newModuleName.value = "";
  moduleDialogOpen.value = false;
  userSearch.value = "";
}

function startNewUserScript(mod: string) {
  resetUserWorkspaceDraft(mod);
  expandedUserModules.value = new Set([...expandedUserModules.value, mod]);
}

async function copyExample() {
  if (!pythonExampleCall.value) return;
  try {
    await navigator.clipboard.writeText(pythonExampleCall.value);
  } catch {
    /* ignore */
  }
}

async function copyInternalLoad() {
  try {
    await navigator.clipboard.writeText(internalLoadExample.value);
  } catch {
    /* ignore */
  }
}

watch(filteredPythonGroups, (groups) => {
  syncExpandedModules(expandedModules, groups.map((g) => g.module));
  const sel = selectedPythonFn.value;
  if (sel && !groups.some((g) => g.functions.some((f) => f.id === sel.id))) {
    selectedPythonFn.value = groups[0]?.functions[0] ?? null;
  }
});

watch(filteredInternalGroups, (groups) => {
  syncExpandedModules(expandedInternalModules, groups.map((g) => g.module));
  const uri = selectedInternalUri.value;
  if (uri && !groups.some((g) => g.scripts.some((s) => s.uri === uri))) {
    const first = groups[0]?.scripts[0];
    if (first) void selectInternal(first);
    else {
      selectedInternalUri.value = null;
      selectedInternal.value = null;
    }
  }
});

watch(filteredUserGroups, (groups) => {
  expandedUserModules.value = new Set(groups.map((g) => g.module));
  const p = scriptPath.value.trim();
  if (p && !groups.some((g) => g.scripts.includes(p))) {
    const mod = userScriptModuleKey(p);
    if (!groups.some((g) => g.module === mod)) {
      if (groups[0]?.scripts[0]) {
        selectUserScript(groups[0].module, groups[0].scripts[0]);
      }
    }
  }
});

function syncExpandedModules(expanded: { value: Set<string> }, keys: string[]) {
  const keySet = new Set(keys);
  const next = new Set<string>();
  for (const m of expanded.value) {
    if (keySet.has(m)) next.add(m);
  }
  if (next.size === 0 && keys.length) next.add(keys[0]);
  expanded.value = next;
}

watch(registry, (reg) => {
  if (!reg?.python_functions.length) {
    selectedPythonFn.value = null;
    expandedModules.value = new Set();
    return;
  }
  const id = selectedPythonFn.value?.id;
  if (id) {
    const found = reg.python_functions.find((f) => f.id === id);
    if (found) {
      selectedPythonFn.value = found;
      expandedModules.value = new Set([pythonModuleKey(found)]);
      return;
    }
  }
  const groups = groupPythonFunctionsByModule(reg.python_functions);
  const g0 = groups[0];
  if (g0) {
    expandedModules.value = new Set([g0.module]);
    selectedPythonFn.value = g0.functions[0] ?? null;
  }

  if (!reg.internal_modules.length) {
    selectedInternal.value = null;
    selectedInternalUri.value = null;
    return;
  }
  const uri = selectedInternalUri.value;
  if (uri) {
    const found = reg.internal_modules.find((m) => m.uri === uri);
    if (found) {
      expandedInternalModules.value = new Set([internalModuleKey(found)]);
      return;
    }
  }
  const ig = groupInternalModulesByModule(reg.internal_modules);
  const i0 = ig[0]?.scripts[0];
  if (i0) {
    expandedInternalModules.value = new Set([ig[0].module]);
    void selectInternal(i0);
  }
});

async function refreshAll() {
  error.value = "";
  loading.value = true;
  try {
    const [reg, usr] = await Promise.all([fetchStarlarkRegistry(), fetchUserScripts()]);
    registry.value = reg;
    scripts.value = usr.scripts;
    scriptsRoot.value = usr.root;
    if (!scriptPath.value.trim() && usr.scripts.length) {
      scriptPath.value = usr.scripts[0] ?? "default/hello.star";
      await loadFromPath();
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

async function loadFromPath() {
  const p = scriptPath.value.trim();
  if (!USER_SCRIPT_PATH_RE.test(p)) {
    return;
  }
  selectedUserModule.value = userScriptModuleKey(p);
  expandedUserModules.value = new Set([...expandedUserModules.value, selectedUserModule.value]);
  try {
    const f = await getUserScript(p);
    userScriptContent.value = f.content;
    userScriptDescription.value = f.description ?? "";
    error.value = "";
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes("404") || msg.includes("not found")) {
      userScriptContent.value = `# 新文件: ${p}（保存后写入）\n\n{"ok": True}\n`;
      userScriptDescription.value = "";
      error.value = "";
    } else {
      error.value = msg;
    }
  }
}

async function save() {
  if (activeSegment.value !== "user") return;
  if (userDraftModule.value) {
    if (!draftScriptPathValid.value) {
      newScriptError.value = "脚本名：字母数字开头，可含 _、-";
      return;
    }
    if (scripts.value.includes(draftScriptPath.value)) {
      newScriptError.value = "该脚本已存在";
      return;
    }
  } else if (!scriptPathValid.value) {
    error.value = "路径格式无效";
    return;
  }
  const p = userDraftModule.value ? draftScriptPath.value : scriptPath.value.trim();
  saving.value = true;
  error.value = "";
  newScriptError.value = "";
  try {
    await putUserScript(p, {
      content: userScriptContent.value,
      description: userScriptDescription.value,
    });
    const usr = await fetchUserScripts();
    scripts.value = usr.scripts;
    const mod = userScriptModuleKey(p);
    extraUserModules.value = new Set([...extraUserModules.value, mod]);
    if (userDraftModule.value) {
      userDraftModule.value = null;
      newScriptBase.value = "";
      scriptPath.value = p;
    }
    selectedUserModule.value = mod;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void refreshAll().then(() => {
    void loadFromPath();
    const mod = userScriptModuleKey(scriptPath.value.trim());
    if (mod) {
      selectedUserModule.value = mod;
      expandedUserModules.value = new Set([mod]);
    }
  });
});
</script>

<style scoped>
.cap {
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
  letter-spacing: -0.02em;
  font-size: 15px;
}

.subtitle {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}

.segments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.seg {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  box-shadow: var(--shadow);
}

.seg.active {
  border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
  background: var(--accent-soft);
  font-weight: 600;
}

.seg-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.seg-badge.py {
  background: color-mix(in srgb, #fde68a 70%, #fff);
  color: #92400e;
}

.seg-badge.int {
  background: color-mix(in srgb, #c7d2fe 75%, #fff);
  color: #3730a3;
}

.seg-badge.usr {
  background: color-mix(in srgb, #a7f3d0 70%, #fff);
  color: #065f46;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
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

.btn.sm {
  padding: 4px 8px;
  font-size: 11px;
}

.btn.primary {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: var(--accent);
  color: #fff;
}

.btn.primary:disabled,
.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn.ghost:hover:not(:disabled) {
  border-color: var(--border-strong);
}

.err {
  margin: 0;
  padding: 8px 16px;
  font-size: 12px;
  color: #b91c1c;
  background: color-mix(in srgb, #fecaca 35%, transparent);
  border-bottom: 1px solid color-mix(in srgb, #f87171 30%, transparent);
}

.body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  gap: 0;
  overflow: hidden;
}

.side {
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  overflow: auto;
  padding: 12px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}

.search-inp,
.inp {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
  background: #fff;
}

.search-inp {
  margin-bottom: 10px;
}

.side-actions {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.side-act {
  flex: 1;
  min-width: 0;
}

.draft-form {
  flex-shrink: 0;
  padding: 0 14px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.draft-name-inp {
  max-width: 280px;
}

.draft-id {
  margin: 0;
  font-size: 11px;
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
  width: min(420px, 100%);
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: var(--shadow);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.confirm-title {
  font-weight: 700;
  font-size: 14px;
}

.confirm-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}

.form-lbl {
  font-size: 11px;
  color: var(--muted);
}

.name-suffix-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.name-suffix-row .inp {
  flex: 1;
  min-width: 0;
}

.name-suffix {
  font-size: 12px;
  color: var(--muted);
  flex-shrink: 0;
}

.field-err {
  margin: 0;
  font-size: 11px;
  color: #b45309;
}

.mod-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-height: 0;
}

.mod-row {
  display: flex;
  align-items: stretch;
  gap: 4px;
}

.mod-row .mod-head {
  flex: 1;
  min-width: 0;
}

.mod-add-btn {
  flex-shrink: 0;
  width: 32px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--muted);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  padding: 0;
}

.mod-add-btn:hover {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  color: var(--accent);
  background: var(--accent-soft);
}

.mod-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  cursor: pointer;
  font-size: 12px;
  text-align: left;
}

.mod-head.open,
.mod-head.active {
  border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
}

.chev {
  font-size: 10px;
  color: var(--muted);
  width: 14px;
}

.mod-name {
  flex: 1;
  font-weight: 600;
}

.mod-count {
  font-size: 10px;
  color: var(--muted);
  background: color-mix(in srgb, var(--bg) 60%, var(--surface));
  padding: 2px 6px;
  border-radius: 6px;
}

.fn-list {
  list-style: none;
  margin: 4px 0 8px 12px;
  padding: 0;
}

.fn-item {
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid transparent;
  margin-bottom: 2px;
}

.fn-item:hover {
  background: color-mix(in srgb, var(--accent-soft) 40%, transparent);
}

.fn-item.active {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  background: var(--accent-soft);
}

.fn-name {
  display: block;
  font-size: 12px;
  font-weight: 600;
}

.fn-sum {
  display: block;
  font-size: 10px;
  color: var(--muted);
  line-height: 1.3;
  margin-top: 2px;
}

.fn-empty {
  font-size: 11px;
  padding: 4px 8px;
  list-style: none;
}

.empty-hint {
  font-size: 11px;
  color: var(--muted);
  margin-top: 8px;
}

.side-foot {
  font-size: 10px;
  margin-top: 10px;
  word-break: break-all;
}

.main-detail {
  min-width: 0;
  padding: 16px 20px;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.main-detail--editor {
  padding: 12px 16px;
  overflow: hidden;
}

.placeholder {
  font-size: 13px;
  color: var(--text);
  line-height: 1.5;
}

.placeholder .muted {
  font-size: 12px;
  color: var(--muted);
  margin-top: 8px;
}

.detail-card {
  max-width: 720px;
}

.detail-card--wide {
  max-width: none;
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}

.detail-card-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.detail-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.chip {
  display: inline-block;
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--accent-soft) 80%, #fff);
  border: 1px solid var(--border);
}

.chip-mod {
  text-transform: lowercase;
}

.chip-ex {
  margin-right: 4px;
  margin-bottom: 4px;
  background: color-mix(in srgb, #e0e7ff 50%, #fff);
}

.detail-desc {
  font-size: 13px;
  margin: 12px 0 16px;
  line-height: 1.45;
}

.detail-sec h3 {
  margin: 0 0 8px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
}

.detail-sec {
  margin-bottom: 14px;
}

.sig-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.sig-table th,
.sig-table td {
  border-bottom: 1px solid var(--border);
  padding: 8px 10px;
  text-align: left;
}

.sig-table th {
  background: color-mix(in srgb, var(--surface) 90%, var(--bg));
  font-weight: 600;
}

.ret {
  margin: 0;
  padding: 8px 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.code-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px;
}

.code-block {
  margin: 0;
  flex: 1;
  min-width: 200px;
  padding: 10px 12px;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  font-size: 12px;
  overflow: auto;
}

.id-ref {
  font-size: 11px;
}

.script-card {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 260px;
  overflow: hidden;
  border-radius: 10px;
  border: 1px solid var(--border);
}

.script-card--dark {
  background: #1e222a;
  border-color: #3e4451;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 1px 2px rgba(15, 23, 42, 0.12);
}

.script-card-readonly {
  margin-top: 8px;
  min-height: 280px;
}

.script-card-editable {
  min-height: 0;
  height: 100%;
}

.script-sec-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px 14px;
  flex-wrap: wrap;
  flex-shrink: 0;
  padding: 10px 14px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.14);
}

.script-sec-head-left {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.script-sec-title {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: #f8fafc;
}

.script-card--dark .id-ref {
  color: #94a3b8;
}

.loading-hint {
  font-size: 11px;
}

.script-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0 0 4px;
}

.muted {
  color: var(--muted);
}

/* 用户脚本：左侧列表 + 右侧工作区（对齐环境配置 / 测试中心） */
.body-user {
  grid-template-columns: minmax(248px, 288px) minmax(0, 1fr);
}

.small {
  font-size: 11px;
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
  margin-bottom: 12px;
}

.btn.full {
  width: 100%;
  box-sizing: border-box;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  font-weight: 700;
  color: var(--text);
  margin: 2px 0 8px;
  padding-top: 6px;
  border-top: 1px dashed var(--border);
}

.user-mod-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.fn-item.draft-item {
  border-style: dashed;
}

.fn-item.draft-item .fn-sum {
  color: color-mix(in srgb, #10b981 55%, var(--muted));
}

.user-workspace {
  padding: 12px 14px;
  overflow: hidden;
  min-height: 0;
}

.user-placeholder {
  margin: auto;
  text-align: center;
  max-width: 360px;
}

.user-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  min-height: 0;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  padding: 14px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
}

.user-focus {
  flex-shrink: 0;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: color-mix(in srgb, var(--surface) 94%, #fbfdff);
}

.user-focus-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.user-focus-name {
  margin: 0;
  font-size: 16px;
  font-weight: 800;
  letter-spacing: -0.02em;
  min-width: 0;
  flex: 1;
}

.user-focus-line {
  margin: 6px 0 0;
  line-height: 1.45;
}

.user-focus-err {
  margin: 8px 0 0;
}

.pill {
  font-size: 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 8px;
  color: var(--muted);
  background: #fbfdff;
  flex-shrink: 0;
}

.pill[data-mode="new"] {
  border-color: color-mix(in srgb, #10b981 40%, var(--border));
  background: color-mix(in srgb, #d1fae5 50%, #fbfdff);
  color: #065f46;
}

.pill[data-mode="edit"] {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  background: var(--accent-soft);
  color: var(--accent);
}

.name-suffix-row--inline {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
}

.user-name-inp {
  width: min(220px, 100%);
  min-width: 120px;
}

.user-meta-card {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  background: color-mix(in srgb, var(--surface) 88%, #fbfdff);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field.full {
  min-width: 0;
}

.field-lbl {
  font-size: 11px;
  font-weight: 700;
  color: var(--text);
}

.field-hint {
  line-height: 1.35;
}

.field-lbl-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px 10px;
}

.user-desc-inp {
  resize: vertical;
  min-height: 52px;
  max-height: 120px;
}

.user-exports-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
}

.user-export-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.user-exports-empty {
  margin: 0;
}

.user-script-editor {
  flex: 1 1 auto;
  min-height: 220px;
}

.user-panel-foot {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 2px;
}

.inp:focus,
.user-desc-inp:focus {
  outline: none;
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

@media (max-width: 900px) {
  .body {
    grid-template-columns: 1fr;
  }
  .body-user {
    grid-template-columns: 1fr;
  }
  .side {
    border-right: none;
    border-bottom: 1px solid var(--border);
    max-height: 38vh;
  }
  .user-nav {
    max-height: 38vh;
  }
}
</style>
