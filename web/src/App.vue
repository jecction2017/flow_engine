<template>
  <div class="app-root">
    <nav class="global-nav" aria-label="主视图">
      <button type="button" class="nav-btn" :class="{ active: view === 'flow' }" @click="view = 'flow'">
        Flow Studio
      </button>
      <button type="button" class="nav-btn" :class="{ active: view === 'ops' }" @click="view = 'ops'">
        运行中心
      </button>
      <button type="button" class="nav-btn" :class="{ active: view === 'test' }" @click="view = 'test'">
        测试中心
      </button>
      <button type="button" class="nav-btn" :class="{ active: view === 'starlark' }" @click="view = 'starlark'">
        能力与脚本
      </button>
      <button type="button" class="nav-btn" :class="{ active: view === 'profiles' }" @click="view = 'profiles'">
        环境配置
      </button>
      <button type="button" class="nav-btn" :class="{ active: view === 'dict' }" @click="view = 'dict'">
        数据字典
      </button>
      <button type="button" class="nav-btn" :class="{ active: view === 'lookup' }" @click="view = 'lookup'">
        Lookup
      </button>
      <button type="button" class="nav-btn" :class="{ active: view === 'guide' }" @click="view = 'guide'">
        帮助文档
      </button>
    </nav>
    <main class="main-fill">
      <FlowStudioView v-if="view === 'flow'" />
      <OperationsCenterView v-else-if="view === 'ops'" />
      <TestCenterView v-else-if="view === 'test'" />
      <CapabilityCenterView v-else-if="view === 'starlark'" />
      <ProfileConfigView v-else-if="view === 'profiles'" />
      <DictConfigView v-else-if="view === 'dict'" />
      <LookupConfigView v-else-if="view === 'lookup'" />
      <ScriptGuideView v-else />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import FlowStudioView from "./views/FlowStudioView.vue";
import OperationsCenterView from "./views/OperationsCenterView.vue";
import TestCenterView from "./views/TestCenterView.vue";
import CapabilityCenterView from "./views/CapabilityCenterView.vue";
import ProfileConfigView from "./views/ProfileConfigView.vue";
import DictConfigView from "./views/DictConfigView.vue";
import LookupConfigView from "./views/LookupConfigView.vue";
import ScriptGuideView from "./views/ScriptGuideView.vue";

const view = ref<"flow" | "ops" | "test" | "starlark" | "profiles" | "dict" | "lookup" | "guide">("flow");
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
