<template>
  <div class="cap">
    <header class="top">
      <div class="brand">
        <span class="logo">◇</span>
        <div>
          <div class="title">能力与脚本</div>
          <div class="subtitle">自定义脚本 · Python 内置函数 · 包内 Starlark 模块</div>
        </div>
      </div>
      <nav class="segments" aria-label="主分区">
        <button
          type="button"
          class="seg"
          :class="{ active: activeSegment === 'user' }"
          @click="setSegment('user')"
        >
          <span class="seg-badge usr">自定义</span>
          用户脚本
        </button>
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
      </nav>
      <div class="actions">
        <button type="button" class="btn ghost" :disabled="loading" @click="refreshAll">刷新</button>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <div v-if="deleteDialog" class="confirm-mask" @click.self="closeDeleteDialog">
      <div
        class="confirm-dialog"
        role="dialog"
        aria-modal="true"
        :aria-label="deleteDialog.type === 'module' ? '删除模块' : '删除脚本'"
      >
        <template v-if="deleteDialog.type === 'module'">
          <div class="confirm-title">删除模块？</div>
          <p class="confirm-text">
            将删除模块 <code class="mono">{{ deleteDialog.module }}</code>
            <template v-if="deleteDialog.scriptCount > 0">
              及其下 <strong>{{ deleteDialog.scriptCount }}</strong> 个脚本（软删除）。
            </template>
            <template v-else>（当前无脚本，仅从列表移除）。</template>
          </p>
        </template>
        <template v-else>
          <div class="confirm-title">删除脚本？</div>
          <p class="confirm-text">
            将删除脚本 <code class="mono">{{ userScriptFileName(deleteDialog.path) }}</code>
            （<code class="mono">{{ deleteDialog.path }}</code>）。
          </p>
        </template>
        <div class="confirm-actions">
          <button type="button" class="btn ghost" :disabled="deletingUser" @click="closeDeleteDialog">取消</button>
          <button type="button" class="btn ghost danger" :disabled="deletingUser" @click="submitDelete">
            {{ deletingUser ? "删除中…" : "删除" }}
          </button>
        </div>
      </div>
    </div>

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
        <div class="side-head side-head--row">
          <div class="side-head-main">
            <span class="side-title">模块与脚本</span>
            <span class="muted small">{{ userScriptCount }} 个脚本</span>
          </div>
          <button type="button" class="btn ghost sm" @click="openModuleDialog">+ 添加模块</button>
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
        <div class="mod-list user-mod-list">
          <div v-for="g in filteredUserGroups" :key="g.module" class="mod-block">
            <div class="mod-row" :class="{ 'is-menu-open': openUserModuleMenu === g.module }">
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
              <div class="mod-menu-wrap" @click.stop>
                <button
                  type="button"
                  class="mod-more-btn"
                  :aria-expanded="openUserModuleMenu === g.module"
                  aria-label="模块操作"
                  @click="toggleUserModuleMenu(g.module)"
                >
                  …
                </button>
                <div v-if="openUserModuleMenu === g.module" class="menu">
                  <button type="button" class="menu-item" @click="onAddScriptFromMenu(g.module)">添加脚本</button>
                  <button type="button" class="menu-item danger" @click="requestDeleteModule(g.module)">删除模块</button>
                </div>
              </div>
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
          <p>从左侧选择脚本，或通过模块 <strong>…</strong> 菜单添加脚本。</p>
          <p class="muted">路径 <code class="mono">模块/名称.star</code> · id <code class="mono">user://…</code></p>
        </div>
        <article v-else class="user-panel">
          <header class="panel-head user-panel-toolbar">
            <div class="panel-head-main user-panel-head-main">
              <template v-if="userIsNew">
                <div class="panel-head-text">
                  <span class="panel-title">新建脚本</span>
                  <p class="muted small user-panel-sub">
                    模块 <span class="mono">{{ effectiveUserModule }}</span>
                    · 保存后路径 <span class="mono">{{ effectiveUserModule }}/名称.star</span>
                  </p>
                </div>
              </template>
              <template v-else>
                <div class="detail-card-head user-edit-title">
                  <h2 class="detail-title mono">{{ userScriptFileName(scriptPath) }}</h2>
                  <span v-if="effectiveUserModule" class="chip chip-mod">{{ effectiveUserModule }}</span>
                </div>
                <p v-if="userScriptId" class="id-ref mono muted user-id-ref">id: {{ userScriptId }}</p>
              </template>
            </div>
            <div class="panel-head-actions user-panel-actions">
              <button
                type="button"
                class="btn primary sm"
                :disabled="!canSaveUserScript || saving"
                @click="save"
              >
                {{ saving ? "保存中…" : "保存" }}
              </button>
              <div class="user-ws-menu-wrap" @click.stop>
                <button
                  type="button"
                  class="btn ghost sm user-ws-more-btn"
                  :aria-expanded="openUserWorkspaceMenu"
                  aria-label="更多操作"
                  @click="toggleUserWorkspaceMenu"
                >
                  …
                </button>
                <div v-if="openUserWorkspaceMenu" class="menu">
                  <button
                    v-if="canDeleteUserScript"
                    type="button"
                    class="menu-item danger"
                    :disabled="deletingUser || saving"
                    @click="onDeleteFromWorkspaceMenu"
                  >
                    删除脚本
                  </button>
                  <p v-else class="menu-hint muted small">新建脚本保存后可删除</p>
                </div>
              </div>
            </div>
          </header>

          <div class="user-form-body">
            <label class="field full" for="user-script-name">
              <span class="field-lbl">方法名 <em class="req">*</em></span>
              <div class="name-suffix-row name-suffix-row--inline">
                <input
                  id="user-script-name"
                  v-model="activeScriptBase"
                  class="inp mono user-name-inp"
                  placeholder="hello"
                  spellcheck="false"
                  autocomplete="off"
                />
                <span class="name-suffix mono">.star</span>
              </div>
              <p v-if="scriptNameError" class="field-err">{{ scriptNameError }}</p>
            </label>

            <label class="field full" for="user-script-desc">
              <span class="field-lbl">描述</span>
              <textarea
                id="user-script-desc"
                v-model="userScriptDescription"
                class="inp user-desc-inp"
                rows="2"
                placeholder="可选：说明脚本用途…"
              />
            </label>

            <div class="field full user-exports-field">
              <span class="field-lbl">导出符号</span>
              <div v-if="userExportFunctions.length" class="user-export-chips">
                <span v-for="(ex, idx) in userExportFunctions" :key="ex" class="chip chip-ex chip-removable">
                  <span class="mono">{{ ex }}</span>
                  <button type="button" class="chip-remove" aria-label="移除" @click="removeExportSymbol(idx)">×</button>
                </span>
              </div>
              <p v-else class="muted small user-exports-empty">暂无导出符号</p>
              <div class="export-add-row">
                <input
                  v-model="newExportInput"
                  class="inp mono export-add-inp"
                  placeholder="符号名，回车添加"
                  spellcheck="false"
                  autocomplete="off"
                  @keydown.enter.prevent="addExportSymbol"
                />
                <button type="button" class="btn ghost sm" @click="addExportSymbol">添加</button>
                <button type="button" class="btn ghost sm" @click="syncExportsFromCode">从源码同步</button>
              </div>
            </div>
          </div>

          <section class="script-card script-card--dark script-card-editable user-script-editor">
            <div class="script-sec-head">
              <span class="script-sec-title">Starlark 源码</span>
              <button
                type="button"
                class="btn ghost sm script-debug-btn"
                :disabled="!canDebugUserScript"
                title="调试当前脚本：配置 Profile、抑制规则并执行"
                @click="openUserDebugDrawer"
              >
                调试
              </button>
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
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";
import CodeEditor from "@/components/CodeEditor.vue";
import DebugDrawer from "@/components/DebugDrawer.vue";
import DebugPanel from "@/components/DebugPanel.vue";
import {
  deleteUserModule,
  deleteUserScript,
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
const EXPORT_SYMBOL_RE = /^[a-zA-Z_][a-zA-Z0-9_]*$/;

const USER_SCRIPT_DRAFT_TEMPLATE = `load("internal://lib/helpers.star", "double_int")

{"demo": double_int(21)}
`;

type Segment = "python" | "internal" | "user";

type DeleteDialog =
  | { type: "module"; module: string; scriptCount: number }
  | { type: "script"; path: string };

const activeSegment = ref<Segment>("user");
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
const editScriptBase = ref("");
const scriptNameError = ref("");
const userExportFunctions = ref<string[]>([]);
const newExportInput = ref("");

const openUserModuleMenu = ref<string | null>(null);
const openUserWorkspaceMenu = ref(false);
const deleteDialog = ref<DeleteDialog | null>(null);
const deletingUser = ref(false);

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

function buildUserScriptPath(mod: string, base: string): string {
  const b = base.trim();
  if (!mod || !b) return "";
  const rel = b.endsWith(".star") ? b : `${b}.star`;
  return `${mod}/${rel}`;
}

function userScriptBaseName(path: string): string {
  const file = userScriptFileName(path);
  return file.endsWith(".star") ? file.slice(0, -5) : file;
}

const activeScriptBase = computed({
  get: () => (userIsNew.value ? newScriptBase.value : editScriptBase.value),
  set: (v: string) => {
    if (userIsNew.value) newScriptBase.value = v;
    else editScriptBase.value = v;
  },
});

const targetScriptPath = computed(() => {
  const mod = effectiveUserModule.value;
  if (!mod) return "";
  return buildUserScriptPath(mod, activeScriptBase.value);
});

const targetScriptPathValid = computed(() => USER_SCRIPT_PATH_RE.test(targetScriptPath.value));

const canSaveUserScript = computed(() => {
  if (!targetScriptPathValid.value) return false;
  const target = targetScriptPath.value;
  if (userIsNew.value) return !scripts.value.includes(target);
  const current = scriptPath.value.trim();
  return target === current || !scripts.value.includes(target);
});

const canDebugUserScript = computed(() => targetScriptPathValid.value);

const effectiveUserScriptPath = computed(() =>
  userIsNew.value ? targetScriptPath.value : targetScriptPathValid.value ? targetScriptPath.value : scriptPath.value.trim(),
);

const userIsNew = computed(() => userDraftModule.value !== null);

const canDeleteUserScript = computed(
  () =>
    !userIsNew.value &&
    scriptPathValid.value &&
    scripts.value.includes(scriptPath.value.trim()),
);

const hasUserWorkspace = computed(() => userIsNew.value || scriptPathValid.value);

const effectiveUserModule = computed(
  () => userDraftModule.value ?? selectedUserModule.value ?? userScriptModuleKey(scriptPath.value.trim()) ?? "",
);

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

watch([scriptPath, userDraftModule, newScriptBase, editScriptBase], () => {
  userDebugDrawerOpen.value = false;
  if (!userDraftModule.value) {
    const mod = userScriptModuleKey(scriptPath.value.trim());
    if (mod) selectedUserModule.value = mod;
  }
});

watch(activeScriptBase, () => {
  scriptNameError.value = "";
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

function userScriptsInModule(mod: string): string[] {
  const key = mod.toLowerCase();
  return scripts.value.filter((p) => userScriptModuleKey(p).toLowerCase() === key);
}

function userModuleTenant(mod: string): string {
  const paths = userScriptsInModule(mod);
  return paths.length ? userScriptModuleKey(paths[0]) : mod;
}

function closeUserMenus() {
  openUserModuleMenu.value = null;
  openUserWorkspaceMenu.value = false;
}

function toggleUserWorkspaceMenu() {
  openUserWorkspaceMenu.value = !openUserWorkspaceMenu.value;
  if (openUserWorkspaceMenu.value) openUserModuleMenu.value = null;
}

function onDeleteFromWorkspaceMenu() {
  closeUserMenus();
  requestDeleteCurrentScript();
}

function addExportSymbol() {
  const name = newExportInput.value.trim();
  if (!name) return;
  if (!EXPORT_SYMBOL_RE.test(name)) {
    error.value = "导出符号：字母或下划线开头，仅含字母数字下划线";
    return;
  }
  if (!userExportFunctions.value.includes(name)) {
    userExportFunctions.value = [...userExportFunctions.value, name];
  }
  newExportInput.value = "";
  error.value = "";
}

function removeExportSymbol(index: number) {
  userExportFunctions.value = userExportFunctions.value.filter((_, i) => i !== index);
}

function syncExportsFromCode() {
  userExportFunctions.value = [...extractStarlarkExportFunctions(userScriptContent.value)];
}

function toggleUserModuleMenu(mod: string) {
  openUserWorkspaceMenu.value = false;
  openUserModuleMenu.value = openUserModuleMenu.value === mod ? null : mod;
}

function onAddScriptFromMenu(mod: string) {
  closeUserMenus();
  startNewUserScript(mod);
}

function requestDeleteModule(mod: string) {
  closeUserMenus();
  deleteDialog.value = { type: "module", module: mod, scriptCount: userScriptsInModule(mod).length };
}

function requestDeleteScript(path: string) {
  closeUserMenus();
  deleteDialog.value = { type: "script", path };
}

function requestDeleteCurrentScript() {
  const p = scriptPath.value.trim();
  if (!canDeleteUserScript.value) return;
  requestDeleteScript(p);
}

function closeDeleteDialog() {
  if (deletingUser.value) return;
  deleteDialog.value = null;
}

function pickFirstUserScriptAfterChange() {
  userDraftModule.value = null;
  newScriptBase.value = "";
  editScriptBase.value = "";
  scriptNameError.value = "";
  userDebugDrawerOpen.value = false;
  const groups = userGroups.value;
  const firstPath = groups[0]?.scripts[0];
  if (firstPath) {
    selectUserScript(userScriptModuleKey(firstPath), firstPath);
    return;
  }
  selectedUserModule.value = groups[0]?.module ?? null;
  scriptPath.value = "";
  userScriptDescription.value = "";
  userScriptContent.value = USER_SCRIPT_DRAFT_TEMPLATE;
  userExportFunctions.value = [];
}

async function submitDelete() {
  const d = deleteDialog.value;
  if (!d) return;
  deletingUser.value = true;
  error.value = "";
  try {
    if (d.type === "module") {
      const modKey = d.module.toLowerCase();
      const hadDraft = userDraftModule.value?.toLowerCase() === modKey;
      const currentMod = userScriptModuleKey(scriptPath.value.trim()).toLowerCase();
      const removingCurrent = currentMod === modKey;
      if (d.scriptCount > 0) {
        await deleteUserModule(userModuleTenant(d.module));
      }
      const nextExtra = new Set(extraUserModules.value);
      nextExtra.delete(modKey);
      extraUserModules.value = nextExtra;
      const nextExpanded = new Set(expandedUserModules.value);
      nextExpanded.delete(d.module);
      expandedUserModules.value = nextExpanded;
      if (hadDraft) {
        userDraftModule.value = null;
        newScriptBase.value = "";
      }
      const usr = await fetchUserScripts();
      scripts.value = usr.scripts;
      if (removingCurrent || hadDraft) {
        pickFirstUserScriptAfterChange();
      }
    } else {
      const removingCurrent = scriptPath.value.trim() === d.path;
      await deleteUserScript(d.path);
      const usr = await fetchUserScripts();
      scripts.value = usr.scripts;
      if (removingCurrent) {
        pickFirstUserScriptAfterChange();
      }
    }
    deleteDialog.value = null;
    closeUserMenus();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    deletingUser.value = false;
  }
}

function onDocPointerDown(e: PointerEvent) {
  const el = e.target instanceof Element ? e.target : null;
  if (!el) return;
  if (openUserModuleMenu.value != null && !el.closest(".mod-menu-wrap")) {
    openUserModuleMenu.value = null;
  }
  if (openUserWorkspaceMenu.value && !el.closest(".user-ws-menu-wrap")) {
    openUserWorkspaceMenu.value = false;
  }
}

function selectUserScript(mod: string, path: string) {
  closeUserMenus();
  userDraftModule.value = null;
  newScriptBase.value = "";
  scriptNameError.value = "";
  selectedUserModule.value = mod;
  scriptPath.value = path;
  void loadFromPath();
}

function resetUserWorkspaceDraft(mod: string) {
  userDraftModule.value = mod;
  selectedUserModule.value = mod;
  scriptPath.value = "";
  newScriptBase.value = "";
  editScriptBase.value = "";
  scriptNameError.value = "";
  userScriptDescription.value = "";
  userScriptContent.value = USER_SCRIPT_DRAFT_TEMPLATE;
  userExportFunctions.value = [...extractStarlarkExportFunctions(USER_SCRIPT_DRAFT_TEMPLATE)];
  newExportInput.value = "";
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
  closeUserMenus();
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
    editScriptBase.value = userScriptBaseName(p);
    userExportFunctions.value = f.export_functions?.length
      ? [...f.export_functions]
      : [...extractStarlarkExportFunctions(f.content)];
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
  const mod = effectiveUserModule.value;
  const base = activeScriptBase.value.trim();
  if (!mod || !USER_SCRIPT_BASE_RE.test(base)) {
    scriptNameError.value = "方法名：字母数字开头，可含 _、-";
    return;
  }
  const target = buildUserScriptPath(mod, base);
  if (!USER_SCRIPT_PATH_RE.test(target)) {
    scriptNameError.value = "路径格式无效";
    return;
  }
  const current = scriptPath.value.trim();
  const isNew = userIsNew.value;
  if (isNew && scripts.value.includes(target)) {
    scriptNameError.value = "该脚本已存在";
    return;
  }
  if (!isNew && target !== current && scripts.value.includes(target)) {
    scriptNameError.value = "目标路径已被占用";
    return;
  }
  saving.value = true;
  error.value = "";
  scriptNameError.value = "";
  try {
    const payload = {
      content: userScriptContent.value,
      description: userScriptDescription.value,
      export_functions: userExportFunctions.value,
    };
    await putUserScript(target, payload);
    if (!isNew && target !== current) {
      await deleteUserScript(current);
    }
    const usr = await fetchUserScripts();
    scripts.value = usr.scripts;
    extraUserModules.value = new Set([...extraUserModules.value, userScriptModuleKey(target)]);
    if (isNew) {
      userDraftModule.value = null;
      newScriptBase.value = "";
    }
    scriptPath.value = target;
    editScriptBase.value = userScriptBaseName(target);
    selectedUserModule.value = userScriptModuleKey(target);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocPointerDown, true);
  void refreshAll().then(() => {
    void loadFromPath();
    const mod = userScriptModuleKey(scriptPath.value.trim());
    if (mod) {
      selectedUserModule.value = mod;
      expandedUserModules.value = new Set([mod]);
    }
  });
});

onUnmounted(() => {
  document.removeEventListener("pointerdown", onDocPointerDown, true);
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

.btn.danger,
.btn.ghost.danger {
  border-color: color-mix(in srgb, #fecaca 55%, var(--border));
  color: #b91c1c;
}

.btn.ghost.danger:hover:not(:disabled) {
  background: color-mix(in srgb, #fef2f2 80%, var(--surface));
  border-color: color-mix(in srgb, #dc2626 45%, var(--border));
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
  margin-bottom: 8px;
  flex-shrink: 0;
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
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  overflow: auto;
}

.mod-block + .mod-block {
  border-top: 1px solid color-mix(in srgb, var(--border) 75%, transparent);
}

.mod-row {
  position: relative;
  display: flex;
  align-items: stretch;
}

.mod-row .mod-head {
  flex: 1;
  min-width: 0;
  padding-right: 30px;
}

.mod-menu-wrap {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
}

.mod-more-btn {
  border: 0;
  background: transparent;
  color: var(--muted);
  padding: 2px 6px;
  font-size: 14px;
  line-height: 1;
  letter-spacing: 0.08em;
  cursor: pointer;
  border-radius: 6px;
  opacity: 0;
  pointer-events: none;
  transition:
    opacity 0.14s ease,
    color 0.14s ease,
    background 0.14s ease;
}

.mod-row:hover .mod-more-btn,
.mod-row.is-menu-open .mod-more-btn,
.mod-row:focus-within .mod-more-btn {
  opacity: 1;
  pointer-events: auto;
}

.mod-more-btn:hover {
  color: var(--text);
  background: color-mix(in srgb, var(--accent-soft) 55%, transparent);
}

.mod-menu-wrap .menu {
  right: 0;
  top: calc(100% + 4px);
  z-index: 30;
  min-width: 132px;
}

.menu {
  position: absolute;
  right: 0;
  min-width: 132px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  box-shadow: var(--shadow);
  padding: 6px;
  z-index: 20;
}

.menu-item {
  width: 100%;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
  cursor: pointer;
}

.menu-item:hover {
  background: color-mix(in srgb, var(--accent-soft) 60%, transparent);
}

.menu-item.danger {
  color: #b91c1c;
}

.menu-item.danger:hover {
  background: color-mix(in srgb, #ef4444 12%, transparent);
}

.mod-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border: none;
  border-radius: 0;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  text-align: left;
  box-shadow: none;
}

.mod-head:hover {
  background: color-mix(in srgb, var(--accent-soft) 40%, transparent);
}

.mod-head.open {
  background: color-mix(in srgb, var(--accent-soft) 28%, var(--surface));
}

.chev {
  font-size: 9px;
  color: var(--muted);
  width: 12px;
  flex-shrink: 0;
}

.mod-name {
  flex: 1;
  min-width: 0;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mod-count {
  font-size: 10px;
  color: var(--muted);
  flex-shrink: 0;
  padding: 1px 5px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg) 55%, var(--surface));
}

.fn-list {
  list-style: none;
  margin: 0;
  padding: 2px 6px 6px;
}

.fn-item {
  padding: 5px 8px 5px 24px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid transparent;
}

.fn-item:hover {
  background: color-mix(in srgb, var(--accent-soft) 45%, transparent);
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
  padding: 4px 8px 4px 24px;
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

.side-head--row {
  align-items: center;
  flex-wrap: wrap;
}

.side-head-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
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
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin: 4px 0 6px;
  padding: 4px 2px 0;
  border-top: 1px dashed var(--border);
}

.user-mod-list {
  flex: 1;
  min-height: 0;
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
  gap: 10px;
  flex: 1;
  min-height: 0;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  padding: 12px 14px 14px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.panel-head-main {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.panel-head-text {
  min-width: 0;
}

.panel-head-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.panel-title {
  font-weight: 800;
  font-size: 15px;
  letter-spacing: -0.02em;
}

.user-panel-toolbar {
  flex-shrink: 0;
  padding-bottom: 10px;
  margin-bottom: 2px;
  border-bottom: 1px solid var(--border);
}

.user-panel-head-main {
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.user-panel-sub {
  margin: 4px 0 0;
  line-height: 1.45;
}

.user-edit-title {
  margin: 0;
}

.user-id-ref {
  margin: 0;
}

.user-panel-actions {
  align-items: center;
}

.user-ws-menu-wrap {
  position: relative;
}

.user-ws-menu-wrap .menu {
  right: 0;
  top: calc(100% + 6px);
  z-index: 30;
  min-width: 140px;
}

.user-ws-more-btn {
  min-width: 32px;
  padding: 0 8px;
  letter-spacing: 0.1em;
}

.menu-hint {
  margin: 0;
  padding: 6px 10px;
  line-height: 1.4;
}

.user-form-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex-shrink: 0;
}

.user-exports-field .user-export-chips {
  margin-bottom: 6px;
}

.chip-removable {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding-right: 4px;
}

.chip-remove {
  border: 0;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0 2px;
}

.chip-remove:hover {
  color: #b91c1c;
}

.export-add-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.export-add-inp {
  flex: 1;
  min-width: 120px;
}

.em.req {
  color: #b91c1c;
  font-style: normal;
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

.user-export-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.user-exports-empty {
  margin: 0;
  line-height: 1.4;
}

.user-desc-inp {
  resize: vertical;
  min-height: 52px;
  max-height: 100px;
}

.user-script-editor {
  flex: 1 1 auto;
  min-height: 220px;
}

.script-debug-btn {
  border-color: rgba(255, 255, 255, 0.2);
  color: #e2e8f0;
  background: rgba(255, 255, 255, 0.06);
  box-shadow: none;
}

.script-debug-btn:hover:not(:disabled) {
  border-color: rgba(255, 255, 255, 0.32);
  background: rgba(255, 255, 255, 0.12);
  color: #f8fafc;
}

.script-debug-btn:disabled {
  opacity: 0.45;
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
  .user-panel-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .user-panel-actions {
    justify-content: flex-end;
  }
}
</style>
