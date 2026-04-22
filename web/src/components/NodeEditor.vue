<template>
  <div v-if="node" class="page" :class="{ 'is-task': node.type === 'task' }">
    <header class="hd">
      <div class="hd-main">
        <span class="hd-title">{{ title }}</span>
        <span class="chip" :data-type="node.type">{{ node.type }}</span>
        <span class="chip strategy-chip" :title="`策略：${node.strategy_ref}`">{{ node.strategy_ref }}</span>
      </div>
      <div class="hd-path mono" :title="path.join(' → ')">{{ path.join(" → ") }}</div>
    </header>

    <div class="body">
      <div class="col col-left">
        <section class="card">
          <div class="sec-title">
            <span>基础信息</span>
          </div>
          <div class="grid">
            <label class="field">
              <span class="lbl-row">
                id<span class="req">*</span>
                <InfoTip text="逻辑主键，字母开头，仅允许字母 / 数字 / 下划线。流程内唯一。" />
              </span>
              <input
                v-model="idText"
                class="inp mono"
                :class="{ invalid: idError !== null }"
                placeholder="例如：ingest_alert"
                spellcheck="false"
                autocomplete="off"
                @input="onIdInput"
                @blur="onIdBlur"
              />
              <span v-if="idError" class="err">{{ idError }}</span>
            </label>

            <label class="field">
              <span class="lbl-row">
                name
                <InfoTip text="显示名，支持中文 / 任意字符；留空自动回落到 id。" />
              </span>
              <input
                v-model="nameText"
                class="inp"
                placeholder="例如：告警归一化"
                @input="onNameInput"
                @blur="onNameBlur"
              />
            </label>

            <label class="field">
              <span class="lbl-row">
                strategy_ref<span class="req">*</span>
                <InfoTip text="引用流程属性中定义的运行策略。" />
              </span>
              <select v-model="node.strategy_ref" class="inp" @change="commit">
                <option v-for="k in store.strategiesList" :key="k" :value="k">{{ k }}</option>
              </select>
            </label>

            <label class="field check">
              <input v-model="node.wait_before" type="checkbox" @change="commit" />
              <span class="lbl-row">
                wait_before
                <InfoTip text="滑动窗口同步屏障：等待同层已派发的异步节点完成后再进入本节点。" />
              </span>
            </label>

            <label class="field full">
              <span class="lbl-row">
                condition
                <InfoTip text="Starlark 表达式，可选。为 False 时跳过本节点。" />
              </span>
              <input
                class="inp mono"
                placeholder="例如：True"
                :value="node.condition ?? ''"
                @input="onConditionInput"
              />
            </label>
          </div>
        </section>

        <section v-if="node.type === 'task'" class="card">
          <div class="sec-title">
            <span>边界映射</span>
            <InfoTip
              wide
              text="YAML 风格文本。inputs：$.上下文路径 → Starlark 变量名；outputs：脚本返回字段 → $.上下文路径。空行与 # 开头行视为注释。"
            />
            <button
              type="button"
              class="mini ghost"
              :disabled="!boundaryDirty"
              @click="resetBoundaryText"
            >
              重置
            </button>
          </div>
          <textarea
            v-model="boundaryText"
            class="area mono"
            :class="{ invalid: boundaryErrors.length > 0 }"
            rows="6"
            spellcheck="false"
            :placeholder="boundaryPlaceholder"
          />
          <div v-if="boundaryErrors.length > 0" class="err-block">
            <div v-for="(msg, i) in boundaryErrors" :key="'b-err-' + i">{{ msg }}</div>
          </div>
          <div v-else class="ctx-hint">{{ boundaryCountHint }}</div>
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
        <section class="card script-card">
          <div class="sec-title">
            <span>Starlark 脚本</span>
            <InfoTip text="节点执行逻辑。通过 inputs 注入变量，结果经由 outputs 写回上下文。" />
          </div>
          <div class="script-body">
            <CodeEditor
              v-model="node.script"
              fill
              :registry="starlarkRegistry"
              @update:model-value="commit"
            />
          </div>
        </section>

        <DebugPanel :path="path" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import type {
  FlowNode,
  LoopCopyItem,
  LoopIterationIsolation,
  LoopNode,
  TaskNode,
} from "@/types/flow";
import { useFlowStudioStore } from "@/stores/flowStudio";
import { useStarlarkRegistryCache } from "@/composables/useStarlarkRegistryCache";
import CodeEditor from "./CodeEditor.vue";
import DebugPanel from "./DebugPanel.vue";
import InfoTip from "./InfoTip.vue";
import { parseBoundaryDoc, serializeBoundaryDoc } from "@/utils/boundaryText";

const props = defineProps<{ path: number[] }>();
const store = useFlowStudioStore();
const { registry: starlarkRegistry, ensureRegistry } = useStarlarkRegistryCache();

onMounted(() => {
  void ensureRegistry();
});

const node = computed(() => store.editableNode(props.path) as FlowNode | null);

const title = computed(() => {
  if (!node.value) return "";
  if (node.value.type === "task") return "Task 节点";
  if (node.value.type === "loop") return "Loop 节点";
  return "Subflow 节点";
});

// ---------------------------------------------------------------------------
// 基础信息：id（严格主键）、name（显示名）
// ---------------------------------------------------------------------------

const idText = ref("");
const nameText = ref("");

watch(
  () => props.path.join("/"),
  () => {
    idText.value = node.value?.id ?? "";
    nameText.value = node.value?.name ?? "";
  },
  { immediate: true },
);

const otherIds = computed(() => {
  const all = store.collectAllNodeIds();
  const own = (node.value?.id ?? "").trim();
  if (own) all.delete(own);
  return all;
});

const idError = computed<string | null>(() => {
  const v = idText.value.trim();
  if (!v) return "id 必填";
  if (!store.isValidNodeId(v)) return "只允许字母开头，字母/数字/下划线";
  if (otherIds.value.has(v)) return "与其它节点 id 冲突";
  return null;
});

function onIdInput() {
  if (!node.value) return;
  const v = idText.value.trim();
  // 输入过程中的实时校验只显示提示，不回写非法值，避免把流程弄脏。
  if (idError.value) return;
  if (node.value.id !== v) {
    node.value.id = v;
    commit();
  }
}

function onIdBlur() {
  if (idError.value) {
    // 非法 id 失焦时把当前值回退为最后一次有效 id，避免污染持久化数据。
    idText.value = node.value?.id ?? "";
  }
}

function onNameInput() {
  if (!node.value) return;
  const next = nameText.value;
  if (node.value.name !== next) {
    node.value.name = next;
    commit();
  }
}

function onNameBlur() {
  // 失焦时若 name 为空白，回落为 id（与后端 model_validator 行为一致）。
  if (!node.value) return;
  if (!nameText.value.trim()) {
    const fallback = (node.value.id ?? "").trim();
    nameText.value = fallback;
    if (node.value.name !== fallback) {
      node.value.name = fallback;
      commit();
    }
  }
}

function onConditionInput(ev: Event) {
  if (!node.value) return;
  const v = (ev.target as HTMLInputElement).value;
  node.value.condition = v.trim() === "" ? null : v;
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
// 边界映射
// ---------------------------------------------------------------------------

const boundaryText = ref("");
const boundaryErrors = ref<string[]>([]);

const boundaryPlaceholder = `inputs:
  $.global.alert: alert
outputs:
  summary: $.global.summary`;

function currentBoundarySerialized(): string {
  if (!node.value || node.value.type !== "task") return "";
  const b = (node.value as TaskNode).boundary;
  return serializeBoundaryDoc({ inputs: b.inputs ?? {}, outputs: b.outputs ?? {} });
}

const boundaryDirty = computed(() => boundaryText.value !== currentBoundarySerialized());

const boundaryCountHint = computed(() => {
  if (!node.value || node.value.type !== "task") return "";
  const b = (node.value as TaskNode).boundary;
  const nin = Object.keys(b.inputs ?? {}).length;
  const nout = Object.keys(b.outputs ?? {}).length;
  if (nin === 0 && nout === 0) return "尚未配置边界映射";
  return `inputs ${nin} 条 · outputs ${nout} 条`;
});

watch(
  () => props.path.join("/"),
  () => {
    boundaryText.value = currentBoundarySerialized();
    boundaryErrors.value = [];
  },
  { immediate: true },
);

watch(boundaryText, (txt) => {
  if (!node.value || node.value.type !== "task") return;
  const res = parseBoundaryDoc(txt);
  boundaryErrors.value = res.errors;
  if (res.errors.length === 0) {
    const b = (node.value as TaskNode).boundary;
    b.inputs = res.data.inputs;
    b.outputs = res.data.outputs;
    commit();
  }
});

function resetBoundaryText() {
  boundaryText.value = currentBoundarySerialized();
  boundaryErrors.value = [];
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
  /* 右栏：Starlark 卡弹性撑满，调试卡保持自然高度。 */
}

.script-card {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 260px;
  overflow: hidden;
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
