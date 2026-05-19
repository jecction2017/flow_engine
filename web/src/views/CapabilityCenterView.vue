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
        <p class="confirm-text muted">
          用户脚本路径为 <code class="mono">模块/脚本名.star</code>：模块是路径的第一段，用于分组归类；在任务中通过
          <code class="mono">load("user://模块/脚本名.star", …)</code> 引用。
        </p>
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
          <button type="submit" class="btn primary" :disabled="creatingModule">
            {{ creatingModule ? "添加中…" : "添加" }}
          </button>
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
        <ModListTreeToolbar
          aria-label="Python 内置列表"
          :disabled="filteredPythonGroups.length === 0"
          :module-count="filteredPythonGroups.length"
          :item-count="filteredPythonItemCount"
          item-label="函数"
          @expand-all="expandAllPythonModules"
          @collapse-all="collapseAllPythonModules"
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
            <p class="detail-mono-panel">{{ selectedPythonFn.returns }}</p>
          </section>
          <section v-if="selectedPythonFn.side_effects" class="detail-sec">
            <h3>副作用</h3>
            <p class="detail-value">{{ selectedPythonFn.side_effects }}</p>
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
        <ModListTreeToolbar
          aria-label="Starlark 内置列表"
          :disabled="filteredInternalGroups.length === 0"
          :module-count="filteredInternalGroups.length"
          :item-count="filteredInternalItemCount"
          item-label="脚本"
          @expand-all="expandAllInternalModules"
          @collapse-all="collapseAllInternalModules"
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
          </div>
          <button type="button" class="btn ghost sm" @click="openModuleDialog">+ 添加模块</button>
        </div>
        <label class="sr-only" for="user-search">搜索模块或脚本</label>
        <input
          id="user-search"
          v-model="userSearch"
          type="search"
          class="search-inp"
          placeholder="搜索模块、脚本名、说明…"
          autocomplete="off"
        />
        <ModListTreeToolbar
          aria-label="用户脚本列表"
          :disabled="filteredUserGroups.length === 0"
          :module-count="filteredUserGroups.length"
          :item-count="filteredUserItemCount"
          item-label="脚本"
          @expand-all="expandAllUserModules"
          @collapse-all="collapseAllUserModules"
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
                <span class="mod-count">{{ userModuleScriptCount(g) }}</span>
              </button>
              <div class="mod-menu-wrap" @click.stop>
                <button
                  type="button"
                  class="btn ghost small mod-more-btn"
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
                v-for="p in visibleUserScripts(g.scripts)"
                :key="p"
                class="fn-item"
                :class="{ active: !userDraftModule && scriptPath === p }"
                role="button"
                tabindex="0"
                @click="selectUserScript(g.module, p)"
                @keydown.enter="selectUserScript(g.module, p)"
              >
                <span class="mono fn-name">{{ userScriptFileName(p) }}</span>
                <span class="fn-sum">{{ userScriptListSummary(p) }}</span>
              </li>
              <li
                v-if="!visibleUserScripts(g.scripts).length && userDraftModule !== g.module"
                class="fn-empty muted"
              >
                暂无脚本
              </li>
            </ul>
          </div>
        </div>
        <p v-if="filteredUserGroups.length === 0" class="empty-hint">无匹配项；请先添加模块。</p>
      </aside>
      <main class="main-detail">
        <div v-if="!hasUserWorkspace" class="placeholder">
          <p>从左侧选择脚本，或通过模块 <strong>…</strong> 菜单添加脚本。</p>
          <p class="muted">路径 <code class="mono">模块/名称.star</code> · 保存后可通过 <code class="mono">load("user://…")</code> 引入。</p>
        </div>
        <template v-else>
          <div class="user-ws-head" :class="{ 'user-ws-head--new': userIsNew }">
            <div class="user-ws-toolbar">
              <div v-if="userIsNew" class="user-ws-toolbar-left user-ws-toolbar-left--new">
                <div class="user-ws-title-row">
                  <div class="user-name-inline name-suffix-row">
                    <input
                      id="user-script-name"
                      v-model="activeScriptBase"
                      class="inp mono user-title-inp"
                      :class="{ 'inp-invalid': scriptNameInvalid }"
                      placeholder="脚本名"
                      spellcheck="false"
                      autocomplete="off"
                      :aria-invalid="scriptNameInvalid"
                      :aria-describedby="scriptNameValidationMessage ? 'user-script-name-err' : undefined"
                    />
                    <span class="name-suffix mono">.star</span>
                  </div>
                  <span v-if="effectiveUserModule" class="chip chip-mod">{{ effectiveUserModule }}</span>
                  <span class="user-ws-load-wrap" :title="userLoadRefDisplay">
                    <span class="user-ws-load-lbl">引入：</span>
                    <span class="user-ws-load-ref mono">{{ userLoadRefDisplay }}</span>
                  </span>
                </div>
                <p
                  v-if="scriptNameValidationMessage"
                  id="user-script-name-err"
                  class="field-err user-name-err"
                  role="alert"
                >
                  {{ scriptNameValidationMessage }}
                </p>
              </div>
              <div v-else class="user-ws-toolbar-left">
                <div class="user-ws-title-row">
                  <h2 class="detail-title mono">{{ displayScriptFileName }}</h2>
                  <span v-if="effectiveUserModule" class="chip chip-mod">{{ effectiveUserModule }}</span>
                  <span class="user-ws-load-wrap" :title="userLoadRefDisplay">
                    <span class="user-ws-load-lbl">引入：</span>
                    <span class="user-ws-load-ref mono">{{ userLoadRefDisplay }}</span>
                  </span>
                </div>
              </div>
              <div class="user-ws-toolbar-actions">
                <button
                  type="button"
                  class="btn primary"
                  :disabled="!canSaveUserScript || saving"
                  :title="saveDisabledHint"
                  @click="save"
                >
                  {{ saving ? "保存中…" : "保存" }}
                </button>
                <div class="user-ws-menu-wrap" @click.stop>
                  <button
                    type="button"
                    class="btn ghost user-ws-more-btn"
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
            </div>
          </div>
          <article class="detail-card detail-card--wide user-detail-card">
            <textarea
              v-if="editingUserDesc"
              ref="userDescInputRef"
              v-model="userScriptDescription"
              class="inp user-desc-inp detail-desc-edit"
              rows="2"
              placeholder="点击添加描述，说明脚本用途…"
              @blur="finishEditingUserDesc"
              @keydown.escape.prevent="cancelEditingUserDesc"
            />
            <p
              v-else
              class="detail-desc user-desc-display"
              :class="{ 'is-empty': !userScriptDescription.trim() }"
              tabindex="0"
              role="button"
              @click="startEditingUserDesc"
              @keydown.enter.prevent="startEditingUserDesc"
            >
              {{ userScriptDescription.trim() || "点击添加描述…" }}
            </p>

            <section class="detail-sec user-exports-sec">
              <div class="detail-sec-head-row">
                <h3>导出符号</h3>
                <button type="button" class="btn-link sm" @click="syncExportsFromCode">从源码同步</button>
              </div>
              <div
                class="export-tags-inp"
                :class="{ focused: exportTagsFocused }"
                @click="focusExportInput"
              >
                <span
                  v-for="(ex, idx) in userExportFunctions"
                  :key="ex"
                  class="export-tag chip-ex"
                >
                  <span class="mono">{{ ex }}</span>
                  <button
                    type="button"
                    class="export-tag-remove"
                    :aria-label="`移除 ${ex}`"
                    @click.stop="removeExportSymbol(idx)"
                  >
                    ×
                  </button>
                </span>
                <input
                  ref="exportInputRef"
                  v-model="newExportInput"
                  class="export-tags-input mono"
                  placeholder="符号名，回车添加"
                  spellcheck="false"
                  autocomplete="off"
                  @focus="exportTagsFocused = true"
                  @blur="exportTagsFocused = false"
                  @keydown.enter.prevent="addExportSymbol"
                  @keydown.backspace="onExportInputBackspace"
                />
              </div>
            </section>

            <section class="script-card script-card--dark script-card-editable user-script-editor">
              <div class="script-sec-head">
                <div class="script-sec-head-left">
                  <span class="script-sec-title">Starlark 脚本</span>
                </div>
                <div class="script-sec-actions">
                  <button
                    type="button"
                    class="btn primary sm"
                    :disabled="!canDebugUserScript"
                    :title="debugDisabledHint"
                    @click="openUserDebugDrawer"
                  >
                    调试
                  </button>
                </div>
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
        </template>

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
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";
import CodeEditor from "@/components/CodeEditor.vue";
import DebugDrawer from "@/components/DebugDrawer.vue";
import DebugPanel from "@/components/DebugPanel.vue";
import ModListTreeToolbar from "@/components/ModListTreeToolbar.vue";
import {
  deleteUserModule,
  deleteUserScript,
  ensureUserModule,
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
  isUserModulePlaceholderPath,
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
const userExportFunctions = ref<string[]>([]);
const newExportInput = ref("");
const editingUserDesc = ref(false);
const userDescBeforeEdit = ref("");
const userDescInputRef = ref<HTMLTextAreaElement | null>(null);
const exportInputRef = ref<HTMLInputElement | null>(null);
const userScriptSummaries = ref<Record<string, string>>({});
const exportTagsFocused = ref(false);

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

const saving = ref(false);
const creatingModule = ref(false);
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

const displayScriptFileName = computed(() => {
  const base = activeScriptBase.value.trim();
  if (base) return base.endsWith(".star") ? base : `${base}.star`;
  return userScriptFileName(scriptPath.value);
});

function validateUserScriptName(): string {
  if (!hasUserWorkspace.value) return "";
  const base = activeScriptBase.value.trim();
  const mod = effectiveUserModule.value;

  if (!base) {
    return userIsNew.value ? "请填写脚本名" : "";
  }
  if (!USER_SCRIPT_BASE_RE.test(base)) {
    if (/[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]/.test(base)) {
      return "脚本名不支持中文，请使用字母、数字、_、-";
    }
    return "脚本名须以字母或数字开头，仅可使用英文、数字、_、-";
  }
  if (!mod) return "";

  const target = buildUserScriptPath(mod, base);
  if (!USER_SCRIPT_PATH_RE.test(target)) return "路径格式无效";

  if (userIsNew.value && scripts.value.includes(target)) return "该脚本已存在";
  const current = scriptPath.value.trim();
  if (!userIsNew.value && target !== current && scripts.value.includes(target)) {
    return "目标路径已被占用";
  }
  return "";
}

const scriptNameValidationMessage = computed(() => validateUserScriptName());

const scriptNameInvalid = computed(() => userIsNew.value && scriptNameValidationMessage.value !== "");

const saveDisabledHint = computed(() => {
  if (saving.value || canSaveUserScript.value) return undefined;
  return scriptNameValidationMessage.value || "请先修正脚本名后再保存";
});

const debugDisabledHint = computed(() => {
  if (canDebugUserScript.value) return "调试当前脚本：配置 Profile、抑制规则并执行";
  return scriptNameValidationMessage.value || "请先填写合法的脚本名后再调试";
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
const filteredUserGroups = computed(() =>
  filterUserScriptGroups(userGroups.value, userSearch.value, userScriptSummaries.value),
);

function setUserScriptSummary(path: string, description: string) {
  userScriptSummaries.value = { ...userScriptSummaries.value, [path]: description };
}

function userScriptListSummary(path: string): string {
  if (!userDraftModule.value && scriptPath.value.trim() === path) {
    const live = userScriptDescription.value.trim();
    if (live) return live;
  }
  const cached = (userScriptSummaries.value[path] ?? "").trim();
  return cached || "暂无描述";
}

function visibleUserScripts(paths: string[]): string[] {
  return paths.filter((p) => !isUserModulePlaceholderPath(p));
}

function userModuleScriptCount(g: { module: string; scripts: string[] }): number {
  return visibleUserScripts(g.scripts).length + (userDraftModule.value === g.module ? 1 : 0);
}

const filteredPythonItemCount = computed(() =>
  filteredPythonGroups.value.reduce((sum, g) => sum + g.functions.length, 0),
);

const filteredInternalItemCount = computed(() =>
  filteredInternalGroups.value.reduce((sum, g) => sum + g.scripts.length, 0),
);

const filteredUserItemCount = computed(() =>
  filteredUserGroups.value.reduce((sum, g) => sum + visibleUserScripts(g.scripts).length, 0),
);

const pythonExampleCall = computed(() =>
  selectedPythonFn.value ? formatPythonExampleCall(selectedPythonFn.value) : "",
);

const internalLoadExample = computed(() => {
  const m = selectedInternal.value;
  if (!m?.exports.length) return `load("${m?.uri ?? ""}")`;
  const syms = m.exports.map((s) => `"${s}"`).join(", ");
  return `load("${m.uri}", ${syms})`;
});

const userLoadRefDisplay = computed(() => {
  const path = effectiveUserScriptPath.value.trim();
  if (path && USER_SCRIPT_PATH_RE.test(path)) {
    const uri = `user://${path}`;
    const syms = userExportFunctions.value;
    if (syms.length) {
      return `load("${uri}", ${syms.map((s) => `"${s}"`).join(", ")})`;
    }
    return `load("${uri}")`;
  }
  const mod = effectiveUserModule.value;
  if (mod) {
    const base = activeScriptBase.value.trim();
    const file = base ? (base.endsWith(".star") ? base : `${base}.star`) : "脚本名.star";
    return `load("user://${mod}/${file}", …)`;
  }
  return 'load("user://模块/脚本名.star", …)';
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

function setExpandedModules(expanded: { value: Set<string> }, keys: string[]) {
  expanded.value = new Set(keys);
}

function collapseExpandedModules(expanded: { value: Set<string> }) {
  expanded.value = new Set();
}

function expandAllPythonModules() {
  setExpandedModules(
    expandedModules,
    filteredPythonGroups.value.map((g) => g.module),
  );
}

function collapseAllPythonModules() {
  collapseExpandedModules(expandedModules);
}

function expandAllInternalModules() {
  setExpandedModules(
    expandedInternalModules,
    filteredInternalGroups.value.map((g) => g.module),
  );
}

function collapseAllInternalModules() {
  collapseExpandedModules(expandedInternalModules);
}

function expandAllUserModules() {
  setExpandedModules(
    expandedUserModules,
    filteredUserGroups.value.map((g) => g.module),
  );
}

function collapseAllUserModules() {
  collapseExpandedModules(expandedUserModules);
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

function focusExportInput() {
  exportInputRef.value?.focus();
}

function onExportInputBackspace() {
  if (newExportInput.value) return;
  const list = userExportFunctions.value;
  if (!list.length) return;
  userExportFunctions.value = list.slice(0, -1);
}

function resetUserDescEditing() {
  editingUserDesc.value = false;
  userDescBeforeEdit.value = "";
}

async function startEditingUserDesc() {
  userDescBeforeEdit.value = userScriptDescription.value;
  editingUserDesc.value = true;
  await nextTick();
  userDescInputRef.value?.focus();
  userDescInputRef.value?.select();
}

function finishEditingUserDesc() {
  editingUserDesc.value = false;
  userDescBeforeEdit.value = "";
  const p = scriptPath.value.trim();
  if (p && !userIsNew.value) {
    setUserScriptSummary(p, userScriptDescription.value);
  }
}

function cancelEditingUserDesc() {
  userScriptDescription.value = userDescBeforeEdit.value;
  resetUserDescEditing();
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
  resetUserDescEditing();
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
      userScriptSummaries.value = usr.descriptions ?? {};
      if (removingCurrent || hadDraft) {
        pickFirstUserScriptAfterChange();
      }
    } else {
      const removingCurrent = scriptPath.value.trim() === d.path;
      await deleteUserScript(d.path);
      const usr = await fetchUserScripts();
      scripts.value = usr.scripts;
      userScriptSummaries.value = usr.descriptions ?? {};
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
  resetUserDescEditing();
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
  resetUserDescEditing();
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

async function confirmAddModule() {
  newModuleError.value = "";
  const name = newModuleName.value.trim();
  if (!USER_MODULE_RE.test(name)) {
    newModuleError.value = "模块名：字母数字开头，可含 _、-，最长 64 字符";
    return;
  }
  const key = name.toLowerCase();
  if (userGroups.value.some((g) => g.module === key)) {
    newModuleError.value = "该模块已存在";
    return;
  }
  creatingModule.value = true;
  try {
    await ensureUserModule(key);
    const usr = await fetchUserScripts();
    scripts.value = usr.scripts;
    userScriptSummaries.value = { ...userScriptSummaries.value, ...usr.descriptions };
    expandedUserModules.value = new Set([...expandedUserModules.value, key]);
    selectedUserModule.value = key;
    newModuleName.value = "";
    moduleDialogOpen.value = false;
    userSearch.value = "";
    startNewUserScript(key);
  } catch (e) {
    newModuleError.value = e instanceof Error ? e.message : String(e);
  } finally {
    creatingModule.value = false;
  }
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
  try {
    const [reg, usr] = await Promise.all([fetchStarlarkRegistry(), fetchUserScripts()]);
    registry.value = reg;
    scripts.value = usr.scripts;
    scriptsRoot.value = usr.root;
    userScriptSummaries.value = usr.descriptions ?? {};
    if (!scriptPath.value.trim() && usr.scripts.length) {
      scriptPath.value = usr.scripts[0] ?? "default/hello.star";
      await loadFromPath();
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
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
    setUserScriptSummary(p, f.description ?? "");
    editScriptBase.value = userScriptBaseName(p);
    resetUserDescEditing();
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
  const nameErr = scriptNameValidationMessage.value;
  if (nameErr || !canSaveUserScript.value) return;
  const mod = effectiveUserModule.value;
  const base = activeScriptBase.value.trim();
  const target = buildUserScriptPath(mod, base);
  const current = scriptPath.value.trim();
  const isNew = userIsNew.value;
  saving.value = true;
  error.value = "";
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
    userScriptSummaries.value = usr.descriptions ?? {};
    setUserScriptSummary(target, userScriptDescription.value);
    if (!isNew && target !== current) {
      const nextSummaries = { ...userScriptSummaries.value };
      delete nextSummaries[current];
      userScriptSummaries.value = nextSummaries;
    }
    extraUserModules.value = new Set([...extraUserModules.value, userScriptModuleKey(target)]);
    if (isNew) {
      userDraftModule.value = null;
      newScriptBase.value = "";
    }
    scriptPath.value = target;
    editScriptBase.value = userScriptBaseName(target);
    selectedUserModule.value = userScriptModuleKey(target);
    resetUserDescEditing();
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
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 86%, transparent);
}

.brand {
  grid-column: 1;
  justify-self: start;
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
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
  grid-column: 2;
  justify-self: center;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  justify-content: center;
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

.btn.sm,
.btn.small {
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
  display: flex;
  align-items: center;
  gap: 4px;
  padding-right: 4px;
}

.mod-row .mod-head {
  flex: 1;
  min-width: 0;
  padding-right: 6px;
}

.user-mod-list .mod-row:hover,
.user-mod-list .mod-row.is-menu-open,
.user-mod-list .mod-row:has(.mod-head.open) {
  background: color-mix(in srgb, var(--accent-soft) 40%, transparent);
}

.user-mod-list .mod-row:has(.mod-head.open) {
  background: color-mix(in srgb, var(--accent-soft) 28%, var(--surface));
}

.user-mod-list .mod-head:hover,
.user-mod-list .mod-head.open {
  background: transparent;
}

.mod-menu-wrap {
  position: relative;
  flex-shrink: 0;
}

.user-mod-list .mod-more-btn {
  min-width: 28px;
  padding: 2px 6px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  box-shadow: none;
  color: var(--muted);
  letter-spacing: 0.08em;
  transition:
    background 0.12s ease,
    color 0.12s ease,
    border-color 0.12s ease,
    box-shadow 0.12s ease;
}

.user-mod-list .mod-more-btn:hover:not(:disabled) {
  color: var(--text);
  background: color-mix(in srgb, var(--accent-soft) 60%, transparent);
  border-color: color-mix(in srgb, var(--border) 70%, transparent);
}

.user-mod-list .mod-more-btn:focus-visible {
  outline: none;
  color: var(--text);
  background: color-mix(in srgb, var(--accent-soft) 60%, transparent);
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 28%, transparent);
}

.user-mod-list .mod-more-btn:active:not(:disabled) {
  color: var(--text);
  background: color-mix(in srgb, var(--accent-soft) 85%, var(--surface));
  border-color: color-mix(in srgb, var(--accent) 25%, var(--border));
  box-shadow: inset 0 1px 2px color-mix(in srgb, var(--text) 8%, transparent);
}

.user-mod-list .mod-row.is-menu-open .mod-more-btn {
  color: var(--text);
  background: color-mix(in srgb, var(--accent-soft) 75%, var(--surface));
  border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
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
  font-size: 13px;
  line-height: 1.45;
  color: var(--text);
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
  margin: 12px 0 16px;
}

.detail-sec h3 {
  margin: 0 0 8px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
}

.detail-sec {
  margin-bottom: 14px;
}

.detail-value {
  margin: 0;
  font-size: inherit;
  line-height: inherit;
  color: var(--text);
}

.detail-mono-panel {
  margin: 0;
  padding: 8px 10px;
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.5;
  color: var(--text);
  background: color-mix(in srgb, var(--surface) 92%, var(--bg));
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow-x: auto;
}

.sig-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  line-height: 1.4;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.sig-table th,
.sig-table td {
  border-bottom: 1px solid var(--border);
  padding: 8px 10px;
  text-align: left;
  font-size: 12px;
}

.sig-table th {
  background: color-mix(in srgb, var(--surface) 90%, var(--bg));
  font-weight: 600;
  color: var(--muted);
}

.sig-table td.mono {
  font-family: var(--mono);
}

.sig-table .muted {
  font-size: 12px;
}

.code-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px;
}

.detail-card .code-block {
  margin: 0;
  flex: 1;
  min-width: 200px;
  padding: 10px 12px;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.5;
  overflow: auto;
}

.detail-card .id-ref {
  margin: 8px 0 0;
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.35;
  color: var(--muted);
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

.script-sec-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
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

.user-ws-head {
  flex-shrink: 0;
  margin-bottom: 0;
}

.user-ws-head--new .user-ws-toolbar {
  align-items: flex-start;
}

.user-ws-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
}

.user-ws-toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1 1 auto;
}

.user-ws-toolbar-left--new {
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
}

.user-ws-title-row {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 6px 10px;
  min-width: 0;
}

.user-ws-title-row .detail-title {
  flex-shrink: 0;
  line-height: 1.2;
}

.user-ws-title-row .chip-mod {
  align-self: flex-end;
  margin-bottom: 3px;
}

.user-ws-load-wrap {
  display: inline-flex;
  align-items: baseline;
  gap: 0;
  align-self: flex-end;
  flex: 1 1 12rem;
  min-width: 0;
  max-width: 100%;
  padding: 2px 6px;
  border-radius: 5px;
  background: color-mix(in srgb, var(--bg) 62%, var(--surface));
  border: 1px solid color-mix(in srgb, var(--border-strong) 55%, var(--border));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
}

.user-ws-load-lbl {
  flex-shrink: 0;
  font-size: 9px;
  line-height: 1.3;
  color: var(--muted);
}

.user-ws-load-ref {
  min-width: 0;
  font-size: 9px;
  line-height: 1.3;
  color: color-mix(in srgb, var(--text) 72%, var(--muted));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-ws-head--new .user-ws-load-wrap {
  flex-basis: 100%;
}

.user-ws-head--new .user-ws-load-ref {
  white-space: normal;
  word-break: break-all;
}

.user-name-err {
  margin: 0;
  font-size: 11px;
  line-height: 1.35;
}

.user-ws-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  margin-left: auto;
}

.user-name-inline.name-suffix-row .inp,
.user-name-inline .user-title-inp {
  flex: 0 0 auto;
  width: 280px;
  max-width: min(56vw, 420px);
  min-width: 160px;
  padding: 5px 8px;
  font-size: 14px;
  font-weight: 600;
}

.user-detail-card {
  flex: 1 1 auto;
  min-height: 0;
}

.user-desc-display {
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.12s ease;
}

.user-desc-display:hover,
.user-desc-display:focus-visible {
  background: color-mix(in srgb, var(--accent-soft) 35%, transparent);
  outline: none;
}

.user-desc-display.is-empty {
  color: var(--muted);
  font-style: italic;
}

.detail-desc-edit {
  margin: 12px 0 16px;
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  min-height: 52px;
  line-height: 1.45;
}

.detail-sec-head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.detail-sec-head-row h3 {
  margin: 0;
}

.user-exports-sec .export-tags-inp {
  max-height: none;
  flex-wrap: wrap;
  overflow-x: visible;
  overflow-y: visible;
  min-height: 34px;
  height: auto;
  padding: 5px 6px;
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
  min-width: 36px;
  letter-spacing: 0.1em;
}

.menu-hint {
  margin: 0;
  padding: 6px 10px;
  line-height: 1.4;
}

.user-title-inp.inp-invalid {
  border-color: color-mix(in srgb, #f87171 55%, var(--border));
  box-shadow: 0 0 0 2px color-mix(in srgb, #fecaca 45%, transparent);
}

.btn-link {
  border: 0;
  background: transparent;
  color: var(--accent);
  font-size: 11px;
  padding: 0;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.btn-link:hover {
  color: color-mix(in srgb, var(--accent) 75%, #000);
}

.export-tags-inp {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 4px;
  min-height: 34px;
  max-height: 34px;
  padding: 3px 6px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  overflow-x: auto;
  overflow-y: hidden;
  cursor: text;
}

.export-tags-inp.focused {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.export-tag {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  font-size: 10px;
  padding: 2px 4px 2px 6px;
  border-radius: 5px;
  border: 1px solid color-mix(in srgb, #c7d2fe 55%, var(--border));
  background: color-mix(in srgb, #e0e7ff 50%, #fff);
}

.export-tag-remove {
  border: 0;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  padding: 0 2px;
}

.export-tag-remove:hover {
  color: #b91c1c;
}

.export-tags-input {
  flex: 1 1 72px;
  min-width: 72px;
  border: 0;
  outline: none;
  background: transparent;
  font-size: 12px;
  padding: 2px 4px;
  box-shadow: none;
}

.em.req {
  color: #b91c1c;
  font-style: normal;
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

.user-desc-inp {
  resize: vertical;
  min-height: 34px;
  max-height: 80px;
  line-height: 1.35;
}

.user-script-editor {
  flex: 1 1 auto;
  min-height: 280px;
  margin-top: 8px;
}

.inp:focus,
.user-desc-inp:focus,
.export-tags-input:focus {
  outline: none;
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.export-tags-input:focus {
  border-color: transparent;
  box-shadow: none;
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
