<template>
  <div class="bmap">
    <datalist :id="pathDatalistId">
      <option v-for="p in pathOptions" :key="p" :value="p" />
    </datalist>

    <div class="bmap-grid">
      <section
        class="bmap-pane bmap-pane--in"
        aria-label="从上下文映射到任务变量（inputs）"
      >
        <div class="bmap-sheet">
            <div class="bmap-cols bmap-head" aria-hidden="true">
              <span class="bmap-col-idx" />
              <span>变量名</span>
              <span class="bmap-col-flow" />
              <span>上下文路径</span>
              <span class="bmap-col-act" />
            </div>
            <div class="bmap-rows" role="list">
            <div
              v-for="(row, i) in inputRows"
              :key="'in-' + i"
              class="bmap-cols bmap-row"
              role="listitem"
              :class="{
                'bmap-row--err': inputRowHasError(i),
                'bmap-row--draft': isScratchInputRow(i),
              }"
            >
              <span class="bmap-idx mono">{{ i + 1 }}</span>
              <input
                v-model="row.left"
                class="bmap-inp"
                spellcheck="false"
                autocomplete="off"
                placeholder="变量名"
                :aria-invalid="inputRowHasError(i)"
                aria-label="入参变量名"
                @input="onRowInput"
              />
              <span class="bmap-flow" aria-hidden="true">←</span>
              <input
                v-model="row.right"
                class="bmap-inp mono"
                spellcheck="false"
                autocomplete="off"
                placeholder="$.global…"
                :list="pathDatalistId"
                :aria-invalid="inputRowHasError(i)"
                aria-label="入参上下文路径"
                @input="onRowInput"
              />
              <div class="bmap-col-act">
                <button
                  type="button"
                  class="bmap-ibtn"
                  title="在下方插入一行"
                  aria-label="在下方插入入参行"
                  @click.stop="addInputRowBelow(i)"
                >
                  <svg class="bmap-ico" viewBox="0 0 16 16" aria-hidden="true">
                    <path
                      d="M8 3.5v9M3.5 8h9"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.35"
                      stroke-linecap="round"
                    />
                  </svg>
                </button>
                <button
                  v-if="canRemoveInputRow(i)"
                  type="button"
                  class="bmap-ibtn bmap-ibtn--danger"
                  title="删除本行"
                  aria-label="删除入参行"
                  @click.stop="removeInputRow(i)"
                >
                  <svg class="bmap-ico" viewBox="0 0 16 16" aria-hidden="true">
                    <path
                      d="M5 5.5h6L10 13H6L5 5.5zM6.5 5.5V4h3v1.5"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                    <path d="M7 8v3.5M9 8v3.5" fill="none" stroke="currentColor" stroke-width="1.15" stroke-linecap="round" />
                  </svg>
                </button>
              </div>
            </div>
            </div>
          </div>
      </section>

      <section
        class="bmap-pane bmap-pane--out"
        aria-label="任务返回值写回上下文（outputs）"
      >
        <div class="bmap-sheet">
            <div class="bmap-cols bmap-head" aria-hidden="true">
              <span class="bmap-col-idx" />
              <span>返回字段</span>
              <span class="bmap-col-flow" />
              <span>上下文路径</span>
              <span class="bmap-col-act" />
            </div>
            <div class="bmap-rows" role="list">
            <div
              v-for="(row, i) in outputRows"
              :key="'out-' + i"
              class="bmap-cols bmap-row"
              role="listitem"
              :class="{
                'bmap-row--err': outputRowHasError(i),
                'bmap-row--draft': isScratchOutputRow(i),
              }"
            >
              <span class="bmap-idx mono">{{ i + 1 }}</span>
              <input
                v-model="row.left"
                class="bmap-inp mono"
                spellcheck="false"
                autocomplete="off"
                placeholder="字段名"
                :aria-invalid="outputRowHasError(i)"
                aria-label="出参返回字段"
                @input="onRowInput"
              />
              <span class="bmap-flow" aria-hidden="true">→</span>
              <input
                v-model="row.right"
                class="bmap-inp mono"
                spellcheck="false"
                autocomplete="off"
                placeholder="$.global…"
                :list="pathDatalistId"
                :aria-invalid="outputRowHasError(i)"
                aria-label="出参上下文路径"
                @input="onRowInput"
              />
              <div class="bmap-col-act">
                <button
                  type="button"
                  class="bmap-ibtn"
                  title="在下方插入一行"
                  aria-label="在下方插入出参行"
                  @click.stop="addOutputRowBelow(i)"
                >
                  <svg class="bmap-ico" viewBox="0 0 16 16" aria-hidden="true">
                    <path
                      d="M8 3.5v9M3.5 8h9"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.35"
                      stroke-linecap="round"
                    />
                  </svg>
                </button>
                <button
                  v-if="canRemoveOutputRow(i)"
                  type="button"
                  class="bmap-ibtn bmap-ibtn--danger"
                  title="删除本行"
                  aria-label="删除出参行"
                  @click.stop="removeOutputRow(i)"
                >
                  <svg class="bmap-ico" viewBox="0 0 16 16" aria-hidden="true">
                    <path
                      d="M5 5.5h6L10 13H6L5 5.5zM6.5 5.5V4h3v1.5"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                    <path d="M7 8v3.5M9 8v3.5" fill="none" stroke="currentColor" stroke-width="1.15" stroke-linecap="round" />
                  </svg>
                </button>
              </div>
            </div>
            </div>
          </div>
      </section>
    </div>

    <div v-if="errors.length" class="bmap-err" role="alert" aria-live="polite">
      <ul class="bmap-err-list">
        <li v-for="(msg, i) in errors" :key="'e-' + i">{{ msg }}</li>
      </ul>
    </div>
    <div v-else-if="countBrief" class="bmap-meta">{{ countBrief }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { Boundary } from "@/types/flow";
import { useFlowStudioStore } from "@/stores/flowStudio";
import { collectContextPathSuggestions } from "@/utils/contextPathSuggestions";
import {
  validateBoundaryInputMapping,
  validateBoundaryOutputMapping,
} from "@/utils/boundaryText";

const props = defineProps<{
  modelValue: Boundary;
  syncKey: string;
}>();

const emit = defineEmits<{ (e: "update:modelValue", v: Boundary): void }>();

const store = useFlowStudioStore();

const pathDatalistId = computed(() =>
  `fe-bmap-paths-${props.syncKey.replace(/[^\w-]/g, "_")}`,
);

type Row = { left: string; right: string };

const inputRows = ref<Row[]>([{ left: "", right: "" }]);
const outputRows = ref<Row[]>([{ left: "", right: "" }]);
const errors = ref<string[]>([]);

/** 与 tryEmit 写入的语义一致，避免键顺序导致误判「父组件已更新」而冲掉本地草稿行。 */
function stableBoundaryJson(b: Boundary | undefined | null): string {
  const ins = b?.inputs ?? {};
  const outs = b?.outputs ?? {};
  return JSON.stringify({
    inputs: Object.fromEntries(Object.entries(ins).sort(([a], [b]) => a.localeCompare(b))),
    outputs: Object.fromEntries(Object.entries(outs).sort(([a], [b]) => a.localeCompare(b))),
  });
}

const lastSyncKey = ref<string | null>(null);
/** 最近一次成功下发到父组件的边界（稳定序列化）；用于识别 props 回显、跳过用 inputs/outputs 重建行。 */
const lastEmittedStable = ref<string | null>(null);

function isEmptyRow(r: Row): boolean {
  return !r.left.trim() && !r.right.trim();
}

function isScratchInputRow(i: number): boolean {
  return i === inputRows.value.length - 1 && isEmptyRow(inputRows.value[i]);
}

function isScratchOutputRow(i: number): boolean {
  return i === outputRows.value.length - 1 && isEmptyRow(outputRows.value[i]);
}

function canRemoveInputRow(_i: number): boolean {
  return inputRows.value.length > 1;
}

function canRemoveOutputRow(_i: number): boolean {
  return outputRows.value.length > 1;
}

/** 尾部最多保留一个全空行作为「新行」占位；从底部向上合并连续空行。 */
function collapseDuplicateTrailingEmpty(which: "in" | "out") {
  const rows = which === "in" ? inputRows : outputRows;
  while (rows.value.length >= 2) {
    const n = rows.value.length;
    if (isEmptyRow(rows.value[n - 1]) && isEmptyRow(rows.value[n - 2])) {
      rows.value.splice(n - 2, 1);
    } else {
      break;
    }
  }
}

function rowsFromInputs(inputs: Record<string, string>): Row[] {
  const entries = Object.entries(inputs ?? {});
  const r = entries.map(([ctxPath, varName]) => ({ left: varName, right: ctxPath }));
  if (r.length === 0) return [{ left: "", right: "" }];
  r.push({ left: "", right: "" });
  return r;
}

function rowsFromOutputs(outputs: Record<string, string>): Row[] {
  const entries = Object.entries(outputs ?? {});
  const r = entries.map(([field, ctxPath]) => ({ left: field, right: ctxPath }));
  if (r.length === 0) return [{ left: "", right: "" }];
  r.push({ left: "", right: "" });
  return r;
}

function reconcileErrorsOnly() {
  errors.value = buildBoundary().errors;
}

watch(
  () => [props.syncKey, stableBoundaryJson(props.modelValue)] as const,
  ([syncKey, incomingStable]) => {
    const navigated = lastSyncKey.value !== syncKey;
    lastSyncKey.value = syncKey;

    const { boundary: semanticBoundary, errors: rowErrs } = buildBoundary();
    const semanticLocal = stableBoundaryJson(semanticBoundary);

    /** 父级回显与本地一致：不重建行，避免 tryEmit 未上行时（如仅多插了空行）被冲掉。 */
    const echoFromSelf =
      !navigated &&
      incomingStable === lastEmittedStable.value &&
      (rowErrs.length > 0 || semanticLocal === incomingStable);

    if (!echoFromSelf) {
      inputRows.value = rowsFromInputs(props.modelValue.inputs ?? {});
      outputRows.value = rowsFromOutputs(props.modelValue.outputs ?? {});
      lastEmittedStable.value = incomingStable;
    }
    reconcileErrorsOnly();
  },
  { immediate: true },
);

function gatherPathFragments(): string[] {
  const out: string[] = [];
  for (const r of inputRows.value) {
    if (r.right.trim()) out.push(r.right.trim());
  }
  for (const r of outputRows.value) {
    if (r.right.trim()) out.push(r.right.trim());
  }
  return out;
}

const pathOptions = computed(() => [
  ...collectContextPathSuggestions(store.doc, gatherPathFragments()),
]);

function inputRowHasError(i: number): boolean {
  const prefix = `入参 第 ${i + 1} 行`;
  return errors.value.some((m) => m.startsWith(prefix));
}

function outputRowHasError(i: number): boolean {
  const prefix = `出参 第 ${i + 1} 行`;
  return errors.value.some((m) => m.startsWith(prefix));
}

function buildBoundary(): { boundary: Boundary; errors: string[] } {
  const errs: string[] = [];
  const inputs: Record<string, string> = {};
  const outputs: Record<string, string> = {};
  const seenIn = new Set<string>();
  const seenOut = new Set<string>();

  inputRows.value.forEach((r, idx) => {
    const p = r.right.trim();
    const v = r.left.trim();
    if (!p && !v) return;
    const line = `入参 第 ${idx + 1} 行`;
    const msg = validateBoundaryInputMapping(p, v);
    if (msg) errs.push(`${line}：${msg}`);
    if (p && v) {
      if (seenIn.has(p)) errs.push(`${line}：路径重复`);
      seenIn.add(p);
      inputs[p] = v;
    }
  });

  outputRows.value.forEach((r, idx) => {
    const p = r.right.trim();
    const f = r.left.trim();
    if (!p && !f) return;
    const line = `出参 第 ${idx + 1} 行`;
    const msg = validateBoundaryOutputMapping(f, p);
    if (msg) errs.push(`${line}：${msg}`);
    if (p && f) {
      if (seenOut.has(f)) errs.push(`${line}：字段重复`);
      seenOut.add(f);
      outputs[f] = p;
    }
  });

  return { boundary: { inputs, outputs }, errors: errs };
}

function tryEmit() {
  const { boundary, errors: e } = buildBoundary();
  errors.value = e;
  if (e.length > 0) return;
  const nextStable = stableBoundaryJson(boundary);
  /** 边界语义未变时不 emit，避免父级 watch 用「单行空表」重建，把多行空占位冲掉（表现为点 + 无反应）。 */
  if (nextStable === lastEmittedStable.value) return;
  lastEmittedStable.value = nextStable;
  emit("update:modelValue", boundary);
}

function onRowInput() {
  tryEmit();
}

/** 在当前行下方插入空行（不合并空行，避免仅多出一行占位时被立刻折回成一行）。 */
function addInputRowBelow(i: number) {
  inputRows.value.splice(i + 1, 0, { left: "", right: "" });
  tryEmit();
}

function addOutputRowBelow(i: number) {
  outputRows.value.splice(i + 1, 0, { left: "", right: "" });
  tryEmit();
}

function removeInputRow(i: number) {
  if (inputRows.value.length <= 1) return;
  inputRows.value.splice(i, 1);
  collapseDuplicateTrailingEmpty("in");
  if (inputRows.value.length === 0) {
    inputRows.value.push({ left: "", right: "" });
  }
  tryEmit();
}

function removeOutputRow(i: number) {
  if (outputRows.value.length <= 1) return;
  outputRows.value.splice(i, 1);
  collapseDuplicateTrailingEmpty("out");
  if (outputRows.value.length === 0) {
    outputRows.value.push({ left: "", right: "" });
  }
  tryEmit();
}

const countBrief = computed(() => {
  const { boundary } = buildBoundary();
  const nin = Object.keys(boundary.inputs).length;
  const nout = Object.keys(boundary.outputs).length;
  if (nin === 0 && nout === 0) return "";
  return `${nin} 条入参 · ${nout} 条出参`;
});
</script>

<style scoped>
.bmap {
  display: flex;
  flex-direction: column;
  gap: 4px;
  container-type: inline-size;
  container-name: bmap;
}

.bmap-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

@container bmap (min-width: 480px) {
  .bmap-grid {
    grid-template-columns: 1fr 1fr;
    gap: 8px 12px;
    align-items: start;
  }
}

.bmap-pane {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-width: 0;
  padding-left: 2px;
  border-left: 3px solid transparent;
}

.bmap-sheet {
  width: 100%;
  min-width: 0;
  border: none;
  background: transparent;
  padding: 0;
}

.bmap-pane--in {
  border-left-color: color-mix(in srgb, var(--accent) 45%, #cbd5e1);
}

.bmap-pane--out {
  border-left-color: color-mix(in srgb, #059669 40%, #cbd5e1);
}

.bmap-cols {
  display: grid;
  /* 路径列显著加宽：索引与箭头收窄，行内图标列 */
  grid-template-columns: 16px minmax(56px, 0.85fr) 14px minmax(0, 2.35fr) 52px;
  align-items: center;
  column-gap: 4px;
}

.bmap-head {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  letter-spacing: 0.02em;
  padding: 0 0 3px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 2px;
}

.bmap-col-idx {
  width: 16px;
}

.bmap-col-flow {
  width: 14px;
}

.bmap-col-act {
  width: 52px;
  display: inline-flex;
  justify-content: flex-end;
  align-items: center;
  gap: 1px;
  flex-shrink: 0;
}

.bmap-rows {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bmap-row {
  padding: 1px 0;
  border-radius: 4px;
  transition: background 0.1s ease;
}

.bmap-row:hover:not(.bmap-row--draft) {
  background: color-mix(in srgb, var(--accent-soft) 18%, transparent);
}

.bmap-row--draft:hover {
  background: color-mix(in srgb, var(--border) 28%, transparent);
}

.bmap-row--err {
  background: color-mix(in srgb, #fecaca 22%, #fffafa) !important;
}

.bmap-row--err .bmap-inp {
  border-color: color-mix(in srgb, #f87171 50%, var(--border));
}

.bmap-idx {
  font-size: 9px;
  font-weight: 600;
  color: #94a3b8;
  text-align: right;
  padding-right: 1px;
  user-select: none;
}

.bmap-flow {
  font-size: 10px;
  font-weight: 700;
  color: #94a3b8;
  user-select: none;
  text-align: center;
}

.bmap-inp {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 5px 8px;
  font-size: 12px;
  line-height: 1.35;
  outline: none;
  background: #fff;
  color: var(--text);
  min-width: 0;
}

.bmap-inp.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
  font-size: 11.5px;
}

.bmap-inp:focus {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}

.bmap-ibtn {
  box-sizing: border-box;
  width: 24px;
  height: 24px;
  margin: 0;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition:
    color 0.12s ease,
    background 0.12s ease,
    border-color 0.12s ease;
}

.bmap-ibtn:hover {
  color: var(--accent);
  background: color-mix(in srgb, var(--accent-soft) 35%, #fff);
  border-color: color-mix(in srgb, var(--accent) 22%, var(--border));
}

.bmap-ibtn:active {
  color: color-mix(in srgb, var(--accent) 80%, #0f172a);
}

.bmap-ibtn--danger:hover {
  color: #b91c1c;
  background: #fef2f2;
  border-color: #fecaca;
}

.bmap-ibtn--danger:active {
  color: #991b1b;
}

.bmap-ico {
  display: block;
  width: 14px;
  height: 14px;
}

.bmap-err {
  font-size: 11px;
  line-height: 1.45;
  color: #991b1b;
  margin-top: 2px;
  padding: 4px 0 0;
}

.bmap-err-list {
  margin: 0;
  padding-left: 1.15em;
}

.bmap-err-list li {
  margin: 2px 0;
}

.bmap-meta {
  font-size: 10px;
  color: var(--muted);
  padding: 1px 0 0;
}
</style>
