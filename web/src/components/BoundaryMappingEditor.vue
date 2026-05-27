<template>
  <div class="bmap">
    <div class="bmap-grid">
      <section
        class="bmap-pane bmap-pane--in"
        aria-label="从上下文映射到任务变量（inputs）"
      >
        <div class="bmap-sheet">
            <div class="bmap-cols bmap-head" aria-hidden="true">
              <span class="bmap-col-idx" />
              <span>注入变量</span>
              <span class="bmap-col-flow" />
              <span class="bmap-path-hd">上下文路径</span>
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
                'bmap-row--lift': pathSuggestOpenFor('in', i),
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
              <div class="bmap-path-line">
                <div class="bmap-path-wrap">
                  <input
                    v-model="row.right"
                    class="bmap-inp mono bmap-path-inp"
                    spellcheck="false"
                    autocomplete="off"
                    placeholder="$.global…"
                    :aria-invalid="inputRowHasError(i)"
                    aria-label="入参上下文路径"
                    :aria-expanded="pathSuggestOpenFor('in', i)"
                    :aria-controls="pathSuggestOpenFor('in', i) ? pathSuggestListId('in', i) : undefined"
                    aria-autocomplete="list"
                    @focus="onPathFocus('in', i)"
                    @blur="onPathBlur"
                    @keydown.escape.prevent="closePathSuggest"
                    @input="onRowInput"
                  />
                  <div
                    v-if="pathSuggestOpenFor('in', i)"
                    :id="pathSuggestListId('in', i)"
                    class="bmap-suggest"
                    role="listbox"
                    aria-label="路径补全建议"
                    @mousedown.prevent
                  >
                    <div class="bmap-suggest-cap">输入时可点选填入；仍支持完全手写路径</div>
                    <button
                      v-for="opt in activePathSuggestions"
                      :key="opt"
                      type="button"
                      class="bmap-suggest-item"
                      role="option"
                      @mousedown.prevent="applyPathSuggestion('in', i, opt)"
                    >
                      {{ opt }}
                    </button>
                  </div>
                </div>
                <div class="bmap-col-act">
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
                  <span v-else class="bmap-act-spacer" aria-hidden="true" />
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
                </div>
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
              <span class="bmap-path-hd">上下文路径</span>
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
                'bmap-row--lift': pathSuggestOpenFor('out', i),
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
              <div class="bmap-path-line">
                <div class="bmap-path-wrap">
                  <input
                    v-model="row.right"
                    class="bmap-inp mono bmap-path-inp"
                    spellcheck="false"
                    autocomplete="off"
                    placeholder="$.global…"
                    :aria-invalid="outputRowHasError(i)"
                    aria-label="出参上下文路径"
                    :aria-expanded="pathSuggestOpenFor('out', i)"
                    :aria-controls="pathSuggestOpenFor('out', i) ? pathSuggestListId('out', i) : undefined"
                    aria-autocomplete="list"
                    @focus="onPathFocus('out', i)"
                    @blur="onPathBlur"
                    @keydown.escape.prevent="closePathSuggest"
                    @input="onRowInput"
                  />
                  <div
                    v-if="pathSuggestOpenFor('out', i)"
                    :id="pathSuggestListId('out', i)"
                    class="bmap-suggest"
                    role="listbox"
                    aria-label="路径补全建议"
                    @mousedown.prevent
                  >
                    <div class="bmap-suggest-cap">输入时可点选填入；仍支持完全手写路径</div>
                    <button
                      v-for="opt in activePathSuggestions"
                      :key="opt"
                      type="button"
                      class="bmap-suggest-item"
                      role="option"
                      @mousedown.prevent="applyPathSuggestion('out', i, opt)"
                    >
                      {{ opt }}
                    </button>
                  </div>
                </div>
                <div class="bmap-col-act">
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
                  <span v-else class="bmap-act-spacer" aria-hidden="true" />
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
                </div>
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

const syncSlug = computed(() => props.syncKey.replace(/[^\w-]/g, "_"));

type PathSuggestPane = "in" | "out";
const pathSuggestTarget = ref<{ pane: PathSuggestPane; index: number } | null>(null);
let pathSuggestBlurTimer: ReturnType<typeof setTimeout> | null = null;

function clearPathSuggestBlurTimer() {
  if (pathSuggestBlurTimer !== null) {
    clearTimeout(pathSuggestBlurTimer);
    pathSuggestBlurTimer = null;
  }
}

function pathSuggestListId(pane: PathSuggestPane, rowIndex: number): string {
  return `fe-bmap-sug-${pane}-${syncSlug.value}-${rowIndex}`;
}

function pathSuggestOpenFor(pane: PathSuggestPane, rowIndex: number): boolean {
  const t = pathSuggestTarget.value;
  return !!t && t.pane === pane && t.index === rowIndex && activePathSuggestions.value.length > 0;
}

function onPathFocus(pane: PathSuggestPane, index: number) {
  clearPathSuggestBlurTimer();
  pathSuggestTarget.value = { pane, index };
}

function onPathBlur() {
  clearPathSuggestBlurTimer();
  pathSuggestBlurTimer = setTimeout(() => {
    pathSuggestTarget.value = null;
    pathSuggestBlurTimer = null;
  }, 150);
}

function closePathSuggest() {
  clearPathSuggestBlurTimer();
  pathSuggestTarget.value = null;
}

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
      pathSuggestTarget.value = null;
      clearPathSuggestBlurTimer();
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

const activePathSuggestions = computed((): string[] => {
  const t = pathSuggestTarget.value;
  if (!t) return [];
  const rows = t.pane === "in" ? inputRows.value : outputRows.value;
  const row = rows[t.index];
  if (!row) return [];
  const q = row.right.trim().toLowerCase();
  const opts = pathOptions.value;
  if (opts.length === 0) return [];
  if (!q) return opts.slice(0, 16);
  const picked: { p: string; rank: number }[] = [];
  for (const p of opts) {
    const pl = p.toLowerCase();
    if (!pl.includes(q)) continue;
    const rank = pl.startsWith(q) ? 0 : 1;
    picked.push({ p, rank });
  }
  picked.sort((a, b) => a.rank - b.rank || a.p.localeCompare(b.p));
  return picked.slice(0, 20).map((x) => x.p);
});

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

function applyPathSuggestion(pane: PathSuggestPane, index: number, value: string) {
  clearPathSuggestBlurTimer();
  const rows = pane === "in" ? inputRows : outputRows;
  const row = rows.value[index];
  if (!row) return;
  row.right = value;
  pathSuggestTarget.value = null;
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
  width: 100%;
  min-width: 0;
}

.bmap-grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
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
  grid-template-columns: 22px minmax(9.5rem, 1fr) 16px minmax(0, 2.4fr);
  align-items: center;
  column-gap: 8px;
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
  width: 22px;
}

.bmap-col-flow {
  width: 16px;
}

.bmap-path-hd {
  min-width: 0;
}

.bmap-path-line {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  min-width: 0;
}

.bmap-col-act {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  flex-shrink: 0;
  padding-top: 1px;
}

.bmap-act-spacer {
  box-sizing: border-box;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  pointer-events: none;
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

.bmap-path-wrap {
  position: relative;
  flex: 1;
  min-width: 0;
}

.bmap-row--lift {
  position: relative;
  z-index: 8;
}

.bmap-suggest {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 3px);
  z-index: 20;
  max-height: 220px;
  overflow-y: auto;
  padding: 4px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--surface, #fff);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
  font-size: 11.5px;
}

.bmap-suggest-cap {
  font-size: 10px;
  font-weight: 500;
  color: var(--muted);
  padding: 2px 6px 6px;
  line-height: 1.35;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
  margin-bottom: 2px;
}

.bmap-suggest-item {
  display: block;
  width: 100%;
  box-sizing: border-box;
  text-align: left;
  border: 0;
  border-radius: 5px;
  margin: 0;
  padding: 6px 8px;
  font: inherit;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
  font-size: 11.5px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
}

.bmap-suggest-item:hover {
  background: color-mix(in srgb, var(--accent-soft) 48%, #fff);
}

.bmap-suggest-item:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--accent) 45%, transparent);
  outline-offset: 0;
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
