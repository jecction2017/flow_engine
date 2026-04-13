<template>
  <div class="lookup-page">
    <header class="top">
      <div class="brand">
        <span class="logo">◇</span>
        <div>
          <div class="title">Lookup 表</div>
          <div class="subtitle">
            <span v-if="lookupDir" class="mono dir" :title="lookupDir">{{ lookupDir }}</span>
            <span v-else class="muted">加载中…</span>
          </div>
        </div>
      </div>
      <div class="actions">
        <button type="button" class="btn ghost" :disabled="loading" @click="reload">刷新</button>
        <button type="button" class="btn primary" :disabled="saving || loading || !nsValid" @click="save">
          {{ saving ? "保存中…" : "保存 JSON" }}
        </button>
        <button type="button" class="btn ghost danger" :disabled="loading || !nsValid" @click="removeNs">
          删除命名空间
        </button>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="hint-bar">
      Starlark：
      <code class="mono">lookup_query("apps", {"appid": "demo-001"})</code>
      ；HTTP 调试：
      <code class="mono">GET /api/lookups/apps/query?filter={"appid":"demo-001"}</code>
    </div>

    <div class="body">
      <aside class="left">
        <label class="lbl">命名空间</label>
        <div class="row2">
          <select v-model="selectedNs" class="sel" @change="onPickNs">
            <option value="">新建 / 选择…</option>
            <option v-for="n in namespaces" :key="n" :value="n">{{ n }}</option>
          </select>
        </div>
        <input v-model="namespaceInput" class="inp mono" placeholder="例如 apps、cwe_list" spellcheck="false" />
        <button type="button" class="btn ghost sm" :disabled="loading" @click="loadInputNs">加载输入的名称</button>

        <div class="imp">
          <div class="lbl">导入文件（JSON / CSV / xlsx）</div>
          <select v-model="importMode" class="sel sm">
            <option value="replace">覆盖（replace）</option>
            <option value="append">追加（append）</option>
          </select>
          <select v-model="importFormat" class="sel sm">
            <option value="auto">格式自动</option>
            <option value="json">json</option>
            <option value="csv">csv</option>
            <option value="xlsx">xlsx</option>
          </select>
          <label class="file-lbl btn ghost sm">
            选择文件
            <input hidden type="file" accept=".json,.csv,.xlsx,.xlsm" @change="onFile" />
          </label>
          <span v-if="importHint" class="imp-hint">{{ importHint }}</span>
        </div>
      </aside>

      <div class="right">
        <div class="meta">
          <span class="lbl">文档结构</span>
          <code class="mono path">{ fields: string[], rows: object[] }</code>
        </div>
        <CodeEditor v-model="editorJson" language="json" :height="540" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import CodeEditor from "@/components/CodeEditor.vue";
import {
  deleteLookupTable,
  fetchLookupList,
  fetchLookupTable,
  importLookupFile,
  saveLookupTable,
  type LookupTable,
} from "@/api/lookups";

const NS_RE = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/;

const lookupDir = ref("");
const namespaces = ref<string[]>([]);
const selectedNs = ref("");
const namespaceInput = ref("");
const editorJson = ref('{\n  "fields": [],\n  "rows": []\n}\n');
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const importMode = ref<"replace" | "append">("replace");
const importFormat = ref<"auto" | "json" | "csv" | "xlsx">("auto");
const importHint = ref("");

const activeNs = computed(() => selectedNs.value || namespaceInput.value.trim());

const nsValid = computed(() => NS_RE.test(activeNs.value));

async function reload() {
  error.value = "";
  loading.value = true;
  try {
    const li = await fetchLookupList();
    lookupDir.value = li.lookup_dir;
    namespaces.value = li.namespaces;
    const ns = activeNs.value;
    if (ns && NS_RE.test(ns)) {
      const t = await fetchLookupTable(ns);
      editorJson.value = JSON.stringify(t, null, 2) + "\n";
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function onPickNs() {
  namespaceInput.value = selectedNs.value;
  void reload();
}

function loadInputNs() {
  selectedNs.value = "";
  void reload();
}

async function save() {
  if (!nsValid.value) {
    error.value = "命名空间格式无效";
    return;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(editorJson.value || "{}");
  } catch {
    error.value = "JSON 解析失败";
    return;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    error.value = "根必须是对象";
    return;
  }
  const o = parsed as Record<string, unknown>;
  const rows = o.rows;
  if (!Array.isArray(rows)) {
    error.value = "缺少 rows 数组";
    return;
  }
  const fields = o.fields;
  const table: LookupTable = {
    fields: Array.isArray(fields) ? (fields as string[]) : [],
    rows: rows as Array<Record<string, unknown>>,
  };
  saving.value = true;
  error.value = "";
  try {
    await saveLookupTable(activeNs.value, table);
    importHint.value = "已保存";
    await reload();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}

async function removeNs() {
  const ns = activeNs.value;
  if (!ns || !NS_RE.test(ns)) return;
  if (!confirm(`删除 lookup 命名空间「${ns}」？`)) return;
  loading.value = true;
  error.value = "";
  try {
    await deleteLookupTable(ns);
    selectedNs.value = "";
    namespaceInput.value = "";
    editorJson.value = '{\n  "fields": [],\n  "rows": []\n}\n';
    await reload();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

async function onFile(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (!nsValid.value) {
    error.value = "请先填写有效命名空间";
    return;
  }
  importHint.value = "";
  loading.value = true;
  error.value = "";
  try {
    const res = await importLookupFile(activeNs.value, file, importMode.value, importFormat.value);
    importHint.value = `已导入 ${res.imported} 行（${res.mode}）`;
    await reload();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

void reload();
</script>

<style scoped>
.lookup-page {
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
  padding: 5px 8px;
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
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 0;
}

.left {
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  overflow: auto;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.right {
  min-width: 0;
  padding: 12px 16px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.lbl {
  font-size: 11px;
  color: var(--muted);
}

.row2 {
  display: flex;
  gap: 6px;
}

.sel {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 12px;
  background: #fff;
}

.sel.sm {
  font-size: 11px;
}

.inp {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 8px;
  font-size: 12px;
  background: #fff;
}

.imp {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.file-lbl {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.imp-hint {
  font-size: 11px;
  color: var(--success);
}

.meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.path {
  font-size: 11px;
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
    max-height: 42vh;
  }
}
</style>
