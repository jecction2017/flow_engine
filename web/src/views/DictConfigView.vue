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
        <button type="button" class="btn ghost" :disabled="loading" @click="reload">刷新</button>
        <button type="button" class="btn primary" :disabled="saving || loading" @click="saveSubtree">
          {{ saving ? "保存中…" : "保存当前节点 (YAML)" }}
        </button>
        <button type="button" class="btn ghost" :disabled="loading" @click="saveFullFromEditor">
          用右侧内容覆盖整份 dictionary
        </button>
        <button type="button" class="btn ghost danger" :disabled="loading" @click="removeSelected">删除选中</button>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="hint-bar">
      树节点对应点路径（如 <code class="mono">app.http.timeout_sec</code>）。流程 / Starlark 使用
      <code class="mono">dict_get("app.http.timeout_sec")</code>或上下文快照
      <code class="mono">resolve("$.global.dictionary.app.http.timeout_sec")</code>。
    </div>

    <div class="body">
      <aside class="left">
        <button
          type="button"
          class="root-btn"
          :class="{ active: selectedPath === '' }"
          @click="selectPath('')"
        >
          （根）dictionary.yaml
        </button>
        <DictTreeItem
          v-if="treeKeys.length"
          :node="tree"
          :path-prefix="[]"
          :selected-path="selectedPath"
          @select="selectPath"
        />
        <p v-else class="empty">暂无键，可在右侧编辑根 YAML 保存。</p>
      </aside>

      <div class="right">
        <div class="meta">
          <span class="lbl">当前路径</span>
          <code class="mono path">{{ selectedPath || "（根）" }}</code>
        </div>
        <CodeEditor v-model="editorYaml" language="yaml" :height="520" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CodeEditor from "@/components/CodeEditor.vue";
import DictTreeItem from "@/components/DictTreeItem.vue";
import {
  deleteDictSubtree,
  fetchDictDocument,
  fetchDictSubtree,
  saveDictFull,
  saveDictSubtree,
} from "@/api/dict";

const dictDir = ref("");
const tree = ref<Record<string, unknown>>({});
const selectedPath = ref("");
const editorYaml = ref("#加载中…\n");
const loading = ref(false);
const saving = ref(false);
const error = ref("");

const treeKeys = computed(() => Object.keys(tree.value));

async function reload() {
  error.value = "";
  loading.value = true;
  try {
    const doc = await fetchDictDocument();
    dictDir.value = doc.dict_dir;
    tree.value = doc.tree && typeof doc.tree === "object" ? doc.tree : {};
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

async function loadEditorForPath(path: string) {
  error.value = "";
  try {
    const sub = await fetchDictSubtree(path);
    editorYaml.value = sub.yaml ?? "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

function selectPath(path: string) {
  selectedPath.value = path;
}

watch(
  () => selectedPath.value,
  (p) => {
    void loadEditorForPath(p);
  },
  { immediate: true },
);

async function saveSubtree() {
  saving.value = true;
  error.value = "";
  try {
    await saveDictSubtree(selectedPath.value, editorYaml.value);
    await reload();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}

async function saveFullFromEditor() {
  if (!confirm("将用右侧 YAML 完整覆盖 dictionary.yaml 根文档，确定？")) return;
  saving.value = true;
  error.value = "";
  try {
    await saveDictFull(editorYaml.value);
    selectedPath.value = "";
    await reload();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}

async function removeSelected() {
  const p = selectedPath.value;
  const msg = p ? `删除路径「${p}」及其子树？` : "清空整份字典（根）？";
  if (!confirm(msg)) return;
  error.value = "";
  loading.value = true;
  try {
    await deleteDictSubtree(p);
    selectedPath.value = "";
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
