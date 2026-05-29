<template>
  <div class="app-root">
    <nav class="global-nav" aria-label="主视图">
      <button
        v-for="item in navItems"
        :key="item.id"
        type="button"
        class="nav-btn"
        :class="{ active: view === item.id }"
        :aria-current="view === item.id ? 'page' : undefined"
        @click="view = item.id"
      >
        {{ item.label }}
      </button>
    </nav>
    <main class="main-fill">
      <!-- KeepAlive：各主 tab 互不依赖，切换时保留滚动位置与局部 UI 状态，避免整页重建 -->
      <KeepAlive :max="12">
        <component :is="activeView" />
      </KeepAlive>
    </main>
  </div>
</template>

<script setup lang="ts">
import { type Component, computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import FlowStudioView from "./views/FlowStudioView.vue";
import OperationsCenterView from "./views/OperationsCenterView.vue";
import TestCenterView from "./views/TestCenterView.vue";
import CapabilityCenterView from "./views/CapabilityCenterView.vue";
import ProfileConfigView from "./views/ProfileConfigView.vue";
import DictConfigView from "./views/DictConfigView.vue";
import LookupConfigView from "./views/LookupConfigView.vue";
import ScriptGuideView from "./views/ScriptGuideView.vue";

const SESSION_MAIN_VIEW_KEY = "flowEngine:app:sessionMainView";
const TAB_QUERY_KEY = "tab";

type MainViewId = "flow" | "ops" | "test" | "starlark" | "profiles" | "dict" | "lookup" | "guide";

const navItems: { id: MainViewId; label: string }[] = [
  { id: "flow", label: "Flow Studio" },
  { id: "ops", label: "运行中心" },
  { id: "test", label: "测试中心" },
  { id: "starlark", label: "能力与脚本" },
  { id: "profiles", label: "环境配置" },
  { id: "dict", label: "数据字典" },
  { id: "lookup", label: "Lookup" },
  { id: "guide", label: "帮助文档" },
];

const viewComponentById: Record<MainViewId, Component> = {
  flow: FlowStudioView,
  ops: OperationsCenterView,
  test: TestCenterView,
  starlark: CapabilityCenterView,
  profiles: ProfileConfigView,
  dict: DictConfigView,
  lookup: LookupConfigView,
  guide: ScriptGuideView,
};

const allowedIds = new Set<MainViewId>(navItems.map((n) => n.id));

function normalizeMainViewId(raw: string | null | undefined): MainViewId | null {
  if (!raw) return null;
  return allowedIds.has(raw as MainViewId) ? (raw as MainViewId) : null;
}

function readMainViewFromUrl(): MainViewId | null {
  try {
    const url = new URL(window.location.href);
    return normalizeMainViewId(url.searchParams.get(TAB_QUERY_KEY));
  } catch {
    return null;
  }
}

function writeMainViewToUrl(viewId: MainViewId): void {
  try {
    const url = new URL(window.location.href);
    if (url.searchParams.get(TAB_QUERY_KEY) === viewId) return;
    url.searchParams.set(TAB_QUERY_KEY, viewId);
    window.history.replaceState(window.history.state, "", url);
  } catch {
    /* ignore URL API failures */
  }
}

function readSessionMainView(): MainViewId | null {
  try {
    return normalizeMainViewId(sessionStorage.getItem(SESSION_MAIN_VIEW_KEY));
  } catch {
    /* private mode / denied */
  }
  return null;
}

function writeSessionMainView(viewId: MainViewId): void {
  try {
    sessionStorage.setItem(SESSION_MAIN_VIEW_KEY, viewId);
  } catch {
    /* ignore */
  }
}

const view = ref<MainViewId>(readMainViewFromUrl() ?? readSessionMainView() ?? "flow");

writeMainViewToUrl(view.value);
writeSessionMainView(view.value);

watch(view, (v) => {
  writeMainViewToUrl(v);
  writeSessionMainView(v);
});

function handlePopState(): void {
  const viewFromUrl = readMainViewFromUrl();
  if (viewFromUrl && viewFromUrl !== view.value) {
    view.value = viewFromUrl;
  }
}

onMounted(() => {
  window.addEventListener("popstate", handlePopState);
});

onBeforeUnmount(() => {
  window.removeEventListener("popstate", handlePopState);
});

const activeView = computed(() => viewComponentById[view.value]);
</script>

<style scoped>
.app-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.global-nav {
  display: flex;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  flex-shrink: 0;
  box-shadow: var(--shadow);
}

.nav-btn {
  font-family: inherit;
  border: 1px solid transparent;
  background: transparent;
  color: var(--muted);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}

.nav-btn:hover {
  color: var(--text);
  background: color-mix(in srgb, var(--bg) 80%, var(--surface));
}

.nav-btn.active {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  background: var(--accent-soft);
  font-weight: 600;
}

.main-fill {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.main-fill > * {
  flex: 1;
  min-height: 0;
}
</style>
