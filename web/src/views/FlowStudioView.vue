<template>
  <div class="studio">
    <header class="top">
      <div class="brand">
        <span class="logo">◇</span>
        <div>
          <div class="title">Flow Studio</div>
          <div class="subtitle">流程拓扑 · 策略 · 节点调试</div>
        </div>
      </div>
      <div class="actions">
        <button type="button" class="btn ghost" @click="download">导出 JSON</button>
        <label class="btn ghost">
          导入
          <input hidden type="file" accept="application/json" @change="onImport" />
        </label>
      </div>
    </header>

    <div class="body">
      <aside class="left">
        <LeftPanel />
      </aside>
      <main class="right">
        <RightPanel />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useFlowStudioStore } from "@/stores/flowStudio";
import LeftPanel from "@/components/LeftPanel.vue";
import RightPanel from "@/components/RightPanel.vue";

const store = useFlowStudioStore();

function download() {
  const blob = new Blob([store.exportJson()], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${store.doc.name || "flow"}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function onImport(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      store.importJson(String(reader.result));
    } catch {
      alert("JSON 解析失败");
    }
  };
  reader.readAsText(file);
  input.value = "";
}
</script>

<style scoped>
.studio {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 640px;
}

.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 86%, transparent);
  backdrop-filter: blur(10px);
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

.btn.ghost:hover {
  border-color: var(--border-strong);
}

.body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 0;
}

.left {
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  min-width: 280px;
}

.right {
  min-width: 0;
  background: linear-gradient(180deg, #fbfcff 0%, #f6f8fc 100%);
}

@media (max-width: 960px) {
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
