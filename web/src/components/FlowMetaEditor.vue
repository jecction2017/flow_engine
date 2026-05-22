<template>
  <div class="form-page">
    <header class="form-page-hd">
      <div class="form-page-hd-main">
        <span class="form-page-title">流程属性</span>
        <InfoTip
          wide
          text="流程名称用于列表与导出文件名；服务端以内部 id 区分流程。上下文内容为运行前注入的全局上下文（存储字段仍为 initial_context）。"
        />
      </div>
    </header>

    <section class="form-card">
      <div class="form-grid">
        <label class="form-field full">
          <span class="lbl-row">
            流程名称<span class="req">*</span>
            <InfoTip text="在流程列表等处展示；保存草稿或新版本前必填。" />
          </span>
          <input v-model="displayName" class="form-inp" placeholder="例如：订单履约主流程" />
        </label>

        <label class="form-field full">
          <span class="lbl-row">默认 Profile</span>
          <input class="form-inp mono" value="由全局环境配置决定" disabled />
        </label>

        <label class="form-field full">
          <span class="lbl-row">
            上下文内容 (JSON)
            <InfoTip wide text="流程启动前注入的全局上下文。顶层字段会被写入 $.global，可在节点 Starlark 中直接读写。" />
          </span>
          <textarea v-model="ctx" class="form-area mono" rows="6" spellcheck="false" />
        </label>
      </div>
    </section>

    <section class="form-card">
      <div class="form-sec-title">
        <span>生命周期钩子（可选）</span>
        <InfoTip
          wide
          text="流程级 Starlark 片段：on_start / on_complete / on_failure。通常仅用 resolve() 读路径。部署/测试运行详情中可查看 flow_logs。"
        />
      </div>
      <HooksEditor
        :model-value="flowHooks"
        :slots="flowHookSlots"
        :registry="starlarkRegistry"
        @update:model-value="onFlowHooksUpdate"
      />
    </section>

    <section class="form-card">
      <div class="card-hd">
        <div class="card-hd-main">
          <span class="form-card-title">并发策略</span>
          <InfoTip
            wide
            text="定义节点的执行模式（同步 / 异步 / 线程 / 进程）、并发、超时与重试。相邻节点引用非 sync 策略且未设置 wait_before 时，拓扑会出现隐式并行提示。"
          />
        </div>
        <button type="button" class="form-btn primary sm" @click="startAddStrategy">＋ 新增策略</button>
      </div>

      <div class="strategies-grid">
        <div
          v-for="k in store.strategiesList"
          :key="k"
          class="strategy-card"
          :class="{ active: selectedStrategyKey === k && !isCreatingStrategy }"
          @click="openStrategyDrawer(k)"
        >
          <div class="strategy-header">
            <span class="strategy-title">{{ strategyCardLabel(k) }}</span>
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
    </section>

    <Teleport to="body">
      <div
        v-if="strategyDrawerOpen"
        class="st-backdrop"
        @click.self="closeStrategyDrawer"
      >
        <aside
          class="st-drawer"
          role="dialog"
          aria-modal="true"
          aria-label="并发策略"
          @click.stop
        >
          <div class="strategy-editor-inline">
            <div class="inline-hd">
              <span class="inline-title">
                <template v-if="isCreatingStrategy">新增策略</template>
                <template v-else>编辑策略：{{ strategyEditTitle }}</template>
              </span>
              <div class="inline-actions">
                <template v-if="isCreatingStrategy">
                  <button type="button" class="form-btn ghost sm" @click="closeStrategyDrawer">取消</button>
                  <button type="button" class="form-btn primary sm" @click="createStrategy">创建</button>
                </template>
                <template v-else>
                  <button
                    v-if="selectedStrategyKey && selectedStrategyKey !== 'default_sync'"
                    type="button"
                    class="form-btn danger sm"
                    @click="removeStrategy(selectedStrategyKey)"
                  >删除</button>
                  <button type="button" class="form-btn ghost sm" @click="closeStrategyDrawer">关闭</button>
                </template>
              </div>
            </div>

            <div class="form-grid">
              <label class="form-field">
                <span class="lbl-row">
                  策略名<span class="req">*</span>
                  <InfoTip text="界面展示用；保存时系统会自动分配内部策略标识。" />
                </span>
                <input v-model="editSt.name" class="form-inp" placeholder="例如：异步 IO 池" />
              </label>
              <label class="form-field">
                <span class="lbl-row">
                  模式<span class="req">*</span>
                  <InfoTip
                    wide
                    text="sync：同步阻塞；async：协程派发；thread：线程池；process：进程池。"
                  />
                </span>
                <select v-model="editSt.mode" class="form-inp" @change="!isCreatingStrategy && saveStrategy()">
                  <option value="sync">sync</option>
                  <option value="async">async</option>
                  <option value="thread">thread</option>
                  <option value="process">process</option>
                </select>
              </label>
              <label class="form-field">
                <span class="lbl-row">
                  并发 / 池大小<span class="req">*</span>
                </span>
                <input
                  v-model.number="editSt.concurrency"
                  class="form-inp"
                  type="number"
                  min="1"
                  @change="!isCreatingStrategy && saveStrategy()"
                />
              </label>
              <label class="form-field">
                <span class="lbl-row">
                  超时 (秒)
                  <InfoTip text="可选。为空表示不限制。" />
                </span>
                <input
                  :value="editTimeout"
                  class="form-inp"
                  type="number"
                  min="0"
                  step="1"
                  placeholder="不限"
                  @input="updateTimeout($event)"
                  @change="!isCreatingStrategy && saveStrategy()"
                />
              </label>
              <label class="form-field">
                <span class="lbl-row">重试次数</span>
                <input
                  v-model.number="editSt.retry_count"
                  class="form-inp"
                  type="number"
                  min="0"
                  @change="!isCreatingStrategy && saveStrategy()"
                />
              </label>
            </div>
            <p v-if="strategyFormErr" class="form-err" style="margin-top: 8px">{{ strategyFormErr }}</p>
          </div>
        </aside>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, watch, ref, onMounted } from "vue";
import type { ExecutionStrategy, FlowHooks } from "@/types/flow";
import { useFlowStudioStore } from "@/stores/flowStudio";
import { useStarlarkRegistryCache } from "@/composables/useStarlarkRegistryCache";
import HooksEditor, { type HookSlotDef } from "./HooksEditor.vue";
import InfoTip from "./InfoTip.vue";

const store = useFlowStudioStore();
const { registry: starlarkRegistry, ensureRegistry } = useStarlarkRegistryCache();

onMounted(() => {
  void ensureRegistry();
});

const flowHookSlots: HookSlotDef[] = [
  { key: "on_start", label: "on_start", tip: "流程开始前执行。" },
  { key: "on_complete", label: "on_complete", tip: "流程成功结束后执行。" },
  { key: "on_failure", label: "on_failure", tip: "流程失败时执行（terminate 除外）。" },
];

const flowHooks = computed(() => store.doc.hooks ?? null);

function onFlowHooksUpdate(v: FlowHooks | null) {
  store.setFlowMeta({ hooks: v });
}

const selectedStrategyKey = computed<string | null>(() =>
  store.selection.kind === "strategy" ? store.selection.key : null,
);

const isCreatingStrategy = ref(false);
const strategyFormErr = ref("");

const editSt = reactive<ExecutionStrategy>({
  name: "default_sync",
  mode: "sync",
  concurrency: 4,
  timeout: undefined,
  retry_count: 0,
});

const strategyDrawerOpen = computed(
  () =>
    isCreatingStrategy.value ||
    (selectedStrategyKey.value != null &&
      !!store.doc.strategies[selectedStrategyKey.value]),
);

const strategyEditTitle = computed(() => {
  if (isCreatingStrategy.value) return "";
  const nm = (editSt.name ?? "").trim();
  return nm || "未命名策略";
});

function strategyCardLabel(key: string): string {
  const st = store.doc.strategies[key];
  const nm = (st?.name ?? "").trim();
  if (nm) return nm;
  return "未命名策略";
}

/** 新建策略时生成的内部 key，不展示给用户。 */
function allocateNewStrategyKey(): string {
  const used = new Set(Object.keys(store.doc.strategies));
  for (let i = 0; i < 10000; i++) {
    const k = `st_${Date.now()}_${i}`;
    if (!used.has(k)) return k;
  }
  return `st_${Date.now()}_${Math.random().toString(36).slice(2, 12)}`;
}

function openStrategyDrawer(key: string) {
  isCreatingStrategy.value = false;
  strategyFormErr.value = "";
  store.select({ kind: "strategy", key });
}

function closeStrategyDrawer() {
  strategyFormErr.value = "";
  if (isCreatingStrategy.value) {
    isCreatingStrategy.value = false;
  }
  if (store.selection.kind === "strategy") {
    store.select({ kind: "flow" });
  }
}

const displayName = computed({
  get: () => store.doc.display_name ?? "",
  set: (v: string) => store.setFlowMeta({ display_name: v }),
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

function startAddStrategy() {
  strategyFormErr.value = "";
  isCreatingStrategy.value = true;
  store.select({ kind: "flow" });

  editSt.name = "";
  editSt.mode = "async";
  editSt.concurrency = 4;
  editSt.timeout = 120;
  editSt.retry_count = 0;
}

function createStrategy() {
  strategyFormErr.value = "";
  const nm = String(editSt.name ?? "").trim();
  if (!nm) {
    strategyFormErr.value = "请填写策略名";
    return;
  }
  const key = allocateNewStrategyKey();
  store.upsertStrategy(key, { ...editSt, name: nm });
  isCreatingStrategy.value = false;
  store.select({ kind: "strategy", key });
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
      strategyFormErr.value = "";
      const cur = store.doc.strategies[sel.key];
      if (cur) Object.assign(editSt, cur);
    }
  },
  { immediate: true, deep: true },
);

function saveStrategy() {
  if (store.selection.kind !== "strategy" || !store.selection.key) return;
  strategyFormErr.value = "";
  const nm = String(editSt.name ?? "").trim();
  if (!nm) {
    strategyFormErr.value = "请填写策略名";
    return;
  }
  store.upsertStrategy(store.selection.key, { ...editSt, name: nm });
}

function removeStrategy(key: string) {
  store.removeStrategy(key);
  if (store.selection.kind === "strategy" && store.selection.key === key) {
    store.select({ kind: "flow" });
  }
}
</script>

<style scoped>
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

.lbl-row {
  display: inline-flex;
  align-items: center;
  font-weight: 500;
  color: #475569;
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

.strategy-title {
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

/* Inline strategy editor (drawer 内复用类名) */
.strategy-editor-inline {
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border));
  border-radius: 10px;
  background: color-mix(in srgb, var(--accent-soft) 25%, #fff);
}

.st-drawer .strategy-editor-inline {
  margin-top: 0;
  border: none;
  background: transparent;
  padding: 0;
}

.st-backdrop {
  position: fixed;
  inset: 0;
  z-index: 45;
  background: color-mix(in srgb, #0f172a 32%, transparent);
  display: flex;
  justify-content: flex-end;
  align-items: stretch;
}

.st-drawer {
  width: min(440px, calc(100vw - 16px));
  max-width: 100%;
  background: var(--surface);
  border-left: 1px solid var(--border);
  box-shadow: -8px 0 28px rgba(15, 23, 42, 0.14);
  overflow: auto;
  padding: 14px 16px 20px;
  animation: st-slide-in 0.2s ease-out;
}

@keyframes st-slide-in {
  from {
    transform: translateX(12px);
    opacity: 0.85;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
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

</style>
