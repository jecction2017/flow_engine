<template>
  <div class="studio">
    <header class="top">
      <div class="brand">
        <span class="logo">◇</span>
        <div>
          <div class="title">Flow Studio</div>
          <div class="subtitle">
            流程拓扑 · 策略 · 节点调试
            <span v-if="store.serverFlowsDir" class="dir-hint" :title="store.serverFlowsDir"> · YAML 目录已连接</span>
          </div>
        </div>
      </div>
      <div class="actions">
        <div class="grp" title="对应服务端 flows 目录下的 YAML 文件">
          <select v-model="selectedId" class="sel" @change="onSelectFlow">
            <option value="" disabled>选择 data/flows/*.yaml…</option>
            <option v-for="f in store.flowList" :key="f.id" :value="f.id">
              {{ f.name }} ({{ f.id }})
            </option>
          </select>
          <button type="button" class="btn ghost" title="重新扫描 flows 目录" @click="refresh">刷新</button>
          <button type="button" class="btn primary" :disabled="!store.activeFlowId || saving" @click="save">
            {{ saving ? "保存中…" : "保存到服务器" }}
          </button>
          <button
            type="button"
            class="btn accent"
            :disabled="!store.activeFlowId"
            title="执行当前选中的流程（需先保存）"
            @click="toggleRun"
          >
            ▶ 运行流程
          </button>
          <button type="button" class="btn ghost" @click="newFlow">新建流程</button>
        </div>
        <div class="grp">
          <button type="button" class="btn ghost" @click="download">导出 JSON</button>
          <label class="btn ghost">
            导入
            <input hidden type="file" accept="application/json" @change="onImport" />
          </label>
        </div>
      </div>
    </header>

    <FlowRunPanel
      :flow-id="store.activeFlowId"
      :visible="runVisible"
      :initial-context="store.doc.initial_context"
      @close="runVisible = false"
    />
    <p v-if="store.apiError" class="api-err">API: {{ store.apiError }}（请先执行 <code>flow-api</code> 或 <code>python -m flow_engine.http_api</code>）</p>

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
import { onMounted, ref, watch } from "vue";
import { useFlowStudioStore } from "@/stores/flowStudio";
import LeftPanel from "@/components/LeftPanel.vue";
import RightPanel from "@/components/RightPanel.vue";
import FlowRunPanel from "@/components/FlowRunPanel.vue";

const store = useFlowStudioStore();
const selectedId = ref("");
const saving = ref(false);
const runVisible = ref(false);

function toggleRun() {
  runVisible.value = !runVisible.value;
}

watch(
  () => store.activeFlowId,
  (v) => {
    selectedId.value = v ?? "";
  },
  { immediate: true },
);

onMounted(async () => {
  await store.refreshFlowList();
  try {
    if (store.flowList.some((f) => f.id === "demo_flow")) {
      await store.loadFlowFromServer("demo_flow");
    } else if (store.flowList.length > 0) {
      await store.loadFlowFromServer(store.flowList[0].id);
    }
  } catch {
    /* 离线时使用内置示例 */
  }
});

async function refresh() {
  await store.refreshFlowList();
}

async function onSelectFlow() {
  if (!selectedId.value) return;
  try {
    await store.loadFlowFromServer(selectedId.value);
  } catch (e) {
    alert(e instanceof Error ? e.message : String(e));
  }
}

async function save() {
  saving.value = true;
  try {
    await store.saveFlowToServer();
  } catch (e) {
    alert(e instanceof Error ? e.message : String(e));
  } finally {
    saving.value = false;
  }
}

async function newFlow() {
  const id = prompt("新流程 id（字母、数字、下划线、短横线）", `flow_${Date.now()}`);
  if (!id?.trim()) return;
  try {
    await store.createFlowOnServer(id.trim());
  } catch (e) {
    alert(e instanceof Error ? e.message : String(e));
  }
}

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
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 86%, transparent);
  backdrop-filter: blur(10px);
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

.dir-hint {
  color: var(--success);
  font-size: 11px;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  justify-content: flex-end;
}

.grp {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.sel {
  min-width: 200px;
  max-width: 280px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 12px;
  background: #fff;
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
  white-space: nowrap;
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

.btn.accent {
  border-color: color-mix(in srgb, #10b981 35%, transparent);
  background: #10b981;
  color: #fff;
}

.btn.accent:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn.accent:hover:not(:disabled) {
  background: #059669;
}

.btn.ghost:hover {
  border-color: var(--border-strong);
}

.api-err {
  margin: 0;
  padding: 6px 16px;
  font-size: 11px;
  color: #b45309;
  background: color-mix(in srgb, #fbbf24 12%, transparent);
  border-bottom: 1px solid color-mix(in srgb, #f59e0b 25%, transparent);
}

.api-err code {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 4px;
  background: #fff8;
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
