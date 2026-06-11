<template>
  <div class="guide-search">
    <div v-if="pending" class="hint">搜索中…</div>
    <div v-else-if="error" class="hint bad">{{ error }}</div>
    <div v-else-if="query.length >= 2 && results.length === 0" class="hint">未找到与「{{ query }}」相关的内容</div>
    <ul v-else-if="results.length > 0" class="results">
      <li v-for="hit in results" :key="hit.path">
        <button type="button" class="result-btn" @click="emit('select', hit.path)">
          <div class="result-title">{{ hit.title }}</div>
          <div class="result-crumb">{{ hit.breadcrumb }}</div>
          <div class="result-snippet" v-html="highlightSnippet(hit.snippet, query)" />
        </button>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { searchGuideDocs, type GuideSearchHit } from "@/api/guide";

const props = defineProps<{
  query: string;
}>();

const emit = defineEmits<{
  (e: "select", path: string): void;
}>();

const results = ref<GuideSearchHit[]>([]);
const pending = ref(false);
const error = ref<string | null>(null);

let debounceTimer: ReturnType<typeof setTimeout> | null = null;
let requestSeq = 0;

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function highlightSnippet(snippet: string, query: string): string {
  const safe = escapeHtml(snippet);
  const q = query.trim();
  if (!q) return safe;
  const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  return safe.replace(re, "<mark>$1</mark>");
}

async function runSearch(q: string): Promise<void> {
  const seq = ++requestSeq;
  if (q.length < 2) {
    results.value = [];
    error.value = null;
    pending.value = false;
    return;
  }
  pending.value = true;
  error.value = null;
  try {
    const resp = await searchGuideDocs(q);
    if (seq !== requestSeq) return;
    results.value = resp.results;
  } catch (e) {
    if (seq !== requestSeq) return;
    error.value = e instanceof Error ? e.message : "搜索失败";
    results.value = [];
  } finally {
    if (seq === requestSeq) pending.value = false;
  }
}

watch(
  () => props.query,
  (q) => {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      void runSearch(q.trim());
    }, 300);
  },
  { immediate: true },
);
</script>

<style scoped>
.guide-search {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.hint {
  font-size: 13px;
  color: var(--muted);
}

.hint.bad {
  color: var(--danger, #dc2626);
}

.results {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-btn {
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
}

.result-btn:hover {
  border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
}

.result-title {
  font-weight: 600;
  font-size: 14px;
}

.result-crumb {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}

.result-snippet {
  font-size: 12px;
  color: var(--text);
  margin-top: 6px;
  line-height: 1.45;
}

.result-snippet :deep(mark) {
  background: color-mix(in srgb, var(--accent) 30%, transparent);
  color: inherit;
  padding: 0 2px;
  border-radius: 2px;
}
</style>
