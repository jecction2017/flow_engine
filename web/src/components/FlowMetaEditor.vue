<template>
  <div class="page">
    <header class="hd">
      <div class="hd-main">
        <span class="hd-title">流程属性</span>
        <InfoTip
          wide
          text="业务逻辑以 flow_id 为唯一主键，显示名仅用于界面展示。initial_context 作为流程运行前的全局上下文。"
        />
      </div>
    </header>

    <section class="card">
      <div class="grid">
        <label class="field">
          <span class="lbl-row">
            显示名
            <InfoTip text="留空时在界面上回落使用 flow_id。" />
          </span>
          <input v-model="displayName" class="inp" :placeholder="store.activeFlowId ?? ''" />
        </label>

        <label class="field">
          <span class="lbl-row">
            版本<span class="req">*</span>
          </span>
          <input v-model="version" class="inp" placeholder="例如：1.0" />
        </label>

        <label class="field">
          <span class="lbl-row">
            默认 Profile
            <InfoTip text="流程运行默认绑定的数据字典 profile；运行时可临时覆盖。" />
          </span>
          <select v-model="defaultProfile" class="inp mono">
            <option v-for="p in profileOptions" :key="p" :value="p">{{ p }}</option>
          </select>
        </label>

        <label class="field full">
          <span class="lbl-row">
            initial_context (JSON)
            <InfoTip wide text="流程启动前注入的全局上下文。顶层字段会被写入 $.global，可在节点 Starlark 中直接读写。" />
          </span>
          <textarea v-model="ctx" class="area mono" rows="6" spellcheck="false" />
        </label>
      </div>
    </section>

    <section class="card">
      <div class="card-hd">
        <div class="card-hd-main">
          <span class="card-title">运行策略</span>
          <InfoTip
            wide
            text="定义节点的执行模式（同步 / 异步 / 线程 / 进程）、并发、超时与重试。相邻节点引用非 sync 策略且未设置 wait_before 时，拓扑会出现隐式并行提示。"
          />
        </div>
        <button type="button" class="btn primary sm" @click="startAddStrategy">＋ 新增策略</button>
      </div>

      <div class="strategies-grid">
        <div
          v-for="k in store.strategiesList"
          :key="k"
          class="strategy-card"
          :class="{ active: selectedStrategyKey === k && !isCreatingStrategy }"
          @click="store.select({ kind: 'strategy', key: k })"
        >
          <div class="strategy-header">
            <span class="mono strategy-key">{{ k }}</span>
            <span class="mode-badge" :data-mode="store.modeOf(k)">{{ store.modeOf(k) }}</span>
          </div>
          <div v-if="store.doc.strategies[k]" class="strategy-meta">
            <span v-if="store.doc.strategies[k].name && store.doc.strategies[k].name !== k" class="meta-item">
              {{ store.doc.strategies[k].name }}
            </span>
            <span v-if="store.doc.strategies[k].concurrency" class="meta-item">并发 {{ store.doc.strategies[k].concurrency }}</span>
            <span v-if="store.doc.strategies[k].timeout" class="meta-item">超时 {{ store.doc.strategies[k].timeout }}s</span>
            <span v-if="store.doc.strategies[k].retry_count" class="meta-item">重试 {{ store.doc.strategies[k].retry_count }}</span>
          </div>
        </div>
      </div>

      <div
        v-if="isCreatingStrategy || (selectedStrategyKey && store.doc.strategies[selectedStrategyKey])"
        class="strategy-editor-inline"
      >
        <div class="inline-hd">
          <span class="inline-title">
            <template v-if="isCreatingStrategy">新增策略</template>
            <template v-else>编辑：<span class="mono">{{ selectedStrategyKey }}</span></template>
          </span>
          <div class="inline-actions">
            <template v-if="isCreatingStrategy">
              <button type="button" class="btn ghost sm" @click="cancelCreateStrategy">取消</button>
              <button type="button" class="btn primary sm" @click="createStrategy">创建</button>
            </template>
            <template v-else>
              <button
                v-if="selectedStrategyKey && selectedStrategyKey !== 'default_sync'"
                type="button"
                class="btn danger sm"
                @click="removeStrategy(selectedStrategyKey)"
              >删除</button>
            </template>
          </div>
        </div>

        <div class="grid">
          <label v-if="isCreatingStrategy" class="field">
            <span class="lbl-row">
              策略 Key<span class="req">*</span>
              <InfoTip text="唯一英文标识，一经创建不可修改。" />
            </span>
            <input v-model="newStrategyKey" class="inp mono" placeholder="my_strategy" />
          </label>
          <label class="field">
            <span class="lbl-row">显示名称</span>
            <input v-model="editSt.name" class="inp" @change="!isCreatingStrategy && saveStrategy()" />
          </label>
          <label class="field">
            <span class="lbl-row">
              模式<span class="req">*</span>
              <InfoTip
                wide
                text="sync：同步阻塞；async：协程派发；thread：线程池；process：进程池。"
              />
            </span>
            <select v-model="editSt.mode" class="inp" @change="!isCreatingStrategy && saveStrategy()">
              <option value="sync">sync</option>
              <option value="async">async</option>
              <option value="thread">thread</option>
              <option value="process">process</option>
            </select>
          </label>
          <label class="field">
            <span class="lbl-row">
              并发 / 池大小<span class="req">*</span>
            </span>
            <input
              v-model.number="editSt.concurrency"
              class="inp"
              type="number"
              min="1"
              @change="!isCreatingStrategy && saveStrategy()"
            />
          </label>
          <label class="field">
            <span class="lbl-row">
              超时 (秒)
              <InfoTip text="可选。为空表示不限制。" />
            </span>
            <input
              :value="editTimeout"
              class="inp"
              type="number"
              min="0"
              step="1"
              placeholder="不限"
              @input="updateTimeout($event)"
              @change="!isCreatingStrategy && saveStrategy()"
            />
          </label>
          <label class="field">
            <span class="lbl-row">重试次数</span>
            <input
              v-model.number="editSt.retry_count"
              class="inp"
              type="number"
              min="0"
              @change="!isCreatingStrategy && saveStrategy()"
            />
          </label>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, watch, ref, onMounted } from "vue";
import type { ExecutionStrategy } from "@/types/flow";
import { useFlowStudioStore } from "@/stores/flowStudio";
import InfoTip from "./InfoTip.vue";
import { fetchDictProfiles } from "@/api/dict";

const store = useFlowStudioStore();
const profileOptions = ref<string[]>(["default"]);

const selectedStrategyKey = computed<string | null>(() =>
  store.selection.kind === "strategy" ? store.selection.key : null,
);

const displayName = computed({
  get: () => store.doc.display_name ?? "",
  set: (v: string) => store.setFlowMeta({ display_name: v }),
});

const version = computed({
  get: () => store.doc.version,
  set: (v: string) => store.setFlowMeta({ version: v }),
});

const defaultProfile = computed({
  get: () => {
    const cur = (store.doc.default_profile ?? "default").trim() || "default";
    if (!profileOptions.value.includes(cur)) profileOptions.value = [...profileOptions.value, cur].sort();
    return cur;
  },
  set: (v: string) => store.setFlowMeta({ default_profile: v.trim() || "default" }),
});

onMounted(async () => {
  try {
    const res = await fetchDictProfiles();
    if (Array.isArray(res.profiles) && res.profiles.length) {
      profileOptions.value = [...res.profiles];
    }
  } catch {
    profileOptions.value = profileOptions.value.length ? profileOptions.value : ["default"];
  }
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
  store.select({ kind: "flow" });

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
      isCreatingStrategy.value = false;
      const cur = store.doc.strategies[sel.key];
      if (cur) Object.assign(editSt, cur);
    }
  },
  { immediate: true, deep: true },
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
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding: 12px 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 1000px;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;
}

.page::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
.page::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}
.page::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
.page::-webkit-scrollbar-track {
  background: transparent;
}

.hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 2px 0;
}

.hd-main {
  display: inline-flex;
  align-items: center;
}

.hd-title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text);
}

.card {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  padding: 12px 14px;
  box-shadow: var(--shadow);
}

.card-hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.card-hd-main {
  display: inline-flex;
  align-items: center;
}

.card-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.01em;
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 12px;
}

.field {
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}

.field.full {
  grid-column: 1 / -1;
}

.lbl-row {
  display: inline-flex;
  align-items: center;
  font-weight: 500;
  color: #475569;
}

.inp {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 10px;
  outline: none;
  font-size: 12.5px;
  background: #fff;
  color: var(--text);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.inp:focus {
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.area {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  outline: none;
  resize: vertical;
  background: #fbfdff;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.area:focus {
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

/* Strategies grid */
.strategies-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px;
}

.strategy-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 9px 11px;
  background: #fff;
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.strategy-card:hover {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 30%, #fff);
}

.strategy-card.active {
  border-color: var(--accent);
  background: var(--accent-soft);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 20%, transparent);
}

.strategy-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}

.strategy-key {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mode-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  flex-shrink: 0;
}

.mode-badge[data-mode="sync"] {
  background: #e0f2fe;
  color: #075985;
}
.mode-badge[data-mode="async"] {
  background: #ede9fe;
  color: #5b21b6;
}
.mode-badge[data-mode="thread"] {
  background: #dcfce7;
  color: #166534;
}
.mode-badge[data-mode="process"] {
  background: #fef3c7;
  color: #92400e;
}

.strategy-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  font-size: 10.5px;
  color: var(--muted);
}

.meta-item {
  padding: 1px 6px;
  border-radius: 3px;
  background: color-mix(in srgb, var(--border) 40%, transparent);
}

/* Inline strategy editor */
.strategy-editor-inline {
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border));
  border-radius: 10px;
  background: color-mix(in srgb, var(--accent-soft) 25%, #fff);
}

.inline-hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.inline-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
}

.inline-actions {
  display: inline-flex;
  gap: 6px;
}

/* Buttons */
.btn {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 7px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.btn.sm {
  padding: 5px 10px;
  font-size: 11.5px;
}

.btn.ghost:hover {
  border-color: var(--border-strong);
  background: #f8fafc;
}

.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.btn.primary:hover {
  background: color-mix(in srgb, var(--accent) 88%, #000);
}

.btn.danger {
  border-color: color-mix(in srgb, #ef4444 45%, transparent);
  color: #b91c1c;
  background: #fff;
}

.btn.danger:hover {
  background: #fef2f2;
}

@media (max-width: 720px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
