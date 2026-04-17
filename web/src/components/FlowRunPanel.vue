<template>
  <div class="run-panel" :class="{ open: visible }">
    <header class="bar">
      <div class="title">
        <span>流程运行结果</span>
        <span v-if="response" class="badge" :class="stateClass(response.state)">{{ response.state }}</span>
        <span v-if="response" class="muted">· {{ response.elapsed_ms }}ms</span>
      </div>
      <div class="actions">
        <label class="opt">
          <input v-model="merge" type="checkbox" /> 合并 initial_context
        </label>
        <label class="opt">
          超时(s)
          <input v-model.number="timeoutSec" type="number" min="1" max="600" step="1" />
        </label>
        <button class="btn primary" :disabled="pending || !flowId" @click="run">
          {{ pending ? "运行中…" : "运行" }}
        </button>
        <button class="btn ghost" @click="$emit('close')">关闭</button>
      </div>
    </header>

    <div class="grid">
      <section class="col">
        <div class="lbl">initial_context 覆盖（JSON，可留空）</div>
        <textarea v-model="ctxText" class="area mono" rows="10" spellcheck="false" />
        <p v-if="error" class="err">{{ error }}</p>
      </section>
      <section class="col">
        <div class="lbl">节点状态</div>
        <div v-if="!response" class="hint">未运行</div>
        <ul v-else class="nodes">
          <li v-for="(st, nid) in response.node_state" :key="nid" :class="['nodeRow', statusClass(st)]">
            <span class="dot" />
            <span class="nid mono">{{ nid }}</span>
            <span class="st">{{ st }}</span>
          </li>
        </ul>
      </section>
      <section class="col">
        <div class="lbl">全局上下文（global_ns）</div>
        <pre class="out mono">{{ globalsText }}</pre>
        <p v-if="response?.message" class="msg">{{ response.message }}</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { runFlow } from "@/api/flows";
import type { RunFlowResponse } from "@/api/flows";

const props = defineProps<{
  flowId: string | null;
  visible: boolean;
  initialContext: Record<string, unknown> | null | undefined;
}>();
defineEmits<{ (e: "close"): void }>();

const ctxText = ref("");
const merge = ref(true);
const timeoutSec = ref(30);
const pending = ref(false);
const response = ref<RunFlowResponse | null>(null);
const error = ref<string | null>(null);

watch(
  () => props.initialContext,
  (v) => {
    ctxText.value = v ? JSON.stringify(v, null, 2) : "";
  },
  { immediate: true },
);

watch(
  () => props.flowId,
  () => {
    response.value = null;
    error.value = null;
  },
);

const globalsText = computed(() =>
  response.value ? JSON.stringify(response.value.global_ns, null, 2) : "// 未运行",
);

function stateClass(state: string): string {
  if (state === "COMPLETED") return "ok";
  if (state === "FAILED") return "bad";
  if (state === "TERMINATED") return "warn";
  return "info";
}

function statusClass(st: string): string {
  if (st === "SUCCESS") return "ok";
  if (st === "FAILED") return "bad";
  if (st === "SKIPPED") return "skipped";
  if (st === "RUNNING" || st === "DISPATCHED" || st === "STAGING") return "running";
  return "info";
}

async function run() {
  if (!props.flowId) return;
  error.value = null;
  let override: Record<string, unknown> | null = null;
  const raw = ctxText.value.trim();
  if (raw) {
    try {
      const parsed: unknown = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("initial_context 必须是一个 JSON 对象");
      }
      override = parsed as Record<string, unknown>;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return;
    }
  }
  pending.value = true;
  try {
    response.value = await runFlow(props.flowId, {
      initial_context: override,
      merge: merge.value,
      timeout_sec: timeoutSec.value,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    pending.value = false;
  }
}
</script>

<style scoped>
.run-panel {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--surface);
  border-top: 1px solid var(--border);
  box-shadow: 0 -12px 28px rgba(15, 23, 42, 0.08);
  transform: translateY(100%);
  transition: transform 0.22s ease;
  max-height: 62vh;
  display: flex;
  flex-direction: column;
  z-index: 40;
}

.run-panel.open {
  transform: translateY(0);
}

.bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 13px;
}

.badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
}

.badge.ok {
  background: color-mix(in srgb, #10b981 14%, transparent);
  color: #047857;
  border-color: color-mix(in srgb, #10b981 35%, transparent);
}

.badge.bad {
  background: color-mix(in srgb, #ef4444 14%, transparent);
  color: #b91c1c;
  border-color: color-mix(in srgb, #ef4444 35%, transparent);
}

.badge.warn {
  background: color-mix(in srgb, #f59e0b 18%, transparent);
  color: #92400e;
  border-color: color-mix(in srgb, #f59e0b 35%, transparent);
}

.muted {
  color: var(--muted);
  font-weight: 400;
  font-size: 11px;
}

.actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.opt {
  font-size: 11px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 4px;
}

.opt input[type="number"] {
  width: 64px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 3px 6px;
  font-size: 11px;
}

.btn {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}

.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
}

.btn.primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.4fr);
  gap: 12px;
  padding: 12px;
  overflow: hidden;
}

.col {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.lbl {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 6px;
}

.hint {
  font-size: 12px;
  color: var(--muted);
  padding: 8px;
}

.area,
.out {
  flex: 1;
  min-height: 0;
  border-radius: 10px;
  font-size: 11px;
  line-height: 1.45;
}

.area {
  padding: 10px;
  border: 1px solid var(--border);
  background: #fbfdff;
  resize: none;
  outline: none;
}

.area:focus {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.out {
  margin: 0;
  padding: 10px;
  border: 1px dashed var(--border);
  background: #0b1220;
  color: #e2e8f0;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.err {
  color: #b91c1c;
  font-size: 11px;
  margin: 6px 0 0;
}

.msg {
  font-size: 11px;
  color: var(--muted);
  margin: 6px 0 0;
}

.nodes {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
}

.nodeRow {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}

.nodeRow:last-child {
  border-bottom: none;
}

.nid {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.st {
  font-size: 11px;
  color: var(--muted);
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #cbd5e1;
}

.nodeRow.ok .dot {
  background: #10b981;
}

.nodeRow.bad .dot {
  background: #ef4444;
}

.nodeRow.skipped .dot {
  background: #94a3b8;
}

.nodeRow.running .dot {
  background: #3b82f6;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

@media (max-width: 960px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
