<template>
  <div class="page">
    <header class="hd">
      <div>
        <div class="t">流程属性</div>
        <div class="s">名称、版本与初始全局上下文</div>
      </div>
    </header>

    <div class="grid">
      <label class="field">
        <span>名称</span>
        <input v-model="name" class="inp" />
      </label>
      <label class="field">
        <span>版本</span>
        <input v-model="version" class="inp" />
      </label>
    </div>

    <label class="field">
      <span>initial_context（JSON）</span>
      <textarea v-model="ctx" class="area mono" rows="10" spellcheck="false" />
    </label>
    <div class="strategies-section">
      <div class="hd" style="margin-top: 24px;">
        <div>
          <div class="t">运行策略</div>
          <div class="s">管理流程节点的执行策略（如 sync、async、process、thread 及并发参数）</div>
        </div>
      </div>

      <div class="strategies-grid">
        <div 
          v-for="k in store.strategiesList" 
          :key="k"
          class="strategy-card"
          :class="{ active: store.selection.kind === 'strategy' && store.selection.key === k }"
          @click="store.select({ kind: 'strategy', key: k })"
        >
          <div class="strategy-header">
            <span class="mono strategy-key">{{ k }}</span>
            <span class="mode-badge">{{ store.modeOf(k) }}</span>
          </div>
          <div class="strategy-meta" v-if="store.doc.strategies[k]">
            <span class="meta-item" v-if="store.doc.strategies[k].name && store.doc.strategies[k].name !== k">{{ store.doc.strategies[k].name }}</span>
            <span class="meta-item" v-if="store.doc.strategies[k].concurrency">并发: {{ store.doc.strategies[k].concurrency }}</span>
            <span class="meta-item" v-if="store.doc.strategies[k].timeout">超时: {{ store.doc.strategies[k].timeout }}s</span>
            <span class="meta-item" v-if="store.doc.strategies[k].retry_count">重试: {{ store.doc.strategies[k].retry_count }}</span>
          </div>
        </div>
        
        <!-- Add Strategy Button Card -->
        <div class="strategy-card add-card" :class="{ active: isCreatingStrategy }" @click="startAddStrategy">
          <div class="add-content">
            <span class="add-icon">＋</span>
            <span>新增策略</span>
          </div>
        </div>
      </div>
      
      <div v-if="isCreatingStrategy || (store.selection.kind === 'strategy' && store.selection.key && store.doc.strategies[store.selection.key])" 
           class="strategy-editor-inline"
           :class="{ 'creating': isCreatingStrategy }">
        <div class="hd" style="margin-top: 0; align-items: center;">
          <div>
            <div class="t" style="font-size: 14px;" v-if="isCreatingStrategy">新增策略</div>
            <div class="t" style="font-size: 14px;" v-else>编辑策略：<span class="mono">{{ store.selection.key }}</span></div>
          </div>
          <div style="display: flex; gap: 8px;">
            <template v-if="isCreatingStrategy">
              <button type="button" class="btn ghost" @click="cancelCreateStrategy">取消</button>
              <button type="button" class="btn primary" @click="createStrategy">创建并保存</button>
            </template>
            <template v-else>
              <button v-if="store.selection.key !== 'default_sync'" type="button" class="danger btn" @click="removeStrategy(store.selection.key)">删除策略</button>
            </template>
          </div>
        </div>

        <div class="grid">
          <label class="field" v-if="isCreatingStrategy">
            <span>策略 Key (唯一英文标识)</span>
            <input v-model="newStrategyKey" class="inp" placeholder="如: my_strategy" />
          </label>
          <label class="field">
            <span>显示名称</span>
            <input v-model="editSt.name" class="inp" @change="!isCreatingStrategy && saveStrategy()" />
          </label>
          <label class="field">
            <span>模式</span>
            <select v-model="editSt.mode" class="inp" @change="!isCreatingStrategy && saveStrategy()">
              <option value="sync">sync（同步阻塞）</option>
              <option value="async">async（协程派发）</option>
              <option value="thread">thread（线程池）</option>
              <option value="process">process（进程池）</option>
            </select>
          </label>
          <label class="field">
            <span>并发 / 池大小</span>
            <input v-model.number="editSt.concurrency" class="inp" type="number" min="1" @change="!isCreatingStrategy && saveStrategy()" />
          </label>
          <label class="field">
            <span>超时（秒，可选）</span>
            <input :value="editTimeout" @input="updateTimeout($event)" class="inp" type="number" min="0" step="1" @change="!isCreatingStrategy && saveStrategy()" />
          </label>
          <label class="field">
            <span>重试次数</span>
            <input v-model.number="editSt.retry_count" class="inp" type="number" min="0" @change="!isCreatingStrategy && saveStrategy()" />
          </label>
        </div>

        <div class="note">
          相邻节点若引用非 <span class="mono">sync</span> 策略，且右侧节点未设置
          <span class="mono">wait_before</span>，左侧拓扑会出现「隐式并行」提示带。
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, watch, ref } from "vue";
import type { ExecutionStrategy } from "@/types/flow";
import { useFlowStudioStore } from "@/stores/flowStudio";

const store = useFlowStudioStore();

const name = computed({
  get: () => store.doc.name,
  set: (v: string) => store.setFlowMeta({ name: v }),
});

const version = computed({
  get: () => store.doc.version,
  set: (v: string) => store.setFlowMeta({ version: v }),
});

const ctx = computed({
  get: () => JSON.stringify(store.doc.initial_context ?? {}, null, 2),
  set: (v: string) => {
    try {
      store.setInitialContextJson(v);
    } catch {
      // 允许编辑过程中的临时非法 JSON
    }
  },
});

// === Inline Strategy Editor Logic ===
const isCreatingStrategy = ref(false);
const newStrategyKey = ref("");

const editSt = reactive<ExecutionStrategy>({
  name: "default_sync",
  mode: "sync",
  concurrency: 4,
  timeout: undefined,
  retry_count: 0,
});

function startAddStrategy() {
  isCreatingStrategy.value = true;
  newStrategyKey.value = `strategy_${Date.now()}`;
  store.select({ kind: "flow" }); // unselect current strategy if any
  
  editSt.name = newStrategyKey.value;
  editSt.mode = "async";
  editSt.concurrency = 4;
  editSt.timeout = 120;
  editSt.retry_count = 0;
}

function createStrategy() {
  const k = newStrategyKey.value.trim();
  if (!k) {
    alert("请输入策略 Key");
    return;
  }
  if (store.doc.strategies[k]) {
    alert("该策略 Key 已存在");
    return;
  }
  
  store.upsertStrategy(k, { ...editSt });
  isCreatingStrategy.value = false;
  store.select({ kind: "strategy", key: k });
}

function cancelCreateStrategy() {
  isCreatingStrategy.value = false;
}

const editTimeout = computed(() => (editSt.timeout == null ? "" : String(editSt.timeout)));

function updateTimeout(e: Event) {
  const target = e.target as HTMLInputElement;
  editSt.timeout = target.value === "" ? undefined : Number(target.value);
}

watch(
  () => store.selection,
  (sel) => {
    if (sel.kind === "strategy" && sel.key) {
      isCreatingStrategy.value = false; // exit create mode if selected from list
      const cur = store.doc.strategies[sel.key];
      if (cur) Object.assign(editSt, cur);
    }
  },
  { immediate: true, deep: true }
);

function saveStrategy() {
  if (store.selection.kind === "strategy" && store.selection.key) {
    store.upsertStrategy(store.selection.key, { ...editSt });
  }
}

function removeStrategy(key: string) {
  store.removeStrategy(key);
  if (store.selection.kind === "strategy" && store.selection.key === key) {
    store.select({ kind: "flow" });
  }
}
</script>

<style scoped>
.page {
  padding: 16px;
  max-width: 980px;
}

.hd {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.t {
  font-size: 16px;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.s {
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.field {
  display: grid;
  gap: 6px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--muted);
}

.inp {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 10px;
  outline: none;
  font-size: 13px;
}

.area {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px;
  outline: none;
  resize: vertical;
  background: #fbfdff;
}

.inp:focus,
.area:focus {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

@media (max-width: 720px) {
  .grid {
    grid-template-columns: 1fr;
  }
}

.strategies-section {
  margin-top: 32px;
  border-top: 1px dashed var(--border);
  padding-top: 8px;
}

.strategies-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.strategy-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  background: var(--surface);
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
}

.strategy-card:hover {
  border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
  transform: translateY(-1px);
  box-shadow: var(--shadow);
}

.strategy-card.add-card {
  border: 1px dashed var(--border);
  background: color-mix(in srgb, var(--surface) 50%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  box-shadow: none;
}

.strategy-card.add-card:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--surface);
  border-style: solid;
}

.strategy-card.add-card.active {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-soft);
  border-style: solid;
}

.add-content {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
}

.add-icon {
  font-size: 16px;
}

.strategy-editor-inline {
  margin-top: 12px; /* reduced to bring it closer to the cards */
  padding: 20px;
  border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border));
  border-radius: 12px;
  background: color-mix(in srgb, var(--accent-soft) 20%, var(--surface));
  position: relative;
}

/* Arrow pointing up to the selected card */
.strategy-editor-inline::before {
  content: '';
  position: absolute;
  top: -6px;
  left: 30px; /* Default position */
  width: 10px;
  height: 10px;
  background: color-mix(in srgb, var(--accent-soft) 20%, var(--surface));
  border-top: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border));
  border-left: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border));
  transform: rotate(45deg);
  display: none; /* Hide the old arrow, we use the downward caret from the active card instead */
}

.strategy-editor-inline.creating::before {
  display: none; /* Hide the arrow when creating a new strategy as it's harder to position correctly under the add card */
}

.strategy-editor-inline .hd {
  margin-top: 0 !important;
}

.strategy-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.strategy-key {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.mode-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 20%, transparent);
  text-transform: uppercase;
}

.strategy-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 11px;
  color: var(--muted);
}

.meta-item {
  background: color-mix(in srgb, var(--surface) 80%, transparent);
  border: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
  padding: 1px 6px;
  border-radius: 4px;
}

.btn {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}

.btn.outline {
  border-color: var(--border);
  color: var(--text);
}

.btn.outline:hover {
  border-color: var(--accent);
  color: var(--accent);
}
</style>
