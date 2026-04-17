<template>
  <div class="cap">
    <header class="top">
      <div class="brand">
        <span class="logo">◇</span>
        <div>
          <div class="title">能力与脚本</div>
          <div class="subtitle">Python 内置参考 · Starlark 内置脚本 · 用户自定义脚本</div>
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
        <button
          v-if="activeSegment === 'user'"
          type="button"
          class="btn primary"
          :disabled="!scriptPathValid || saving"
          @click="save"
        >
          {{ saving ? "保存中…" : "保存脚本" }}
        </button>
        <button
          v-if="activeSegment === 'user'"
          type="button"
          class="btn ghost"
          :disabled="pendingDebug"
          @click="runDebug"
        >
          {{ pendingDebug ? "调试中…" : "调试" }}
        </button>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <!-- Python 内置：按模块浏览，结构化说明 -->
    <div v-show="activeSegment === 'python'" class="body body-py">
      <aside class="side py-side">
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
      <main class="main-detail py-detail">
        <div v-if="!selectedPythonFn" class="placeholder">
          <p>从左侧选择函数，查看参数说明与调用示例。</p>
          <p class="muted">Python 内置由服务端注册表提供，任务脚本中可直接调用函数名（无需 <code>load</code>）。</p>
        </div>
        <article v-else class="py-card">
          <header class="py-card-head">
            <h2 class="py-fn-title mono">{{ selectedPythonFn.starlark_name }}</h2>
            <span class="chip chip-mod">{{ pythonModuleKey(selectedPythonFn) }}</span>
          </header>
          <p class="py-desc">{{ selectedPythonFn.summary }}</p>
          <section class="py-sec">
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
          <section class="py-sec">
            <h3>返回值</h3>
            <p class="mono ret">{{ selectedPythonFn.returns }}</p>
          </section>
          <section v-if="selectedPythonFn.side_effects" class="py-sec">
            <h3>副作用</h3>
            <p>{{ selectedPythonFn.side_effects }}</p>
          </section>
          <section class="py-sec">
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

    <!-- Starlark 内置：卡片 + 只读源码 -->
    <div v-show="activeSegment === 'internal'" class="body body-int">
      <aside class="side int-list">
        <div class="panel-h">
          <span class="seg-badge int">内置 .star</span>
          包内脚本（只读）
        </div>
        <p class="panel-desc">通过 <code class="mono">load("internal://…", "符号1", …)</code> 引入后，即可使用列出的符号。</p>
        <ul class="int-cards">
          <li
            v-for="m in registry?.internal_modules ?? []"
            :key="m.uri"
            class="int-card"
            :class="{ active: selectedInternalUri === m.uri }"
            role="button"
            tabindex="0"
            @click="selectInternal(m)"
            @keydown.enter="selectInternal(m)"
          >
            <div class="int-card-title">{{ m.summary || m.uri }}</div>
            <div class="mono int-uri">{{ m.uri }}</div>
            <div class="int-exports">
              <span v-for="ex in m.exports" :key="ex" class="chip chip-ex">{{ ex }}</span>
            </div>
          </li>
        </ul>
      </aside>
      <main class="main-detail int-detail">
        <div v-if="!selectedInternal" class="placeholder">
          <p>请选择左侧内置模块，查看 <code>load</code> 写法与源码。</p>
        </div>
        <template v-else>
          <section class="int-meta">
            <h2 class="int-h">{{ selectedInternal.summary || selectedInternal.uri }}</h2>
            <div class="load-line-wrap">
              <span class="lbl">引入</span>
              <pre class="code-block mono load-line">{{ internalLoadExample }}</pre>
              <button type="button" class="btn ghost sm" @click="copyInternalLoad">复制</button>
            </div>
            <div>
              <span class="lbl">导出符号</span>
              <span v-for="ex in selectedInternal.exports" :key="ex" class="chip chip-ex">{{ ex }}</span>
            </div>
          </section>
          <div class="int-src-head">
            <span class="lbl">源码（只读）</span>
            <span v-if="internalLoading" class="muted">加载中…</span>
          </div>
          <CodeEditor
            :model-value="internalReadonlyContent"
            :read-only="true"
            :height="420"
            language="python"
            :registry="registry"
          />
        </template>
      </main>
    </div>

    <!-- 用户脚本：可编辑 -->
    <div v-show="activeSegment === 'user'" class="body body-user">
      <div class="user-panel">
        <div class="user-banner">
          <span class="seg-badge usr">自定义</span>
          <span>用户脚本保存在服务端 <code class="mono">starlark_user</code> 目录；路径格式：<code class="mono">租户/路径.star</code></span>
        </div>
        <div v-if="scriptsRoot" class="root-line mono">根目录：{{ scriptsRoot }}</div>
        <div class="row">
          <label class="lbl">脚本路径</label>
          <div class="path-row">
            <input
              v-model="scriptPath"
              class="path-inp mono"
              spellcheck="false"
              placeholder="default/my.star"
              @keydown.enter="loadFromPath"
            />
            <button type="button" class="btn ghost" @click="loadFromPath">加载</button>
          </div>
          <p v-if="!scriptPathValid && scriptPath.trim()" class="field-err">
            路径格式：租户名/相对路径.star（字母数字、_、-、/）
          </p>
          <label class="lbl row-gap">快速选择</label>
          <select class="sel" :value="scripts.includes(scriptPath) ? scriptPath : ''" @change="onQuickPick">
            <option value="">选择已有脚本…</option>
            <option v-for="s in scripts" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
        <CodeEditor
          v-model="userScriptContent"
          :read-only="false"
          :height="520"
          language="python"
          class="user-editor"
          :registry="registry"
        />
        <details class="dbg-details" open>
          <summary class="dbg-sum">调试（上下文 JSON + 输出）</summary>
          <div class="row dbg">
            <label class="lbl">初始上下文 JSON</label>
            <textarea v-model="ctxJson" class="area mono" rows="4" spellcheck="false" />
          </div>
          <div class="lbl">输出</div>
          <pre class="out mono">{{ debugOut }}</pre>
        </details>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import CodeEditor from "@/components/CodeEditor.vue";
import {
  debugNode,
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
  filterPythonModuleGroups,
  formatPythonExampleCall,
  groupPythonFunctionsByModule,
  pythonModuleKey,
} from "@/utils/registryGroup";

const USER_SCRIPT_PATH_RE = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\/[a-zA-Z0-9][a-zA-Z0-9_./-]*\.star$/;

type Segment = "python" | "internal" | "user";

const activeSegment = ref<Segment>("python");
const registry = ref<RegistryDoc | null>(null);
const scripts = ref<string[]>([]);
const scriptsRoot = ref("");

const pythonSearch = ref("");
const expandedModules = ref<Set<string>>(new Set());
const selectedPythonFn = ref<RegistryPythonFn | null>(null);

const selectedInternalUri = ref<string | null>(null);
const selectedInternal = ref<RegistryInternalModule | null>(null);
const internalReadonlyContent = ref("# 请选择内置模块\n");
const internalLoading = ref(false);

const scriptPath = ref("default/hello.star");
const userScriptContent = ref(`load("internal://lib/helpers.star", "double_int")

{"demo": double_int(21)}
`);
const ctxJson = ref("{}");
const debugOut = ref("// 在「用户脚本」分区点击「调试」");

const loading = ref(false);
const saving = ref(false);
const pendingDebug = ref(false);
const error = ref("");

const scriptPathValid = computed(() => USER_SCRIPT_PATH_RE.test(scriptPath.value.trim()));

const pythonGroups = computed(() => groupPythonFunctionsByModule(registry.value?.python_functions ?? []));
const filteredPythonGroups = computed(() => filterPythonModuleGroups(pythonGroups.value, pythonSearch.value));

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
  const keys = new Set(groups.map((g) => g.module));
  const next = new Set<string>();
  for (const m of expandedModules.value) {
    if (keys.has(m)) next.add(m);
  }
  if (next.size === 0 && groups.length) next.add(groups[0].module);
  expandedModules.value = next;
  const sel = selectedPythonFn.value;
  if (sel && !groups.some((g) => g.functions.some((f) => f.id === sel.id))) {
    selectedPythonFn.value = groups[0]?.functions[0] ?? null;
  }
});

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

function onQuickPick(ev: Event) {
  const v = (ev.target as HTMLSelectElement).value;
  if (!v) return;
  scriptPath.value = v;
  void loadFromPath();
}

async function loadFromPath() {
  const p = scriptPath.value.trim();
  if (!USER_SCRIPT_PATH_RE.test(p)) {
    error.value = "路径格式无效";
    return;
  }
  try {
    const f = await getUserScript(p);
    userScriptContent.value = f.content;
    error.value = "";
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes("404") || msg.includes("not found")) {
      userScriptContent.value = `# 新文件: ${p}（保存后写入）\n\n{"ok": True}\n`;
      error.value = "";
    } else {
      error.value = msg;
    }
  }
}

async function save() {
  if (activeSegment.value !== "user") return;
  const p = scriptPath.value.trim();
  if (!USER_SCRIPT_PATH_RE.test(p)) {
    error.value = "路径格式无效";
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    await putUserScript(p, userScriptContent.value);
    const usr = await fetchUserScripts();
    scripts.value = usr.scripts;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}

async function runDebug() {
  if (activeSegment.value !== "user") return;
  let ctx: Record<string, unknown> = {};
  try {
    ctx = JSON.parse(ctxJson.value || "{}") as Record<string, unknown>;
  } catch {
    debugOut.value = "// 上下文 JSON 无效";
    return;
  }
  pendingDebug.value = true;
  try {
    const res = await debugNode(userScriptContent.value, ctx);
    debugOut.value = JSON.stringify(res, null, 2);
  } catch (e) {
    debugOut.value = e instanceof Error ? e.message : String(e);
  } finally {
    pendingDebug.value = false;
  }
}

onMounted(() => {
  void refreshAll().then(() => {
    void loadFromPath();
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

.btn.primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn.ghost:hover {
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

.body-user {
  grid-template-columns: 1fr;
  overflow: auto;
}

.side {
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  overflow: auto;
  padding: 12px;
  min-height: 0;
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

.search-inp {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
  margin-bottom: 10px;
  background: #fff;
}

.mod-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
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

.mod-head.open {
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

.empty-hint {
  font-size: 11px;
  color: var(--muted);
  margin-top: 8px;
}

.main-detail {
  min-width: 0;
  padding: 16px 20px;
  overflow: auto;
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

.py-card {
  max-width: 720px;
}

.py-card-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.py-fn-title {
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

.py-desc {
  font-size: 13px;
  margin: 12px 0 16px;
  line-height: 1.45;
}

.py-sec h3 {
  margin: 0 0 8px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
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
  margin-top: 20px;
  font-size: 11px;
}

.body-int .int-list {
  max-width: 320px;
}

.panel-h {
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-desc {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.4;
  margin: 0 0 12px;
}

.int-cards {
  list-style: none;
  margin: 0;
  padding: 0;
}

.int-card {
  padding: 10px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--surface);
  margin-bottom: 8px;
  cursor: pointer;
  box-shadow: 0 1px 0 color-mix(in srgb, var(--border) 50%, transparent);
}

.int-card:hover {
  border-color: color-mix(in srgb, #6366f1 35%, var(--border));
}

.int-card.active {
  border-color: color-mix(in srgb, #4f46e5 50%, var(--border));
  background: color-mix(in srgb, #eef2ff 55%, var(--surface));
}

.int-card-title {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 4px;
}

.int-uri {
  font-size: 11px;
  color: var(--muted);
  word-break: break-all;
  margin-bottom: 6px;
}

.int-exports {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.int-meta {
  margin-bottom: 12px;
}

.int-h {
  margin: 0 0 12px;
  font-size: 16px;
}

.load-line-wrap {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
}

.load-line {
  flex: 1;
  min-width: 220px;
}

.lbl {
  display: block;
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 4px;
}

.load-line-wrap .lbl {
  width: 100%;
}

.int-src-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.user-panel {
  box-sizing: border-box;
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 16px 24px 28px;
}

.user-editor {
  width: 100%;
  min-width: 0;
  display: block;
}

.user-banner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, #10b981 35%, var(--border));
  background: color-mix(in srgb, #d1fae5 28%, var(--surface));
  font-size: 12px;
  margin-bottom: 10px;
}

.root-line {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 10px;
  word-break: break-all;
}

.row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}

.row-gap {
  margin-top: 6px;
}

.path-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.path-inp {
  flex: 1;
  min-width: 0;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 12px;
  background: #fff;
}

.field-err {
  margin: 0;
  font-size: 11px;
  color: #b45309;
}

.sel {
  width: 100%;
  max-width: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 12px;
  background: #fff;
}

.dbg-details {
  margin-top: 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 12px;
  background: color-mix(in srgb, var(--surface) 95%, transparent);
}

.dbg-sum {
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  user-select: none;
}

.area {
  width: 100%;
  max-width: none;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  font-size: 12px;
  resize: vertical;
}

.out {
  margin: 0;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: #0f172a;
  color: #e2e8f0;
  font-size: 11px;
  max-height: min(50vh, 360px);
  overflow: auto;
  white-space: pre-wrap;
}

.muted {
  color: var(--muted);
}

@media (max-width: 900px) {
  .body-py,
  .body-int {
    grid-template-columns: 1fr;
  }
  .side {
    border-right: none;
    border-bottom: 1px solid var(--border);
    max-height: 38vh;
  }
}
</style>
