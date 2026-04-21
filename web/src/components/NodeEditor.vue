<template>
  <div v-if="node" class="page">
    <header class="hd">
      <div>
        <div class="t">{{ title }}</div>
        <div class="s mono">{{ path.join(" → ") }}</div>
      </div>
      <div class="chips">
        <span class="chip">{{ node.type }}</span>
        <span class="chip">{{ node.strategy_ref }}</span>
      </div>
    </header>

    <section class="card">
      <div class="sec-title">基础信息</div>
      <div class="grid">
        <label class="field">
          <span>
            id（逻辑主键，必填）
            <span class="hint-inline">字母开头，仅允许字母/数字/下划线</span>
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
          <span>
            name（显示名）
            <span class="hint-inline">仅可视化使用，可输入中文/任意字符；留空将自动回落到 id</span>
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
          <span>strategy_ref</span>
          <select v-model="node.strategy_ref" class="inp" @change="commit">
            <option v-for="k in store.strategiesList" :key="k" :value="k">{{ k }}</option>
          </select>
        </label>

        <label class="field check">
          <input v-model="node.wait_before" type="checkbox" @change="commit" />
          <span>wait_before（滑动窗口同步屏障）</span>
        </label>

        <label class="field full">
          <span>condition（Starlark 表达式，可选）</span>
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
      <div class="sec-title">边界映射</div>
      <div class="sec-desc">
        <p class="d">
          使用 YAML 风格文本，<span class="mono">inputs</span> 与 <span class="mono">outputs</span> 两个顶级键，每条映射以 <span class="mono">key: value</span> 缩进书写。空行与 <span class="mono">#</span> 开头的行视为注释。
        </p>
        <p class="d">
          <strong>inputs</strong>：<span class="mono">$.上下文路径 → Starlark 变量名</span>；<strong>outputs</strong>：<span class="mono">脚本返回字段 → $.上下文路径</span>。
        </p>
        <p class="d muted">
          后续将在 value 位置扩展参数约束与校验（例如
          <span class="mono">$.item: {var: alarm, required: true, type: dict}</span>）。
        </p>
      </div>

      <div class="kvhead">
        <span>inputs / outputs 定义</span>
        <button type="button" class="mini ghost" :disabled="!boundaryDirty" @click="resetBoundaryText">
          恢复为已解析版本
        </button>
      </div>
      <textarea
        v-model="boundaryText"
        class="area mono"
        :class="{ invalid: boundaryErrors.length > 0 }"
        rows="10"
        spellcheck="false"
        :placeholder="boundaryPlaceholder"
      />
      <div v-if="boundaryErrors.length > 0" class="err-block">
        <div v-for="(msg, i) in boundaryErrors" :key="'b-err-' + i">{{ msg }}</div>
      </div>
      <div v-else class="ctx-hint">{{ boundaryCountHint }}</div>
    </section>

    <section v-if="node.type === 'loop'" class="card">
      <div class="sec-title">循环</div>
      <div class="grid">
        <label class="field full">
          <span>iterable（Starlark 表达式，或 <code>$.path</code> 简写）</span>
          <input
            v-model="node.iterable"
            class="inp mono"
            placeholder='$.global.items   或   resolve("$.global.items")'
            @input="commit"
          />
        </label>
        <label class="field">
          <span>alias</span>
          <input v-model="node.alias" class="inp mono" @input="commit" />
        </label>
        <label class="field">
          <span>
            copy_item
            <span class="hint-inline">每次迭代绑定 <span class="mono">$.item</span> 的方式</span>
          </span>
          <select :value="loopCopyItem" class="inp" @change="onCopyItemChange">
            <option value="shared">shared（引用，默认）</option>
            <option value="shallow">shallow（copy.copy）</option>
            <option value="deep">deep（copy.deepcopy）</option>
          </select>
        </label>
        <label class="field">
          <span>
            iteration_isolation
            <span class="hint-inline">迭代上下文是否与父 ctx 隔离</span>
          </span>
          <select :value="loopIsolation" class="inp" @change="onIsolationChange">
            <option value="shared">shared（共享 $.global，默认）</option>
            <option value="fork">fork（每次迭代独立深拷贝）</option>
          </select>
        </label>
      </div>

      <div class="subcard">
        <label class="field check">
          <input
            type="checkbox"
            :checked="collectEnabled"
            @change="onCollectToggle(($event.target as HTMLInputElement).checked)"
          />
          <span>
            iteration_collect（把每次迭代结果追加到父 ctx 的 list）
            <span class="hint-inline">常配合 <span class="mono">iteration_isolation: fork</span> 使用</span>
          </span>
        </label>
        <div v-if="collectEnabled" class="grid">
          <label class="field">
            <span>from_path（从迭代 ctx 读取的 <span class="mono">$.</span> 路径）</span>
            <input
              :value="node.iteration_collect?.from_path ?? ''"
              class="inp mono"
              placeholder="$.global.per_item_result"
              @input="onCollectFromPath(($event.target as HTMLInputElement).value)"
            />
          </label>
          <label class="field">
            <span>append_to（父 ctx 的 list 路径）</span>
            <input
              :value="node.iteration_collect?.append_to ?? ''"
              class="inp mono"
              placeholder="$.global.results"
              @input="onCollectAppendTo(($event.target as HTMLInputElement).value)"
            />
          </label>
        </div>
      </div>

      <div class="hint">
        子节点在左侧树中编辑；循环体会继承 <span class="mono">$.item</span> 上下文。
        <span v-if="loopIsolation === 'fork'">
          当前为 <span class="mono">fork</span> 隔离，迭代里对 <span class="mono">$.global</span> 的写入不会回到父 ctx，如需汇总请启用 iteration_collect。
        </span>
      </div>
    </section>

    <section v-if="node.type === 'subflow'" class="card">
      <div class="sec-title">子流程</div>
      <label class="field">
        <span>alias</span>
        <input v-model="node.alias" class="inp mono" @input="commit" />
      </label>
      <div class="hint">子节点在左侧树中编辑。</div>
    </section>

    <section v-if="node.type === 'task'" class="card">
      <div class="sec-title">Starlark 脚本</div>
      <CodeEditor v-model="node.script" :height="340" :registry="starlarkRegistry" @update:model-value="commit" />
    </section>

    <DebugPanel v-if="node.type === 'task'" :path="path" />
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
  // name 允许任意字符串；仅做 UI 绑定，不参与业务逻辑。
  const next = nameText.value;
  if (node.value.name !== next) {
    node.value.name = next;
    commit();
  }
}

function onNameBlur() {
  // 失焦时若 name 为空白，回落为 id（与后端 model_validator 行为一致，
  // 保证 UI/持久化里 name 始终是人类可读字符串）。
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
// Loop 专属：copy_item / iteration_isolation / iteration_collect
//   * 后端 (models.LoopNode) 的默认值是 shared / shared / None，
//     加载草稿时若字段缺失，计算属性会回落到这些默认值，并把实际的默认值
//     写回节点以便再次提交时与后端序列化结果保持一致。
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
// 边界映射：单一文本框，YAML 风格 ``inputs`` / ``outputs`` 顶级键
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
  if (nin === 0 && nout === 0) return "尚未配置任何边界映射。";
  return `已解析 inputs ${nin} 条、outputs ${nout} 条。`;
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

// ---------------------------------------------------------------------------

function commit() {
  if (!node.value) return;
  store.updateNodeDraft(props.path, JSON.parse(JSON.stringify(node.value)) as FlowNode);
}
</script>

<style scoped>
.page {
  padding: 16px;
  max-width: 1100px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.hd {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.t {
  font-size: 16px;
  font-weight: 900;
  letter-spacing: -0.02em;
}

.s {
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}

.chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.chip {
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
}

.card {
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface);
  padding: 12px;
  box-shadow: var(--shadow);
}

.sec-title {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.02em;
  margin-bottom: 10px;
}

.sec-desc {
  margin: -2px 0 10px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
}

.sec-desc .d {
  margin: 0 0 4px;
}

.sec-desc .muted {
  opacity: 0.75;
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.field {
  display: grid;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
}

.field.full {
  grid-column: 1 / -1;
}

.field.check {
  grid-column: 1 / -1;
  display: flex;
  gap: 8px;
  align-items: center;
}

.hint-inline {
  margin-left: 6px;
  font-weight: 400;
  font-size: 11px;
  color: color-mix(in srgb, var(--muted) 80%, transparent);
}

.inp {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 9px 10px;
  outline: none;
  font-size: 13px;
  background: #fff;
}

.inp:focus {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.inp.invalid {
  border-color: #fca5a5;
  background: #fff7f7;
}

.err {
  font-size: 11px;
  color: #b91c1c;
}

.kvhead {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 10px 0 6px;
  font-size: 12px;
  color: var(--muted);
}

.area {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px;
  font-size: 12px;
  line-height: 1.5;
  resize: vertical;
  outline: none;
  background: #fbfdff;
}

.area:focus {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.area.invalid {
  border-color: #fca5a5;
  background: #fff7f7;
}

.err-block {
  margin: 4px 2px 0;
  font-size: 11px;
  color: #b91c1c;
  line-height: 1.45;
}

.ctx-hint {
  margin: 4px 2px 0;
  font-size: 11px;
  color: var(--muted);
}

.mini {
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 8px;
  padding: 4px 9px;
  font-size: 11px;
  cursor: pointer;
}

.mini.ghost {
  color: var(--muted);
}

.mini:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.mini:hover:not(:disabled) {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
}

.hint {
  margin-top: 10px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
}

.subcard {
  margin-top: 10px;
  padding: 10px;
  border: 1px dashed var(--border);
  border-radius: 10px;
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.subcard .grid {
  gap: 10px;
}

@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
