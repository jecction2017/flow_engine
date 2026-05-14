<template>
  <div v-if="node" class="page" :class="{ 'is-task': node.type === 'task' }">
    <header class="hd">
      <div class="hd-main">
        <span class="hd-title">{{ title }}</span>
        <span class="chip" :data-type="node.type">{{ node.type }}</span>
        <span class="chip strategy-chip" :title="`并发策略：${node.strategy_ref}`">{{ node.strategy_ref }}</span>
      </div>
      <div class="hd-path mono" :title="path.join(' → ')">{{ path.join(" → ") }}</div>
    </header>

    <div class="body">
      <div class="col col-left">
        <section class="card">
          <div class="sec-title">
            <span>基础信息</span>
          </div>
          <div class="grid grid-task-basic">
            <label class="field full">
              <span class="lbl-row">
                名称<span class="req">*</span>
                <InfoTip
                  text="流程内必填且唯一（与其它节点去空白后不可重名）。树与编排页仅展示此名称；引擎内部 id 由系统自动分配。"
                />
              </span>
              <input
                v-model="nameText"
                class="inp"
                :class="{ invalid: nameErrorNode !== null }"
                placeholder="例如：告警归一化"
                @input="onNameInput"
              />
              <span v-if="nameErrorNode" class="err">{{ nameErrorNode }}</span>
            </label>

            <label class="field full">
              <span class="lbl-row">
                描述
                <InfoTip text="可选。说明本节点在流程中的作用；不参与执行与校验，仅用于文档与树状列表提示。" />
              </span>
              <textarea
                class="inp node-desc"
                rows="2"
                placeholder="例如：将外部告警归一化为内部事件模型"
                :value="nodeDescriptionText"
                @input="onDescriptionInput($event)"
              />
            </label>

            <div class="field full task-strategy-row">
              <span class="lbl-row">
                并发策略<span class="req">*</span>
                <InfoTip
                  wide
                  text="策略键引用流程属性中的执行方式（同步 / 异步派发 / 线程池等）。勾选「同步屏障」时，进入本节点前会等待同层已派发的异步任务结束。"
                />
              </span>
              <div class="task-strategy-inner">
                <select v-model="node.strategy_ref" class="inp strat-sel" @change="commit">
                  <option v-for="k in store.strategiesList" :key="k" :value="k">{{ k }}</option>
                </select>
                <label class="wait-inline">
                  <input v-model="node.wait_before" type="checkbox" @change="commit" />
                  <span>同步屏障</span>
                </label>
              </div>
            </div>

            <label class="field full">
              <span class="lbl-row">
                执行条件
                <InfoTip text="Starlark 表达式，可选。为 False 时跳过本节点。" />
              </span>
              <div class="cond-editor-wrap">
                <CodeEditor
                  :model-value="node.condition ?? ''"
                  :height="conditionEditorHeight"
                  :registry="starlarkRegistry"
                  :path-suggestions="conditionPathSuggestionsGetter"
                  placeholder="True"
                  @update:model-value="onConditionCodeUpdate"
                />
              </div>
            </label>
          </div>
        </section>

        <section v-if="node.type === 'task'" class="card card-compact">
          <div class="sec-title sec-title-tight">
            <span>参数映射</span>
            <InfoTip
              wide
              text="声明本任务如何从流程上下文取数、如何把返回值写回上下文。左侧表：变量名 ← 上下文路径（注入 Starlark 的 inputs）；右侧表：返回字段 → 上下文路径（outputs）。空映射表示由脚本自行读写 $.global 等，可不填。"
            />
            <button type="button" class="mini ghost" @click="resetBoundaryMapping">重置</button>
          </div>
          <BoundaryMappingEditor
            :key="`${path.join('/')}-${boundaryMappingLayoutEpoch}`"
            :model-value="(node as TaskNode).boundary"
            :sync-key="path.join('/')"
            @update:model-value="onBoundaryUpdate"
          />
        </section>

        <section v-if="node.type === 'task'" class="card card-cap-rules">
          <div class="sec-title">
            <span>副作用函数抑制规则（本节点）</span>
            <InfoTip
              wide
              text="写入流程定义，仅对本任务节点生效；按类目或具体副作用函数（Starlark 注册名）匹配后执行放行 / 抑制 / 改写。优先级高于环境级策略与部署、测试时的附加策略；空表示不额外覆盖。技术字段名：capability_overrides。"
            />
          </div>
          <CapabilityRulesEditor
            :model-value="taskCapabilityOverrides"
            @update:model-value="onCapabilityOverridesChange"
          />
        </section>

        <section v-if="node.type === 'loop'" class="card">
          <div class="sec-title"><span>循环</span></div>
          <div class="grid">
            <label class="field full">
              <span class="lbl-row">
                iterable<span class="req">*</span>
                <InfoTip wide text="Starlark 表达式或 $.path 简写。如：$.global.items 或 resolve('$.global.items')。" />
              </span>
              <input
                v-model="node.iterable"
                class="inp mono"
                placeholder="$.global.items"
                @input="commit"
              />
            </label>
            <label class="field">
              <span class="lbl-row">
                alias
                <InfoTip text="迭代别名，默认为 item。" />
              </span>
              <input v-model="node.alias" class="inp mono" placeholder="item" @input="commit" />
            </label>
            <label class="field">
              <span class="lbl-row">
                copy_item
                <InfoTip wide text="每次迭代绑定 $.item 的方式：shared 引用 / shallow 浅拷贝 / deep 深拷贝。" />
              </span>
              <select :value="loopCopyItem" class="inp" @change="onCopyItemChange">
                <option value="shared">shared</option>
                <option value="shallow">shallow</option>
                <option value="deep">deep</option>
              </select>
            </label>
            <label class="field">
              <span class="lbl-row">
                iteration_isolation
                <InfoTip wide text="shared：共享 $.global；fork：每次迭代独立深拷贝父 ctx。" />
              </span>
              <select :value="loopIsolation" class="inp" @change="onIsolationChange">
                <option value="shared">shared</option>
                <option value="fork">fork</option>
              </select>
            </label>

            <label class="field check full">
              <input
                type="checkbox"
                :checked="collectEnabled"
                @change="onCollectToggle(($event.target as HTMLInputElement).checked)"
              />
              <span class="lbl-row">
                iteration_collect
                <InfoTip wide text="启用后：把每次迭代结果追加到父 ctx 的 list。常配合 iteration_isolation=fork 使用。" />
              </span>
            </label>

            <template v-if="collectEnabled">
              <label class="field">
                <span class="lbl-row">
                  from_path<span class="req">*</span>
                  <InfoTip text="从迭代 ctx 读取的 $. 路径。" />
                </span>
                <input
                  :value="node.iteration_collect?.from_path ?? ''"
                  class="inp mono"
                  placeholder="$.global.per_item_result"
                  @input="onCollectFromPath(($event.target as HTMLInputElement).value)"
                />
              </label>
              <label class="field">
                <span class="lbl-row">
                  append_to<span class="req">*</span>
                  <InfoTip text="父 ctx 的 list 路径。" />
                </span>
                <input
                  :value="node.iteration_collect?.append_to ?? ''"
                  class="inp mono"
                  placeholder="$.global.results"
                  @input="onCollectAppendTo(($event.target as HTMLInputElement).value)"
                />
              </label>
            </template>
          </div>
        </section>

        <section v-if="node.type === 'subflow'" class="card">
          <div class="sec-title"><span>子流程</span></div>
          <label class="field">
            <span class="lbl-row">
              alias
              <InfoTip text="子流程别名，子节点在左侧树中编辑。" />
            </span>
            <input v-model="node.alias" class="inp mono" @input="commit" />
          </label>
        </section>
      </div>

      <div v-if="node.type === 'task'" class="col col-right">
        <section class="card script-card script-card--dark">
          <div class="script-sec-head">
            <div class="script-sec-head-left">
              <span class="script-sec-title">Starlark 脚本</span>
              <InfoTip text="节点执行逻辑。通过 inputs 注入变量，结果经由 outputs 写回上下文。" />
            </div>
            <div class="script-sec-actions">
              <button
                type="button"
                class="btn primary sm"
                title="打开节点调试：编辑上下文、附加策略并执行脚本"
                @click="openDebugDrawer"
              >
                调试
              </button>
            </div>
          </div>
          <div class="script-body">
            <CodeEditor
              v-model="node.script"
              fill
              appearance="code-dark"
              :registry="starlarkRegistry"
              @update:model-value="commit"
            />
          </div>
        </section>
      </div>
    </div>

    <Teleport to="body">
      <template v-if="node && node.type === 'task'">
        <div
          v-show="debugDrawerOpen"
          class="nde-backdrop"
          @click.self="debugDrawerOpen = false"
        />
        <aside
          class="nde-drawer"
          :class="{ 'nde-drawer--open': debugDrawerOpen }"
          role="dialog"
          aria-modal="true"
          aria-label="节点调试"
          @click.stop
        >
          <div class="nde-drawer-hd">
            <span class="nde-drawer-title">节点调试</span>
            <div class="nde-drawer-hd-actions">
              <button
                type="button"
                class="btn primary sm"
                :disabled="debugPending"
                @click="runNodeDebug"
              >
                {{ debugPending ? "请求中…" : "▶ 调试" }}
              </button>
              <button type="button" class="btn ghost sm" @click="debugDrawerOpen = false">关闭</button>
            </div>
          </div>
          <div class="nde-drawer-body">
            <DebugPanel ref="debugPanelRef" :path="path" embedded hide-toolbar />
          </div>
        </aside>
      </template>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";
import type {
  Boundary,
  CapabilityRule,
  FlowNode,
  LoopCopyItem,
  LoopIterationIsolation,
  LoopNode,
  TaskNode,
} from "@/types/flow";
import { useFlowStudioStore } from "@/stores/flowStudio";
import { useStarlarkRegistryCache } from "@/composables/useStarlarkRegistryCache";
import BoundaryMappingEditor from "./BoundaryMappingEditor.vue";
import CapabilityRulesEditor from "./CapabilityRulesEditor.vue";
import CodeEditor from "./CodeEditor.vue";
import DebugPanel from "./DebugPanel.vue";
import InfoTip from "./InfoTip.vue";
import { collectContextPathSuggestions } from "@/utils/contextPathSuggestions";

const props = defineProps<{ path: number[] }>();
const store = useFlowStudioStore();
/** 重置参数映射时递增，强制子组件 remount，避免边界 JSON 未变时 UI 仍保留多行空草稿。 */
const boundaryMappingLayoutEpoch = ref(0);
const { registry: starlarkRegistry, ensureRegistry } = useStarlarkRegistryCache();

const debugDrawerOpen = ref(false);
const debugPanelRef = shallowRef<InstanceType<typeof DebugPanel> | null>(null);

const debugPending = computed(() => {
  const inst = debugPanelRef.value as unknown as { pending?: { value?: boolean } | boolean } | null;
  if (!inst?.pending) return false;
  return typeof inst.pending === "object" && inst.pending !== null && "value" in inst.pending
    ? !!inst.pending.value
    : !!inst.pending;
});

function runNodeDebug() {
  const inst = debugPanelRef.value as unknown as { run?: () => void | Promise<void> } | null;
  void inst?.run?.();
}

function openDebugDrawer() {
  debugDrawerOpen.value = true;
}

watch(
  () => props.path.join("/"),
  () => {
    debugDrawerOpen.value = false;
  },
);

function onDebugEscape(ev: KeyboardEvent) {
  if (ev.key !== "Escape" || !debugDrawerOpen.value) return;
  debugDrawerOpen.value = false;
}

onMounted(() => {
  void ensureRegistry();
  document.addEventListener("keydown", onDebugEscape);
});

onUnmounted(() => {
  document.removeEventListener("keydown", onDebugEscape);
});

const node = computed(() => store.editableNode(props.path) as FlowNode | null);

const title = computed(() => {
  if (!node.value) return "";
  if (node.value.type === "task") return "Task 节点";
  if (node.value.type === "loop") return "Loop 节点";
  return "Subflow 节点";
});

/** 执行条件：按换行数增高编辑器（单行约一行高，上限避免占满屏）。 */
const conditionEditorHeight = computed(() => {
  const n = node.value;
  if (!n) return 40;
  const raw = (n.condition ?? "").replace(/\r\n/g, "\n");
  const lines = Math.max(1, raw.split("\n").length);
  const perLine = 21;
  const pad = 18;
  return Math.min(440, Math.max(38, lines * perLine + pad));
});

// ---------------------------------------------------------------------------
// 基础信息：name（用户可见）；id 由系统自动分配，不向用户展示
// ---------------------------------------------------------------------------

const nameText = ref("");

watch(
  () => `${props.path.join("/")}|${node.value?.type ?? ""}|${node.value?.name ?? ""}`,
  () => {
    const n = node.value;
    if (!n) return;
    nameText.value = n.name ?? "";
  },
  { immediate: true },
);

const nameErrorNode = computed<string | null>(() => {
  if (!node.value) return null;
  const v = nameText.value.trim();
  if (!v) return "名称必填";
  const taken = store.collectAllTrimmedNodeDisplayNamesExcludePath(props.path.join("/"));
  if (taken.has(v)) return "名称与其它节点重复";
  return null;
});

function onNameInput() {
  if (!node.value) return;
  const next = nameText.value;
  if (node.value.name !== next) {
    node.value.name = next;
    commit();
  }
}

const nodeDescriptionText = computed(() => {
  const n = node.value;
  if (!n) return "";
  const d = n.description;
  return typeof d === "string" ? d : "";
});

function onDescriptionInput(ev: Event) {
  if (!node.value) return;
  const raw = (ev.target as HTMLTextAreaElement).value.replace(/\r\n/g, "\n");
  const next = raw.trim() === "" ? null : raw;
  if (node.value.description !== next) {
    node.value.description = next;
    commit();
  }
}

function onConditionCodeUpdate(v: string) {
  if (!node.value) return;
  const t = v.replace(/\r\n/g, "\n").trim();
  node.value.condition = t === "" ? null : t;
  commit();
}

function conditionPathSuggestionsGetter(): readonly string[] {
  const extra: string[] = [];
  const n = node.value;
  if (n?.type === "task") {
    const b = (n as TaskNode).boundary;
    extra.push(...Object.keys(b.inputs ?? {}), ...Object.values(b.outputs ?? {}));
  }
  return collectContextPathSuggestions(store.doc, extra);
}

function onBoundaryUpdate(b: Boundary) {
  if (!node.value || node.value.type !== "task") return;
  (node.value as TaskNode).boundary = { inputs: { ...b.inputs }, outputs: { ...b.outputs } };
  commit();
}

function cloneBoundaryFromDoc(src: Boundary | undefined | null): Boundary {
  return {
    inputs: { ...(src?.inputs ?? {}) },
    outputs: { ...(src?.outputs ?? {}) },
  };
}

/** 恢复为 ``doc`` 中该节点的参数映射（未 flush 到文档的草稿改动会被丢弃）；新任务在文档里默认空映射，等价于清空。 */
function resetBoundaryMapping() {
  if (!node.value || node.value.type !== "task") return;
  const base = store.getNode(props.path);
  const next: Boundary =
    base?.type === "task" ? cloneBoundaryFromDoc(base.boundary) : { inputs: {}, outputs: {} };
  (node.value as TaskNode).boundary = next;
  boundaryMappingLayoutEpoch.value += 1;
  commit();
}

// ---------------------------------------------------------------------------
// Loop 专属
// ---------------------------------------------------------------------------

const loopCopyItem = computed<LoopCopyItem>(() => {
  if (node.value?.type !== "loop") return "shared";
  return (node.value as LoopNode).copy_item ?? "shared";
});

const loopIsolation = computed<LoopIterationIsolation>(() => {
  if (node.value?.type !== "loop") return "shared";
  return (node.value as LoopNode).iteration_isolation ?? "shared";
});

const collectEnabled = computed<boolean>(() => {
  if (node.value?.type !== "loop") return false;
  return !!(node.value as LoopNode).iteration_collect;
});

function onCopyItemChange(ev: Event) {
  if (!node.value || node.value.type !== "loop") return;
  const v = (ev.target as HTMLSelectElement).value as LoopCopyItem;
  (node.value as LoopNode).copy_item = v;
  commit();
}

function onIsolationChange(ev: Event) {
  if (!node.value || node.value.type !== "loop") return;
  const v = (ev.target as HTMLSelectElement).value as LoopIterationIsolation;
  (node.value as LoopNode).iteration_isolation = v;
  commit();
}

function onCollectToggle(on: boolean) {
  if (!node.value || node.value.type !== "loop") return;
  const loop = node.value as LoopNode;
  if (on) {
    if (!loop.iteration_collect) {
      loop.iteration_collect = { from_path: "", append_to: "" };
    }
  } else {
    loop.iteration_collect = null;
  }
  commit();
}

function onCollectFromPath(v: string) {
  if (!node.value || node.value.type !== "loop") return;
  const loop = node.value as LoopNode;
  if (!loop.iteration_collect) {
    loop.iteration_collect = { from_path: "", append_to: "" };
  }
  loop.iteration_collect.from_path = v;
  commit();
}

function onCollectAppendTo(v: string) {
  if (!node.value || node.value.type !== "loop") return;
  const loop = node.value as LoopNode;
  if (!loop.iteration_collect) {
    loop.iteration_collect = { from_path: "", append_to: "" };
  }
  loop.iteration_collect.append_to = v;
  commit();
}

// ---------------------------------------------------------------------------
// 节点级 CapabilityRule 覆盖（仅 task 节点）
// 后端在 model_dump(exclude_none=True) 时会移除 null 字段；UI 维持 null=未设置。
// ---------------------------------------------------------------------------

const taskCapabilityOverrides = computed<CapabilityRule[]>(() => {
  if (!node.value || node.value.type !== "task") return [];
  return (node.value as TaskNode).capability_overrides ?? [];
});

function onCapabilityOverridesChange(rules: CapabilityRule[]) {
  if (!node.value || node.value.type !== "task") return;
  const t = node.value as TaskNode;
  t.capability_overrides = rules.length === 0 ? null : rules;
  commit();
}

function commit() {
  if (!node.value) return;
  store.updateNodeDraft(props.path, JSON.parse(JSON.stringify(node.value)) as FlowNode);
}
</script>

<style scoped>
.page {
  height: 100%;
  min-height: 0;
  padding: 10px 14px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hd {
  flex: 0 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 2px 2px 0;
  flex-wrap: wrap;
}

.body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.page.is-task .body {
  grid-template-columns: minmax(360px, 5fr) minmax(460px, 7fr);
}

.col {
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: auto;
  padding-right: 2px;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;
}

.col::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
.col::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}
.col::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
.col::-webkit-scrollbar-track {
  background: transparent;
}

.col-right {
  /* 右栏仅脚本编辑器，纵向铺满 */
}

.script-card {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 260px;
  overflow: hidden;
}

.script-sec-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px 14px;
  flex-wrap: wrap;
  flex-shrink: 0;
  margin: -2px 0 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 88%, transparent);
}

.card-cap-rules {
  background: linear-gradient(180deg, #fafbfd 0%, #f4f7fb 100%);
  border-color: color-mix(in srgb, var(--accent) 14%, var(--border));
}

.script-sec-head-left {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.script-sec-title {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: var(--text);
}

.script-sec-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

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

.btn.ghost {
  background: #fff;
  box-shadow: none;
}

.btn.ghost:hover {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  color: var(--accent);
}

.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
}

.btn.primary:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 88%, #000);
}

.btn.primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.nde-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: color-mix(in srgb, #0f172a 32%, transparent);
}

.nde-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 51;
  width: min(480px, calc(100vw - 12px));
  max-width: 100%;
  background: var(--surface);
  border-left: 1px solid var(--border);
  box-shadow: -8px 0 28px rgba(15, 23, 42, 0.14);
  display: flex;
  flex-direction: column;
  transform: translateX(100%);
  transition: transform 0.22s ease-out, visibility 0.22s;
  pointer-events: none;
  visibility: hidden;
}

.nde-drawer--open {
  transform: translateX(0);
  pointer-events: auto;
  visibility: visible;
}

.nde-drawer-hd {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}

.nde-drawer-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.01em;
}

.nde-drawer-hd-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.nde-drawer-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 12px 14px 16px;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;
}

.script-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.hd-main {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.hd-title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text);
}

.hd-path {
  font-size: 11px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 60%;
}

.chip {
  font-size: 10.5px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  background: #eef2f7;
  color: #475569;
}

.chip[data-type="task"] {
  background: #dbeafe;
  color: #1d4ed8;
}
.chip[data-type="loop"] {
  background: #fef3c7;
  color: #92400e;
}
.chip[data-type="subflow"] {
  background: #e0e7ff;
  color: #4338ca;
}

.chip.strategy-chip {
  background: #f0fdf4;
  color: #166534;
  text-transform: none;
  font-family: var(--mono);
  letter-spacing: 0;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  padding: 10px 14px 12px;
  box-shadow: var(--shadow);
}

/* 写在 .card 之后：浅色 .card 背景会覆盖 .script-card--dark，导致标题浅色字落在白底上 */
.card.script-card.script-card--dark {
  background: #1e222a;
  border-color: #3e4451;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 1px 2px rgba(15, 23, 42, 0.12);
}

.card.script-card.script-card--dark .script-sec-head {
  border-bottom-color: rgba(255, 255, 255, 0.14);
}

.card.script-card.script-card--dark .script-sec-title {
  color: #f8fafc;
  letter-spacing: 0.02em;
}

.card.script-card.script-card--dark :deep(.info-tip) {
  color: #94a3b8;
}

.card.script-card.script-card--dark :deep(.info-tip:hover),
.card.script-card.script-card--dark :deep(.info-tip:focus-visible) {
  color: #e2e8f0;
}

.sec-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: var(--text);
  margin-bottom: 10px;
}

.sec-title > span:first-child {
  color: var(--text);
}

.sec-title .mini {
  margin-left: auto;
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 12px;
}

.grid-task-basic {
  grid-template-columns: 1fr;
}

.task-strategy-inner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
}

.strat-sel {
  flex: 1 1 160px;
  min-width: 140px;
  max-width: 320px;
}

.wait-inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
  font-weight: 500;
  cursor: pointer;
  user-select: none;
}

.wait-inline input[type="checkbox"] {
  margin: 0;
  width: 14px;
  height: 14px;
  accent-color: var(--accent);
}

.cond-editor-wrap {
  display: flex;
  flex-direction: column;
  min-height: 38px;
}

.cond-editor-wrap :deep(.wrap) {
  flex: 0 0 auto;
  min-height: 0;
}

.card-compact {
  padding: 8px 12px 10px;
}

.sec-title-tight {
  margin-bottom: 6px;
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

.field.check {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.field.check input[type="checkbox"] {
  margin: 0;
  width: 14px;
  height: 14px;
  accent-color: var(--accent);
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

.inp.invalid {
  border-color: #fca5a5;
  background: #fff7f7;
}

textarea.inp.node-desc {
  /* 约两行正文 + .inp 上下 padding(7px*2) */
  min-height: calc(2 * 1.45em + 14px);
  resize: vertical;
  font-family: inherit;
  line-height: 1.45;
}

.err {
  font-size: 11px;
  color: #b91c1c;
  margin-top: 1px;
}

.area {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.55;
  resize: vertical;
  outline: none;
  background: #fbfdff;
  color: var(--text);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.area:focus {
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.area.invalid {
  border-color: #fca5a5;
  background: #fff7f7;
}

.err-block {
  margin: 5px 2px 0;
  font-size: 11px;
  color: #b91c1c;
  line-height: 1.45;
}

.ctx-hint {
  margin: 5px 2px 0;
  font-size: 11px;
  color: var(--muted);
}

.mini {
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
  color: var(--muted);
  font-weight: 500;
  transition: all 0.15s ease;
}

.mini.ghost:hover:not(:disabled) {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
}

.mini:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

@media (max-width: 1100px) {
  .page.is-task .body {
    grid-template-columns: 1fr;
    overflow: auto;
  }
  .page.is-task .col {
    overflow: visible;
    padding-right: 0;
  }
  .page.is-task .script-card {
    min-height: 320px;
    flex: 0 0 auto;
  }
}

@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
