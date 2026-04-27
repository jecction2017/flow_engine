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
        <label class="lbl inline">
          <span>Profile</span>
          <select v-model="selectedProfile" class="sel sm" @change="reload">
            <option v-for="p in profileOptions" :key="p" :value="p">{{ p }}</option>
          </select>
        </label>
        <button type="button" class="btn ghost" :disabled="loading" @click="reload">刷新</button>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>
    <div v-if="confirmOpen" class="confirm-mask" @click.self="closeConfirmDialog">
      <div class="confirm-dialog" role="dialog" aria-modal="true" :aria-label="confirmTitle">
        <div class="confirm-title">{{ confirmTitle }}</div>
        <p class="confirm-text">{{ confirmText }}</p>
        <div class="confirm-actions">
          <button type="button" class="btn ghost" @click="closeConfirmDialog">取消</button>
          <button type="button" class="btn ghost danger" @click="confirmDialogAction">确认删除</button>
        </div>
      </div>
    </div>

    <div class="hint-bar">
      Starlark：
      <code class="mono">lookup_query("apps", {"appid": "demo-001"})</code>
      ；HTTP 调试：
      <code class="mono">GET /api/lookups/apps/query?filter={"appid":"demo-001"}</code>
    </div>

    <div class="body">
      <aside class="left">
        <div class="search-box">
          <input
            v-model="searchQuery"
            class="search-input mono"
            type="text"
            placeholder="搜索命名空间..."
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

        <div class="section-title">
          <span>命名空间</span>
          <button type="button" class="link" @click="startNew">新增</button>
        </div>
        <button
          v-for="n in filteredNamespaces"
          :key="n"
          type="button"
          class="module-btn"
          :class="{ active: activeNs === n && !isNew }"
          @click="pickNamespace(n)"
        >
          <span class="mono">{{ n }}</span>
        </button>
        <p v-if="!filteredNamespaces.length" class="empty">暂无匹配的命名空间</p>
      </aside>

      <div class="right">
        <template v-if="isNew">
          <div class="meta" style="margin-bottom: 16px;">
            <span class="lbl">新建命名空间</span>
            <input v-model="newNamespaceInput" class="inp mono" placeholder="例如 apps、cwe_list" spellcheck="false" style="max-width: 300px;" />
            <button type="button" class="btn primary" :disabled="!newNsValid || saving" @click="createNamespace">
              创建并保存
            </button>
          </div>
          
          <div class="new-options">
            <div class="new-option-card">
              <h4>1. 定义 JSON Schema (可选)</h4>
              <p class="muted" style="font-size: 11px; margin-bottom: 8px;">定义数据结构，支持标准的 JSON Schema 格式。</p>
              <CodeEditor v-model="newSchemaJson" language="json" :height="200" />
            </div>
            
            <div class="new-option-card">
              <h4>2. 初始数据 (可选)</h4>
              <div class="tabs" style="margin-bottom: 8px;">
                <button class="tab" :class="{ active: newInitMode === 'paste' }" @click="newInitMode = 'paste'">粘贴 JSON</button>
                <button class="tab" :class="{ active: newInitMode === 'upload' }" @click="newInitMode = 'upload'">上传文件</button>
              </div>
              
              <div v-if="newInitMode === 'paste'">
                <p class="muted" style="font-size: 11px; margin-bottom: 8px;">粘贴包含对象数组的 JSON 文本。</p>
                <CodeEditor v-model="newRowsJson" language="json" :height="200" />
              </div>
              
              <div v-if="newInitMode === 'upload'" class="upload-area">
                <p class="muted" style="font-size: 11px; margin-bottom: 12px;">支持 .json, .csv, .xlsx 格式文件。</p>
                <label class="btn ghost">
                  选择文件并导入
                  <input hidden type="file" accept=".json,.csv,.xlsx,.xlsm" @change="onNewFile" />
                </label>
                <div v-if="newFile" style="margin-top: 8px; font-size: 12px;">
                  已选择: {{ newFile.name }}
                </div>
              </div>
            </div>
          </div>
        </template>
        
        <template v-else-if="activeNs">
          <div class="meta">
            <span class="lbl">当前命名空间</span>
            <span class="mono path">{{ activeNs }}</span>
            <button type="button" class="btn ghost danger" :disabled="loading" @click="removeNs">
              删除
            </button>
            <div class="meta-actions">
              <button type="button" class="btn ghost" @click="downloadJson">
                导出 JSON
              </button>
              <span class="lbl">导入:</span>
              <select v-model="importMode" class="sel sm">
                <option value="replace">覆盖</option>
                <option value="append">追加</option>
              </select>
              <label class="file-lbl btn ghost sm">
                选择文件
                <input hidden type="file" accept=".json,.csv,.xlsx,.xlsm" @change="onFile" />
              </label>
              <span v-if="importHint" class="imp-hint">{{ importHint }}</span>
            </div>
          </div>

          <div class="tabs">
            <button class="tab" :class="{ active: activeTab === 'content' }" @click="activeTab = 'content'">数据内容 (Rows)</button>
            <button class="tab" :class="{ active: activeTab === 'structure' }" @click="activeTab = 'structure'">结构定义 (JSON Schema)</button>
          </div>

          <div v-if="activeTab === 'structure'" class="tab-pane">
            <p class="muted" style="font-size: 11px; margin-bottom: 8px;">
              使用标准的 JSON Schema 定义数据结构。后端在保存时会进行校验。
            </p>
            <div class="meta">
              <button type="button" class="btn primary" :disabled="saving || loading" @click="saveSchema">
                {{ saving ? "保存中..." : "保存结构定义" }}
              </button>
            </div>
            <CodeEditor v-model="editorSchemaJson" language="json" :height="500" />
          </div>

          <div v-if="activeTab === 'content'" class="tab-pane">
            <div class="filter-toolbar single-row">
              <div class="toolbar-item toolbar-main-left">
                <div class="search-wrap">
                  <input 
                    v-model="rowSearchInput" 
                    @input="onSearchInput"
                    @keydown="onSearchKeyDown"
                    @focus="onSearchFocus"
                    @blur="onSearchBlur"
                    class="inp sm mono"
                    :class="{ 'search-submitted': searchSubmittedPulse }"
                    placeholder="输入过滤表达式，如: appid == 'demo-001' && owner in ['platform','risk']"
                    style="width: 100%; padding-right: 86px;"
                  />
                  <span v-if="filterError" class="filter-err" :title="filterError">⚠️</span>
                  <select class="filter-preset-select" @change="onPresetChange">
                    <option value="">预设</option>
                    <option v-for="item in presetFilters" :key="item.label" :value="item.expr">{{ item.label }}</option>
                  </select>
                  <ul v-if="showAutocomplete && autocompleteItems.length > 0" class="autocomplete-list">
                    <li 
                      v-for="(item, i) in autocompleteItems" 
                      :key="i"
                      :class="{ active: i === autocompleteIndex }"
                      @mousedown.prevent="selectAutocomplete(item)"
                    >
                      <span class="ac-type">{{ item.type }}</span>
                      <span class="ac-val">{{ item.value }}</span>
                    </li>
                  </ul>
                </div>
                <div class="search-actions">
                <InfoTip text="支持: ==, !=, >, >=, <, <=, in [], not in [], &&, ||" />
                <button
                  type="button"
                  class="btn ghost sm"
                  :disabled="loading || (!rowSearchInput.trim() && !rowSearchQuery.trim())"
                  @click="clearFilter"
                >
                  清空过滤
                </button>
                </div>
              </div>
              <div class="toolbar-item toolbar-main-right">
                <button
                  type="button"
                  class="btn ghost danger sm"
                  :disabled="loading || selectedCount === 0"
                  @click="deleteSelectedRows"
                >
                  批量删除（{{ selectedCount }}）
                </button>
                <button
                  type="button"
                  class="btn ghost danger sm"
                  :disabled="loading || totalRows === 0"
                  @click="deleteByCurrentFilter"
                >
                  按过滤全量删除
                </button>
              </div>
              </div>

            <div class="table-wrap" style="flex: 1; min-height: 0; overflow: auto;">
              <table class="data-table rows-table">
                <thead>
                  <tr>
                    <th style="width: 36px">
                      <input
                        type="checkbox"
                        :checked="allPageRowsSelected"
                        :disabled="!paginatedRows.length"
                        @change="togglePageSelection(($event.target as HTMLInputElement).checked)"
                      />
                    </th>
                    <th v-for="f in dynamicFields" :key="f">{{ f }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in paginatedRows" :key="idx">
                    <td>
                      <input
                        type="checkbox"
                        :checked="isRowSelected(row)"
                        @change="toggleRowSelection(row, ($event.target as HTMLInputElement).checked)"
                      />
                    </td>
                    <td v-for="f in dynamicFields" :key="f">
                      <span class="cell-text" :title="getCellValue(row, f)">{{ getCellValue(row, f) }}</span>
                    </td>
                  </tr>
                  <tr v-if="!paginatedRows.length">
                    <td :colspan="dynamicFields.length + 1" class="empty text-center">暂无数据</td>
                  </tr>
                </tbody>
              </table>
            </div>
            
            <div class="pagination">
              <button class="btn sm ghost" @click="page--" :disabled="page <= 1">上一页</button>
              <span class="lbl">第 {{ page }} / {{ totalPages || 1 }} 页 (共 {{ totalRows }} 行)</span>
              <button class="btn sm ghost" @click="page++" :disabled="page >= totalPages">下一页</button>
            </div>
            <p class="muted" style="font-size: 11px;">
              数据内容为只读，支持当前页批量删除、按过滤全量删除。
            </p>
          </div>
        </template>
        
        <template v-else>
          <div class="empty-state">请在左侧选择或新建命名空间</div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CodeEditor from "@/components/CodeEditor.vue";
import InfoTip from "@/components/InfoTip.vue";
import {
  deleteLookupRows,
  deleteLookupRowsByFilter,
  deleteLookupTable,
  fetchLookupList,
  importLookupFile,
  queryLookupTable,
  saveLookupSchema,
  saveLookupTable,
  type LookupTable,
} from "@/api/lookups";
import { fetchProfileConfig } from "@/api/profiles";

const NS_RE = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/;
const FILTER_FIELD_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

const lookupDir = ref("");
const namespaces = ref<string[]>([]);
const searchQuery = ref("");
const activeNs = ref("");
const isNew = ref(false);

const newNamespaceInput = ref("");
const newSchemaJson = ref('{\n  "type": "object",\n  "properties": {}\n}');
const newRowsJson = ref('[]');
const newInitMode = ref<"paste" | "upload">("paste");
const newFile = ref<File | null>(null);

const activeTab = ref<"structure" | "content">("content");

const schema = ref<Record<string, unknown>>({});
const rows = ref<Array<Record<string, unknown>>>([]);
const editorSchemaJson = ref('{}');

const profileOptions = ref<string[]>(["default"]);
const selectedProfile = ref("default");
const loading = ref(false);
const saving = ref(false);
const error = ref("");

const importMode = ref<"replace" | "append">("replace");
const importFormat = ref<"auto">("auto");
const importHint = ref("");

const rowSearchInput = ref("");
const rowSearchQuery = ref("");
const filterError = ref("");
const page = ref(1);
const pageSize = 50;
const totalRows = ref(0);
const selectedRowKeys = ref<Set<string>>(new Set());

const showAutocomplete = ref(false);
const autocompleteIndex = ref(0);
const autocompleteItems = ref<{type: string, value: string}[]>([]);
const searchSubmittedPulse = ref(false);
const confirmOpen = ref(false);
const confirmTitle = ref("确认操作");
const confirmText = ref("");
const pendingConfirmAction = ref<null | "deleteSelectedRows" | "deleteByFilter" | "removeNamespace">(null);
const pendingRowsToDelete = ref<Array<Record<string, unknown>>>([]);
const pendingDeleteFilter = ref("");
const pendingRemoveNs = ref("");
let searchTimer: ReturnType<typeof setTimeout> | null = null;
let submitPulseTimer: ReturnType<typeof setTimeout> | null = null;
let activeQueryAbort: AbortController | null = null;
let activeQueryId = 0;

function onSearchInput(ev: Event) {
  const target = ev.target as HTMLInputElement;
  const val = target.value;
  const cursor = target.selectionStart || 0;
  updateAutocomplete(val, cursor);
}

function onSearchFocus(ev: Event) {
  const target = ev.target as HTMLInputElement;
  updateAutocomplete(target.value, target.selectionStart || 0);
}

function updateAutocomplete(val: string, cursor: number) {
  const textBefore = val.substring(0, cursor);
  const match = textBefore.match(/([a-zA-Z0-9_]+)$/);
  
  const items: {type: string, value: string}[] = [];
  
  if (match) {
    const word = match[1].toLowerCase();
    for (const f of dynamicFields.value) {
      if (f.toLowerCase().includes(word) && f !== match[1]) {
        items.push({ type: "field", value: f });
      }
    }
    const keywords = ["in", "not in", "&&", "||"];
    for (const k of keywords) {
      if (k.startsWith(word) && k !== match[1]) {
        items.push({ type: "keyword", value: k });
      }
    }
  } else {
    if (textBefore.endsWith(" ") || textBefore === "") {
      for (const f of dynamicFields.value) {
        items.push({ type: "field", value: f });
      }
      items.push({ type: "tmpl", value: "== ''" });
      items.push({ type: "tmpl", value: "!= ''" });
      items.push({ type: "tmpl", value: ">= 0" });
      items.push({ type: "tmpl", value: "<= 0" });
      items.push({ type: "tmpl", value: "> 0" });
      items.push({ type: "tmpl", value: "< 0" });
      items.push({ type: "tmpl", value: "in ['']" });
      items.push({ type: "tmpl", value: "not in ['']" });
      items.push({ type: "keyword", value: "in" });
      items.push({ type: "keyword", value: "not in" });
      items.push({ type: "op", value: "&&" });
      items.push({ type: "op", value: "||" });
    }
  }
  
  autocompleteItems.value = items.slice(0, 10);
  autocompleteIndex.value = 0;
  showAutocomplete.value = items.length > 0;
}

function onSearchKeyDown(ev: KeyboardEvent) {
  if (ev.key === "Enter") {
    const raw = rowSearchInput.value;
    // Empty/whitespace means "search all", even if autocomplete suggestions are shown.
    if (!raw.trim()) {
      ev.preventDefault();
      showAutocomplete.value = false;
      submitSearch();
      return;
    }
  }

  if (ev.key === "Enter" && (!showAutocomplete.value || autocompleteItems.value.length === 0)) {
    ev.preventDefault();
    submitSearch();
    return;
  }

  if (!showAutocomplete.value || autocompleteItems.value.length === 0) return;
  
  if (ev.key === "ArrowDown") {
    ev.preventDefault();
    autocompleteIndex.value = (autocompleteIndex.value + 1) % autocompleteItems.value.length;
  } else if (ev.key === "ArrowUp") {
    ev.preventDefault();
    autocompleteIndex.value = (autocompleteIndex.value - 1 + autocompleteItems.value.length) % autocompleteItems.value.length;
  } else if (ev.key === "Enter" || ev.key === "Tab") {
    ev.preventDefault();
    selectAutocomplete(autocompleteItems.value[autocompleteIndex.value]);
  } else if (ev.key === "Escape") {
    showAutocomplete.value = false;
  }
}

function selectAutocomplete(item: {type: string, value: string}) {
  const target = document.querySelector('.search-wrap input') as HTMLInputElement;
  if (!target) return;
  
  const val = rowSearchInput.value;
  const cursor = target.selectionStart || 0;
  const textBefore = val.substring(0, cursor);
  const textAfter = val.substring(cursor);
  
  const match = textBefore.match(/([a-zA-Z0-9_]+)$/);
  let newBefore = textBefore;
  if (match) {
    newBefore = textBefore.substring(0, textBefore.length - match[1].length);
  }
  
  const insertText = item.value + " ";
  rowSearchInput.value = newBefore + insertText + textAfter;
  showAutocomplete.value = false;
  
  setTimeout(() => {
    target.focus();
    const newPos = newBefore.length + insertText.length;
    target.setSelectionRange(newPos, newPos);
  }, 0);
}

function onSearchBlur() {
  setTimeout(() => {
    showAutocomplete.value = false;
  }, 200);
}

const filteredNamespaces = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return namespaces.value;
  return namespaces.value.filter((n) => n.toLowerCase().includes(q));
});

const newNsValid = computed(() => NS_RE.test(newNamespaceInput.value.trim()));

const dynamicFields = computed(() => {
  const fields = new Set<string>();
  // Extract from schema properties if available
  if (schema.value?.properties && typeof schema.value.properties === 'object') {
    Object.keys(schema.value.properties).forEach(k => fields.add(k));
  }
  // Extract from current page rows
  for (const r of rows.value) {
    Object.keys(r).forEach(k => fields.add(k));
  }
  return Array.from(fields);
});

const totalPages = computed(() => Math.max(1, Math.ceil(totalRows.value / pageSize)));
const paginatedRows = computed(() => rows.value);
const selectedCount = computed(() => selectedRowKeys.value.size);
const presetFilters = computed(() => {
  const out: Array<{ label: string; expr: string }> = [];
  const fields = new Set(dynamicFields.value);
  if (fields.has("status")) {
    out.push({ label: "状态=1", expr: "status == 1" });
    out.push({ label: "状态=0", expr: "status == 0" });
  }
  if (fields.has("owner")) {
    out.push({ label: "owner=platform", expr: "owner == 'platform'" });
  }
  if (fields.has("appid")) {
    out.push({ label: "示例 appid", expr: "appid == 'demo-001'" });
  }
  return out;
});

watch(rowSearchQuery, () => {
  page.value = 1;
  void refreshPage();
});

watch(page, () => {
  void refreshPage();
});

watch([activeNs, rowSearchQuery, page], () => {
  selectedRowKeys.value = new Set();
});

async function reload() {
  error.value = "";
  loading.value = true;
  try {
    const li = await fetchLookupList(selectedProfile.value);
    lookupDir.value = li.lookup_dir;
    namespaces.value = li.namespaces;
    
    if (activeNs.value && namespaces.value.includes(activeNs.value)) {
      await loadTable(activeNs.value);
    } else if (namespaces.value.length > 0 && !isNew.value) {
      await pickNamespace(namespaces.value[0]);
    } else if (!isNew.value) {
      activeNs.value = "";
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

async function loadTable(ns: string) {
  await refreshPage();
}

function validateFilterExpr(raw: string): string | null {
  const isPrimitiveLiteral = (rhs: string): boolean => {
    const t = rhs.trim();
    if (!t) return false;
    if ((t.startsWith("'") && t.endsWith("'")) || (t.startsWith('"') && t.endsWith('"'))) return true;
    if (/^-?\d+(\.\d+)?$/.test(t)) return true;
    if (t === "true" || t === "false" || t === "null") return true;
    return false;
  };

  const groups = raw.split("||").map((x) => x.trim()).filter(Boolean);
  if (!groups.length) return null;
  for (const group of groups) {
    const clauses = group.split("&&").map((x) => x.trim()).filter(Boolean);
    for (const c of clauses) {
      if (c.includes(" not in ")) {
        const [field, rhs] = c.split(" not in ", 2);
        if (!FILTER_FIELD_RE.test(field.trim())) return `字段名不合法: ${field.trim()}`;
        const listText = (rhs || "").trim();
        if (!listText.startsWith("[") || !listText.endsWith("]")) {
          return `'not in' 右侧必须是列表，如 ['a','b']`;
        }
        try {
          const parsed = JSON.parse(listText.replace(/'/g, '"'));
          if (!Array.isArray(parsed)) return `'not in' 右侧必须是列表，如 ['a','b']`;
        } catch {
          return `'not in' 列表格式不合法；字符串请使用引号，如 ['a','b']`;
        }
        continue;
      }
      if (c.includes(" in ")) {
        const [field, rhs] = c.split(" in ", 2);
        if (!FILTER_FIELD_RE.test(field.trim())) return `字段名不合法: ${field.trim()}`;
        const listText = (rhs || "").trim();
        if (!listText.startsWith("[") || !listText.endsWith("]")) {
          return `'in' 右侧必须是列表，如 ['a','b']`;
        }
        try {
          const parsed = JSON.parse(listText.replace(/'/g, '"'));
          if (!Array.isArray(parsed)) return `'in' 右侧必须是列表，如 ['a','b']`;
        } catch {
          return `'in' 列表格式不合法；字符串请使用引号，如 ['a','b']`;
        }
        continue;
      }
      let handled = false;
      for (const token of ["==", "!=", ">=", "<=", ">", "<"]) {
        if (c.includes(token)) {
          const [field, rhs] = c.split(token, 2);
          const fieldName = field.trim();
          const rhsText = (rhs || "").trim();
          if (!FILTER_FIELD_RE.test(fieldName)) return `字段名不合法: ${fieldName}`;
          if (!rhsText) return `'${token}' 右侧不能为空`;
          // Prevent backend parse/runtime errors from bare identifiers like: appid == appid
          // If users mean literal string, require quotes: appid == 'appid'
          if (FILTER_FIELD_RE.test(rhsText) && !isPrimitiveLiteral(rhsText)) {
            return `右侧值 "${rhsText}" 需要加引号；如匹配字符串请写为 '${rhsText}'`;
          }
          if (!isPrimitiveLiteral(rhsText) && !FILTER_FIELD_RE.test(rhsText)) {
            return `右侧值格式不支持: ${rhsText}`;
          }
          handled = true;
          break;
        }
      }
      if (!handled) {
        return `不支持的子句: ${c}`;
      }
    }
  }
  return null;
}

function parsedFilterFromInput(): string | null {
  const raw = rowSearchQuery.value.trim();
  if (!raw) {
    filterError.value = "";
    return "";
  }
  const err = validateFilterExpr(raw);
  if (err) {
    filterError.value = err;
    return null;
  }
  filterError.value = "";
  return raw;
}

async function refreshPage() {
  if (!activeNs.value) return;
  const filter = parsedFilterFromInput();
  if (filter === null) {
    rows.value = [];
    totalRows.value = 0;
    return;
  }
  if (activeQueryAbort) {
    activeQueryAbort.abort();
  }
  const requestId = ++activeQueryId;
  activeQueryAbort = new AbortController();
  const offset = (page.value - 1) * pageSize;
  try {
    const res = await queryLookupTable(activeNs.value, {
      profile: selectedProfile.value,
      filter,
      offset,
      limit: pageSize,
      signal: activeQueryAbort.signal,
    });
    if (requestId !== activeQueryId) {
      return;
    }
    schema.value = (res.schema || { type: "object", properties: {} }) as Record<string, unknown>;
    rows.value = res.rows || [];
    totalRows.value = res.total || 0;
    editorSchemaJson.value = JSON.stringify(schema.value, null, 2) + "\n";
    if (page.value > totalPages.value) {
      page.value = totalPages.value;
    }
  } catch (e) {
    if ((e as Error).name === "AbortError") {
      return;
    }
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    if (requestId === activeQueryId) {
      activeQueryAbort = null;
    }
  }
}

async function pickNamespace(ns: string) {
  if (!ns) return;
  isNew.value = false;
  activeNs.value = ns;
  page.value = 1;
  rowSearchInput.value = "";
  rowSearchQuery.value = "";
  importHint.value = "";
  error.value = "";
  loading.value = true;
  try {
    await loadTable(ns);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function startNew() {
  isNew.value = true;
  activeNs.value = "";
  newNamespaceInput.value = "";
  newSchemaJson.value = '{\n  "type": "object",\n  "properties": {}\n}';
  newRowsJson.value = '[]';
  newFile.value = null;
  rowSearchInput.value = "";
  rowSearchQuery.value = "";
}

function onNewFile(ev: Event) {
  const input = ev.target as HTMLInputElement;
  if (input.files && input.files.length > 0) {
    newFile.value = input.files[0];
  }
}

async function createNamespace() {
  const ns = newNamespaceInput.value.trim();
  if (!ns || !NS_RE.test(ns)) return;
  
  saving.value = true;
  error.value = "";
  
  try {
    let parsedSchema: Record<string, unknown> = { type: "object", properties: {} };
    try {
      parsedSchema = JSON.parse(newSchemaJson.value);
    } catch {
      // ignore schema parse error, use default
    }
    
    let initialRows: Array<Record<string, unknown>> = [];
    
    if (newInitMode.value === 'paste') {
      try {
        const parsedRows = JSON.parse(newRowsJson.value);
        if (Array.isArray(parsedRows)) {
          initialRows = parsedRows;
        }
      } catch {
        throw new Error("粘贴的 JSON 数据格式无效，必须是对象数组");
      }
      
      const table: LookupTable = {
        schema: parsedSchema,
        rows: initialRows,
      };
      
      await saveLookupTable(ns, table, selectedProfile.value);
      
    } else if (newInitMode.value === 'upload' && newFile.value) {
      // First save empty table with schema
      const table: LookupTable = {
        schema: parsedSchema,
        rows: [],
      };
      await saveLookupTable(ns, table, selectedProfile.value);
      
      // Then import file
      await importLookupFile(ns, newFile.value, "replace", "auto", selectedProfile.value);
    } else {
      // Just save schema
      const table: LookupTable = {
        schema: parsedSchema,
        rows: [],
      };
      await saveLookupTable(ns, table, selectedProfile.value);
    }
    
    isNew.value = false;
    activeNs.value = ns;
    await reload();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}

function getCellValue(row: Record<string, unknown>, fieldName: string): string {
  const val = row[fieldName];
  if (val === null || val === undefined) return "";
  if (typeof val === "object") return JSON.stringify(val);
  return String(val);
}

function rowKey(row: Record<string, unknown>): string {
  return JSON.stringify(row);
}

function isRowSelected(row: Record<string, unknown>): boolean {
  return selectedRowKeys.value.has(rowKey(row));
}

function toggleRowSelection(row: Record<string, unknown>, checked: boolean): void {
  const key = rowKey(row);
  const next = new Set(selectedRowKeys.value);
  if (checked) {
    next.add(key);
  } else {
    next.delete(key);
  }
  selectedRowKeys.value = next;
}

function togglePageSelection(checked: boolean): void {
  const next = new Set(selectedRowKeys.value);
  for (const row of paginatedRows.value) {
    const key = rowKey(row);
    if (checked) {
      next.add(key);
    } else {
      next.delete(key);
    }
  }
  selectedRowKeys.value = next;
}

const allPageRowsSelected = computed(
  () => paginatedRows.value.length > 0 && paginatedRows.value.every((row) => isRowSelected(row)),
);

async function deleteRows(rowsToDelete: Array<Record<string, unknown>>): Promise<void> {
  if (!activeNs.value || rowsToDelete.length === 0) return;
  loading.value = true;
  error.value = "";
  try {
    await deleteLookupRows(activeNs.value, rowsToDelete, selectedProfile.value);
    selectedRowKeys.value = new Set();
    await refreshPage();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function openConfirmDialog(
  action: "deleteSelectedRows" | "deleteByFilter" | "removeNamespace",
  title: string,
  text: string,
): void {
  pendingConfirmAction.value = action;
  confirmTitle.value = title;
  confirmText.value = text;
  confirmOpen.value = true;
}

function closeConfirmDialog(): void {
  confirmOpen.value = false;
}

async function confirmDialogAction(): Promise<void> {
  const action = pendingConfirmAction.value;
  confirmOpen.value = false;
  pendingConfirmAction.value = null;
  if (!action) return;

  if (action === "deleteSelectedRows") {
    const chosen = pendingRowsToDelete.value;
    pendingRowsToDelete.value = [];
    if (!chosen.length) return;
    await deleteRows(chosen);
    return;
  }

  if (action === "deleteByFilter") {
    await executeDeleteByFilter(pendingDeleteFilter.value);
    pendingDeleteFilter.value = "";
    return;
  }

  if (action === "removeNamespace") {
    await executeRemoveNs(pendingRemoveNs.value);
    pendingRemoveNs.value = "";
  }
}

async function deleteSelectedRows(): Promise<void> {
  const chosen = paginatedRows.value.filter((row) => isRowSelected(row));
  if (!chosen.length) return;
  pendingRowsToDelete.value = chosen;
  openConfirmDialog("deleteSelectedRows", "确认批量删除", `确认删除当前页选中的 ${chosen.length} 条数据吗？`);
}

async function deleteByCurrentFilter(): Promise<void> {
  if (!activeNs.value) return;
  const filter = parsedFilterFromInput();
  if (filter === null) return;
  const hasFilter = filter.trim().length > 0;
  const text = hasFilter
    ? `确认删除所有匹配当前过滤条件的数据吗？预计影响 ${totalRows.value} 条。`
    : `当前过滤为空，将删除此命名空间的全部 ${totalRows.value} 条数据，确认继续吗？`;
  pendingDeleteFilter.value = filter;
  openConfirmDialog("deleteByFilter", "确认删除数据", text);
}

async function executeDeleteByFilter(filter: string): Promise<void> {
  if (!activeNs.value) return;
  loading.value = true;
  error.value = "";
  try {
    await deleteLookupRowsByFilter(activeNs.value, filter, selectedProfile.value);
    selectedRowKeys.value = new Set();
    page.value = 1;
    await refreshPage();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function applyPreset(expr: string): void {
  rowSearchInput.value = expr;
  submitSearch();
}

function onPresetChange(ev: Event): void {
  const val = (ev.target as HTMLSelectElement).value;
  if (!val) return;
  applyPreset(val);
  (ev.target as HTMLSelectElement).value = "";
}

function clearFilter(): void {
  rowSearchInput.value = "";
  submitSearch();
}

function submitSearch(): void {
  if (searchTimer) {
    clearTimeout(searchTimer);
    searchTimer = null;
  }
  const nextQuery = rowSearchInput.value;
  const changed = rowSearchQuery.value !== nextQuery;
  rowSearchQuery.value = nextQuery;
  if (!changed) {
    page.value = 1;
    void refreshPage();
  }
  if (submitPulseTimer) {
    clearTimeout(submitPulseTimer);
  }
  searchSubmittedPulse.value = true;
  submitPulseTimer = setTimeout(() => {
    searchSubmittedPulse.value = false;
    submitPulseTimer = null;
  }, 200);
}

async function saveSchema(): Promise<void> {
  if (!activeNs.value) return;
  let parsedSchema: Record<string, unknown>;
  try {
    parsedSchema = JSON.parse(editorSchemaJson.value);
  } catch (e) {
    error.value = `JSON Schema 解析失败: ${e instanceof Error ? e.message : String(e)}`;
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    await saveLookupSchema(activeNs.value, parsedSchema, selectedProfile.value);
    importHint.value = "结构定义已保存";
    await refreshPage();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}

async function removeNs() {
  const ns = activeNs.value;
  if (!ns || !NS_RE.test(ns)) return;
  pendingRemoveNs.value = ns;
  openConfirmDialog("removeNamespace", "确认删除命名空间", `删除 lookup 命名空间「${ns}」？`);
}

async function executeRemoveNs(ns: string) {
  if (!ns || !NS_RE.test(ns)) return;
  loading.value = true;
  error.value = "";
  try {
    await deleteLookupTable(ns, selectedProfile.value);
    activeNs.value = "";
    isNew.value = false;
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
  if (!activeNs.value || !NS_RE.test(activeNs.value)) {
    error.value = "请先填写有效命名空间";
    return;
  }
  importHint.value = "";
  loading.value = true;
  error.value = "";
  try {
    const res = await importLookupFile(activeNs.value, file, importMode.value, importFormat.value, selectedProfile.value);
    importHint.value = `已导入 ${res.imported} 行（${res.mode}）`;
    await reload();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function downloadJson() {
  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify({ schema: schema.value, rows: paginatedRows.value, page: page.value, total: totalRows.value }, null, 2));
  const downloadAnchorNode = document.createElement('a');
  downloadAnchorNode.setAttribute("href", dataStr);
  downloadAnchorNode.setAttribute("download", `${activeNs.value}.json`);
  document.body.appendChild(downloadAnchorNode);
  downloadAnchorNode.click();
  downloadAnchorNode.remove();
}

void (async () => {
  try {
    const cfg = await fetchProfileConfig();
    profileOptions.value = cfg.profiles.length ? cfg.profiles : ["default"];
    selectedProfile.value = cfg.default_profile || profileOptions.value[0] || "default";
  } catch {
    // fallback default
  }
  await reload();
})();
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

.inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
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
}

.module-btn:hover {
  background: color-mix(in srgb, var(--accent-soft) 50%, transparent);
}

.module-btn.active {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: var(--accent-soft);
}

.empty {
  font-size: 12px;
  color: var(--muted);
}

.text-center {
  text-align: center;
}

.right {
  min-width: 0;
  padding: 12px 16px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--muted);
  font-size: 14px;
}

.meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.meta-actions {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
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

.tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}

.tab {
  border: none;
  background: transparent;
  padding: 8px 16px;
  font-size: 13px;
  color: var(--muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
}

.tab:hover {
  color: var(--text);
}

.tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  font-weight: 600;
}

.tab-pane {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
  min-height: 0;
}

.filter-toolbar {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-toolbar.single-row {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  overflow: visible;
  padding-bottom: 2px;
}

.toolbar-item {
  flex: 0 0 auto;
}

.search-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.ops-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.search-wrap {
  flex: 1 1 auto;
  min-width: 240px;
  position: relative;
  display: flex;
  align-items: center;
}

.toolbar-main-left {
  flex: 1 1 auto;
  min-width: 360px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-main-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.search-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.filter-err {
  position: absolute;
  right: 64px;
  font-size: 12px;
  cursor: help;
}

.filter-preset-select {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  width: 52px;
  height: 20px;
  font-size: 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  color: var(--muted);
  padding: 0 6px;
}

.autocomplete-list {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin: 4px 0 0 0;
  padding: 4px 0;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  list-style: none;
  z-index: 100;
  max-height: 200px;
  overflow-y: auto;
}

.autocomplete-list li {
  padding: 6px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 12px;
  font-family: var(--mono), monospace;
}

.autocomplete-list li:hover, .autocomplete-list li.active {
  background: color-mix(in srgb, var(--accent-soft) 50%, transparent);
}

.ac-type {
  font-size: 10px;
  color: var(--muted);
  background: color-mix(in srgb, var(--surface) 80%, transparent);
  padding: 2px 4px;
  border-radius: 4px;
  width: 40px;
  text-align: center;
}

.ac-val {
  color: var(--text);
  font-weight: 500;
}

.imp-inline {
  display: flex;
  align-items: center;
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

.filter-inline-hint {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
}

.filter-inline-hint code {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 4px;
  background: #fff8;
}

.table-wrap {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  overflow: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.data-table th,
.data-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}

.data-table th {
  background: color-mix(in srgb, var(--surface) 50%, transparent);
  font-weight: 600;
  color: var(--muted);
  position: sticky;
  top: 0;
  z-index: 1;
}

.data-table tbody tr:last-child td {
  border-bottom: none;
}

.data-table tbody tr:hover {
  background: color-mix(in srgb, var(--surface) 30%, transparent);
}

.rows-table th,
.rows-table td {
  white-space: nowrap;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cell-text {
  display: inline-block;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pagination {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.sel {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  background: #fff;
}

.sel.sm {
  font-size: 11px;
  padding: 4px 6px;
}

.inp {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  background: #fff;
}

.inp.sm {
  padding: 4px 6px;
  font-size: 11px;
}

.inp:focus, .sel:focus {
  outline: none;
  border-color: var(--accent);
}

.inp.search-submitted {
  border-color: color-mix(in srgb, var(--accent) 70%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent-soft) 80%, transparent);
  transition: box-shadow 0.16s ease, border-color 0.16s ease;
}

.new-options {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.new-option-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  background: #fff;
}

.new-option-card h4 {
  margin: 0 0 4px 0;
  font-size: 13px;
  color: var(--text);
}

.upload-area {
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 24px;
  text-align: center;
  background: color-mix(in srgb, var(--surface) 50%, transparent);
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
  .toolbar-main-left {
    min-width: 0;
    width: 100%;
    flex-wrap: wrap;
  }
  .toolbar-main-right {
    width: 100%;
    justify-content: flex-end;
  }
  .meta-actions {
    width: 100%;
    margin-left: 0;
  }
}
</style>
