<template>
  <div class="cap">
    <header class="top">
      <div class="brand">
        <span class="logo">◇</span>
        <div>
          <div class="title">能力与脚本</div>
          <div class="subtitle">
            注册表 · 用户 Starlark · 快速调试（<code class="mono">/api/starlark</code>）
          </div>
        </div>
      </div>
      <div class="actions">
        <button type="button" class="btn ghost" :disabled="loading" @click="refreshAll">刷新</button>
        <button
          type="button"
          class="btn primary"
          :disabled="panelMode !== 'user' || !scriptPathValid || saving"
          @click="save"
        >
          {{ saving ? "保存中…" : "保存脚本" }}
        </button>
        <button type="button" class="btn ghost" :disabled="pendingDebug" @click="runDebug">
          {{ pendingDebug ? "调试中…" : "调试当前编辑器" }}
        </button>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="body">
      <aside class="left">
        <section class="block">
          <div class="h">Python 内置（registry）</div>
          <ul class="list">
            <li
              v-for="f in registry?.python_functions ?? []"
              :key="f.id"
              class="item click"
              :class="{ active: activePythonId === f.id }"
              role="button"
              tabindex="0"
              @click="showPythonDetail(f)"
              @keydown.enter="showPythonDetail(f)"
            >
              <span class="mono name">{{ f.starlark_name }}</span>
              <span class="meta">{{ f.category }} · {{ f.summary }}</span>
              <span class="hint">点击查看详情（可编辑、可调试）</span>
            </li>
          </ul>
        </section>
        <section class="block">
          <div class="h">internal 模块</div>
          <ul class="list">
            <li
              v-for="m in registry?.internal_modules ?? []"
              :key="m.uri"
              class="item click"
              :class="{ active: activeInternalUri === m.uri }"
              role="button"
              tabindex="0"
              @click="showInternalDetail(m)"
              @keydown.enter="showInternalDetail(m)"
            >
              <span class="mono name">{{ m.uri }}</span>
              <span class="meta">{{ m.exports.join(", ") }}</span>
              <span class="hint">点击查看源码（可编辑、可调试）</span>
            </li>
          </ul>
        </section>
        <section v-if="scriptsRoot" class="block muted-block">
          <div class="h">用户根目录</div>
          <div class="root mono">{{ scriptsRoot }}</div>
        </section>
      </aside>

      <div class="right">
        <p v-if="panelMode !== 'user'" class="banner">
          <span>{{ panelHint }}</span>
          <button type="button" class="btn ghost sm" @click="switchToUserEditing">切到用户脚本</button>
        </p>

        <div class="row">
          <label class="lbl">用户脚本路径（可改；保存将创建或覆盖该路径）</label>
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
            用户路径格式：租户名/相对路径.star（仅字母数字、_、-、/）
          </p>
          <label class="lbl row-gap">从已有列表选择</label>
          <select
            class="sel"
            :value="scripts.includes(scriptPath) ? scriptPath : ''"
            @change="onQuickPick"
          >
            <option value="">快速选择…</option>
            <option v-for="s in scripts" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>

        <CodeEditor :model-value="editorText" :height="420" @update:model-value="onEditorInput" />
        <div class="row dbg">
          <label class="lbl">调试上下文 JSON</label>
          <textarea v-model="ctxJson" class="area mono" rows="4" spellcheck="false" />
        </div>
        <div class="lbl">调试输出</div>
        <pre class="out mono">{{ debugOut }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
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

const USER_SCRIPT_PATH_RE = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\/[a-zA-Z0-9][a-zA-Z0-9_./-]*\.star$/;

const registry = ref<RegistryDoc | null>(null);
const scripts = ref<string[]>([]);
const scriptsRoot = ref("");

type PanelMode = "user" | "detail_python" | "detail_internal";
const panelMode = ref<PanelMode>("user");
const activePythonId = ref<string | null>(null);
const activeInternalUri = ref<string | null>(null);

const scriptPath = ref("default/hello.star");
const editorText = ref(`load("internal://lib/helpers.star", "double_int")

{"demo": double_int(21)}
`);
const ctxJson = ref("{}");
const debugOut = ref("// 点击「调试当前编辑器」");
const loading = ref(false);
const saving = ref(false);
const pendingDebug = ref(false);
const error = ref("");

const scriptPathValid = computed(() => USER_SCRIPT_PATH_RE.test(scriptPath.value.trim()));

const panelHint = computed(() => {
  if (panelMode.value === "detail_python") {
    return "Python 内置说明可在编辑器修改（便于复制/试写）；「保存脚本」只写入上方用户路径，不会回写 registry。";
  }
  if (panelMode.value === "detail_internal") {
    return "internal 源码可编辑并调试；保存仍只针对用户脚本路径。若要把修改写回包内文件请改仓库源码或后续加写入接口。";
  }
  return "";
});

function onEditorInput(v: string) {
  editorText.value = v;
}

function formatPythonDetail(f: RegistryPythonFn): string {
  const lines = [
    "# Python 内置函数（registry 元数据，可编辑；保存不会更新 registry）",
    "",
    JSON.stringify(f, null, 2),
    "",
    "# 在 Starlark 任务中直接调用：",
    `# ${f.starlark_name}(...)`,
  ];
  return lines.join("\n");
}

function showPythonDetail(f: RegistryPythonFn) {
  panelMode.value = "detail_python";
  activePythonId.value = f.id;
  activeInternalUri.value = null;
  editorText.value = formatPythonDetail(f);
  error.value = "";
}

async function showInternalDetail(m: RegistryInternalModule) {
  panelMode.value = "detail_internal";
  activeInternalUri.value = m.uri;
  activePythonId.value = null;
  error.value = "";
  const rel = internalRelFromRegistryPath(m.path);
  try {
    const f = await getInternalScript(rel);
    editorText.value = f.content;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    editorText.value = `# 加载失败：${error.value}\n# 路径：${rel}`;
  }
}

function switchToUserEditing() {
  panelMode.value = "user";
  activePythonId.value = null;
  activeInternalUri.value = null;
  error.value = "";
  void loadFromPath();
}

async function refreshAll() {
  error.value = "";
  loading.value = true;
  try {
    const [reg, usr] = await Promise.all([fetchStarlarkRegistry(), fetchUserScripts()]);
    registry.value = reg;
    scripts.value = usr.scripts;
    scriptsRoot.value = usr.root;
    if (panelMode.value === "user" && !scriptPath.value.trim() && usr.scripts.length) {
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
    panelMode.value = "user";
    activePythonId.value = null;
    activeInternalUri.value = null;
    editorText.value = f.content;
    error.value = "";
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes("404") || msg.includes("not found")) {
      panelMode.value = "user";
      activePythonId.value = null;
      activeInternalUri.value = null;
      editorText.value = `# 新文件: ${p}（保存后写入磁盘）\n\n{"ok": True}\n`;
      error.value = "";
    } else {
      error.value = msg;
    }
  }
}

async function save() {
  if (panelMode.value !== "user") return;
  const p = scriptPath.value.trim();
  if (!USER_SCRIPT_PATH_RE.test(p)) {
    error.value = "路径格式无效";
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    await putUserScript(p, editorText.value);
    const usr = await fetchUserScripts();
    scripts.value = usr.scripts;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}

async function runDebug() {
  let ctx: Record<string, unknown> = {};
  try {
    ctx = JSON.parse(ctxJson.value || "{}") as Record<string, unknown>;
  } catch {
    debugOut.value = "// 上下文 JSON 无效";
    return;
  }
  pendingDebug.value = true;
  try {
    const res = await debugNode(editorText.value, ctx);
    debugOut.value = JSON.stringify(res, null, 2);
  } catch (e) {
    debugOut.value = e instanceof Error ? e.message : String(e);
  } finally {
    pendingDebug.value = false;
  }
}

onMounted(() => {
  void refreshAll().then(() => {
    if (panelMode.value === "user") void loadFromPath();
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

.banner {
  margin: 0;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--accent) 25%, transparent);
  background: var(--accent-soft);
  font-size: 12px;
  color: var(--text);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 0;
}

.left {
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  overflow: auto;
  padding: 12px;
}

.right {
  min-width: 0;
  padding: 12px 16px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.block {
  margin-bottom: 16px;
}

.h {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  margin-bottom: 8px;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.item {
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface);
  margin-bottom: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.item.click {
  cursor: pointer;
  transition: border-color 0.12s ease, box-shadow 0.12s ease;
}

.item.click:hover {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 12%, transparent);
}

.item.click.active {
  border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 55%, var(--surface));
}

.item .hint {
  font-size: 10px;
  color: var(--accent);
  margin-top: 2px;
}

.name {
  font-size: 12px;
  color: var(--text);
}

.meta {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.35;
}

.muted-block .root {
  font-size: 11px;
  color: var(--muted);
  word-break: break-all;
}

.row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.row-gap {
  margin-top: 6px;
}

.row.dbg {
  margin-top: 4px;
}

.lbl {
  font-size: 11px;
  color: var(--muted);
}

.path-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.path-inp {
  flex: 1;
  min-width: 200px;
  max-width: 520px;
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
  max-width: 480px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 12px;
  background: #fff;
}

.area {
  width: 100%;
  max-width: 640px;
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
  max-height: 240px;
  overflow: auto;
  white-space: pre-wrap;
}

@media (max-width: 900px) {
  .body {
    grid-template-columns: 1fr;
  }
  .left {
    border-right: none;
    border-bottom: 1px solid var(--border);
    max-height: 40vh;
  }
}
</style>
