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
          <span>name</span>
          <input v-model="node.name" class="inp" @change="commit" />
        </label>
        <label class="field">
          <span>id（可选）</span>
          <input v-model="idText" class="inp" @change="commit" />
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
            @input="
              node.condition = ($event.target as HTMLInputElement).value || null;
              commit();
            "
          />
        </label>
      </div>
    </section>

    <section v-if="node.type === 'task'" class="card">
      <div class="sec-title">边界映射</div>
      <div class="kvhead">
        <span>inputs（$. 路径 → Starlark 变量名）</span>
      </div>
      <div v-for="(varName, pathKey) in node.boundary.inputs" :key="'in-' + String(pathKey)" class="kv">
        <input
          class="inp mono"
          :value="String(pathKey)"
          @blur="renameInPath(String(pathKey), ($event.target as HTMLInputElement).value)"
        />
        <span class="arrow">→</span>
        <input
          class="inp mono"
          :value="String(varName)"
          @input="setInVar(String(pathKey), ($event.target as HTMLInputElement).value)"
        />
        <button type="button" class="x" @click="delIn(String(pathKey))">×</button>
      </div>
      <div class="kv new">
        <input
          v-model="newIn.path"
          class="inp mono"
          placeholder="$.global.x"
          @blur="maybeAddInFromDraft"
          @keydown.enter.prevent="addIn"
        />
        <span class="arrow">→</span>
        <input
          v-model="newIn.var"
          class="inp mono"
          placeholder="var"
          @blur="maybeAddInFromDraft"
          @keydown.enter.prevent="addIn"
        />
        <button type="button" class="mini" @click="addIn">添加</button>
      </div>

      <div class="kvhead">
        <span>outputs（结果键 → $. 路径）</span>
      </div>
      <div v-for="(pathVal, outKey) in node.boundary.outputs" :key="'out-' + String(outKey)" class="kv">
        <input
          class="inp mono"
          :value="String(outKey)"
          @blur="renameOutKey(String(outKey), ($event.target as HTMLInputElement).value)"
        />
        <span class="arrow">→</span>
        <input
          class="inp mono"
          :value="String(pathVal)"
          @input="setOutPath(String(outKey), ($event.target as HTMLInputElement).value)"
        />
        <button type="button" class="x" @click="delOut(String(outKey))">×</button>
      </div>
      <div class="kv new">
        <input
          v-model="newOut.key"
          class="inp mono"
          placeholder="field"
          @blur="maybeAddOutFromDraft"
          @keydown.enter.prevent="addOut"
        />
        <span class="arrow">→</span>
        <input
          v-model="newOut.path"
          class="inp mono"
          placeholder="$.global.y"
          @blur="maybeAddOutFromDraft"
          @keydown.enter.prevent="addOut"
        />
        <button type="button" class="mini" @click="addOut">添加</button>
      </div>
    </section>

    <section v-if="node.type === 'loop'" class="card">
      <div class="sec-title">循环</div>
      <div class="grid">
        <label class="field full">
          <span>iterable（Starlark 表达式）</span>
          <input v-model="node.iterable" class="inp mono" @change="commit" />
        </label>
        <label class="field">
          <span>alias</span>
          <input v-model="node.alias" class="inp mono" @change="commit" />
        </label>
      </div>
      <div class="hint">子节点在左侧树中编辑；循环体会继承 <span class="mono">$.item</span> 上下文。</div>
    </section>

    <section v-if="node.type === 'subflow'" class="card">
      <div class="sec-title">子流程</div>
      <label class="field">
        <span>alias</span>
        <input v-model="node.alias" class="inp mono" @change="commit" />
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
import { computed, onMounted, reactive, watch } from "vue";
import type { FlowNode } from "@/types/flow";
import { useFlowStudioStore } from "@/stores/flowStudio";
import { useStarlarkRegistryCache } from "@/composables/useStarlarkRegistryCache";
import CodeEditor from "./CodeEditor.vue";
import DebugPanel from "./DebugPanel.vue";

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

const idText = computed({
  get: () => node.value?.id ?? "",
  set: (v: string) => {
    if (!node.value) return;
    node.value.id = v.trim() === "" ? null : v.trim();
  },
});

const newIn = reactive({ path: "", var: "" });
const newOut = reactive({ key: "", path: "" });

watch(
  () => props.path.join("/"),
  () => {
    newIn.path = "";
    newIn.var = "";
    newOut.key = "";
    newOut.path = "";
  },
);

function commit() {
  if (!node.value) return;
  store.updateNodeDraft(props.path, JSON.parse(JSON.stringify(node.value)) as FlowNode);
}

function addIn() {
  if (!node.value || node.value.type !== "task") return;
  const p = newIn.path.trim();
  const v = newIn.var.trim();
  if (!p || !v) return;
  node.value.boundary.inputs[p] = v;
  newIn.path = "";
  newIn.var = "";
  commit();
}

function maybeAddInFromDraft() {
  if (!newIn.path.trim() || !newIn.var.trim()) return;
  addIn();
}

function addOut() {
  if (!node.value || node.value.type !== "task") return;
  const k = newOut.key.trim();
  const p = newOut.path.trim();
  if (!k || !p) return;
  node.value.boundary.outputs[k] = p;
  newOut.key = "";
  newOut.path = "";
  commit();
}

function maybeAddOutFromDraft() {
  if (!newOut.key.trim() || !newOut.path.trim()) return;
  addOut();
}

function delIn(k: string) {
  if (!node.value || node.value.type !== "task") return;
  delete node.value.boundary.inputs[k];
  commit();
}

function delOut(k: string) {
  if (!node.value || node.value.type !== "task") return;
  delete node.value.boundary.outputs[k];
  commit();
}

function setInVar(pathKey: string, val: string) {
  if (!node.value || node.value.type !== "task") return;
  node.value.boundary.inputs[pathKey] = val;
  commit();
}

function renameInPath(oldPath: string, newPath: string) {
  if (!node.value || node.value.type !== "task") return;
  const np = newPath.trim();
  if (!np || np === oldPath) return;
  const v = node.value.boundary.inputs[oldPath];
  delete node.value.boundary.inputs[oldPath];
  node.value.boundary.inputs[np] = v;
  commit();
}

function setOutPath(outKey: string, val: string) {
  if (!node.value || node.value.type !== "task") return;
  node.value.boundary.outputs[outKey] = val;
  commit();
}

function renameOutKey(oldK: string, newK: string) {
  if (!node.value || node.value.type !== "task") return;
  const nk = newK.trim();
  if (!nk || nk === oldK) return;
  const v = node.value.boundary.outputs[oldK];
  delete node.value.boundary.outputs[oldK];
  node.value.boundary.outputs[nk] = v;
  commit();
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

.kvhead {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 10px 0 6px;
  font-size: 12px;
  color: var(--muted);
}

.kv {
  display: grid;
  grid-template-columns: 1fr auto 1fr auto;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.kv.new {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
}

.arrow {
  color: var(--muted);
  font-size: 12px;
}

.mini {
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 10px;
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
}

.x {
  border: 1px solid color-mix(in srgb, #ef4444 30%, transparent);
  background: #fff;
  color: #b91c1c;
  border-radius: 10px;
  width: 34px;
  cursor: pointer;
}

.hint {
  margin-top: 10px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
}

@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
  .kv {
    grid-template-columns: 1fr;
  }
  .arrow {
    display: none;
  }
}
</style>
