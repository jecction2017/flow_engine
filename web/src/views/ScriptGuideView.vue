<template>
  <div class="guide">
    <header class="topbar">
      <div class="topbar-title">帮助文档</div>
      <div class="topbar-search">
        <input
          v-model="searchInput"
          type="search"
          class="inp search-inp"
          placeholder="搜索帮助文档…"
          aria-label="搜索帮助文档"
        />
      </div>
    </header>

    <aside class="sidebar">
      <div class="sidebar-title">目录</div>
      <div v-if="treeError" class="sidebar-hint bad">{{ treeError }}</div>
      <div v-else-if="treePending" class="sidebar-hint">加载目录…</div>
      <GuideTreeNav
        v-else
        :nodes="treeNodes"
        :active-path="docPath"
        @select="onSelectDoc"
      />
    </aside>

    <main class="content">
      <div v-if="searchActive" class="search-panel">
        <GuideSearch :query="searchInput" @select="onSearchSelect" />
      </div>
      <template v-else>
        <div v-if="docError" class="hint bad">{{ docError }}</div>
        <div v-else-if="docPending" class="hint">加载文档…</div>
        <GuideMarkdown
          v-else-if="docContent"
          :content="docContent"
          :current-path="docPath"
          @navigate="onSelectDoc"
        />
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  fetchGuideDoc,
  fetchGuideTree,
  type GuideTreeNode,
} from "@/api/guide";
import GuideTreeNav from "@/components/guide/GuideTreeNav.vue";
import GuideSearch from "@/components/guide/GuideSearch.vue";
import GuideMarkdown from "@/components/guide/GuideMarkdown.vue";
import { useGuideDocPath } from "@/composables/useGuideDocPath";

const docPath = useGuideDocPath();

const treeNodes = ref<GuideTreeNode[]>([]);
const treePending = ref(true);
const treeError = ref<string | null>(null);

const docContent = ref("");
const docPending = ref(false);
const docError = ref<string | null>(null);

const searchInput = ref("");
const searchActive = computed(() => searchInput.value.trim().length >= 2);

async function loadTree(): Promise<void> {
  treePending.value = true;
  treeError.value = null;
  try {
    const resp = await fetchGuideTree();
    treeNodes.value = resp.children;
  } catch (e) {
    treeError.value = e instanceof Error ? e.message : "加载目录失败";
  } finally {
    treePending.value = false;
  }
}

async function loadDoc(path: string): Promise<void> {
  docPending.value = true;
  docError.value = null;
  try {
    const resp = await fetchGuideDoc(path);
    docContent.value = resp.content;
  } catch (e) {
    docContent.value = "";
    docError.value = e instanceof Error ? e.message : "加载文档失败";
  } finally {
    docPending.value = false;
  }
}

function onSelectDoc(path: string): void {
  searchInput.value = "";
  docPath.value = path;
}

function onSearchSelect(path: string): void {
  searchInput.value = "";
  docPath.value = path;
}

watch(
  docPath,
  (path) => {
    void loadDoc(path);
  },
  { immediate: true },
);

void loadTree();
</script>

<style scoped>
.guide {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  grid-template-rows: auto minmax(0, 1fr);
  height: 100%;
  min-height: 0;
}

.topbar {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

.topbar-title {
  font-weight: 700;
  font-size: 13px;
  flex-shrink: 0;
}

.topbar-search {
  flex: 1;
  display: flex;
  justify-content: flex-end;
}

.search-inp {
  width: 100%;
  max-width: 360px;
}

.sidebar {
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 95%, transparent);
  padding: 12px 10px;
  overflow: auto;
  min-height: 0;
}

.sidebar-title {
  font-weight: 700;
  font-size: 12px;
  margin-bottom: 10px;
  color: var(--muted);
}

.sidebar-hint {
  font-size: 12px;
  color: var(--muted);
}

.content {
  overflow: auto;
  padding: 16px 20px;
  min-height: 0;
}

.search-panel {
  max-width: 720px;
}

.hint {
  font-size: 13px;
  color: var(--muted);
}

.hint.bad,
.sidebar-hint.bad {
  color: var(--danger, #dc2626);
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow);
}

@media (max-width: 980px) {
  .guide {
    grid-template-columns: 1fr;
    grid-template-rows: auto auto minmax(0, 1fr);
  }

  .sidebar {
    border-right: none;
    border-bottom: 1px solid var(--border);
    max-height: 200px;
  }

  .topbar {
    flex-wrap: wrap;
  }

  .search-inp {
    max-width: none;
  }
}
</style>
