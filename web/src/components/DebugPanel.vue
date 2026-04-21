<template>
  <section class="card">
    <div class="head">
      <div>
        <div class="h">节点调试</div>
        <div class="d">
          每个节点拥有独立、可完全自定义的调试上下文；顶层 key 会直接绑定为 Starlark 全局变量
          （不走边界映射）。上下文仅存在于前端，不写回流程定义。
        </div>
      </div>
      <button type="button" class="btn" :disabled="pending" @click="run">
        {{ pending ? "请求中…" : "发送调试" }}
      </button>
    </div>

    <div class="lbl row">
      <span>调试上下文（JSON）</span>
      <span class="actions">
        <button type="button" class="mini" @click="resetFromInitialContext">
          重置为 initial_context
        </button>
        <button type="button" class="mini" @click="clearCtx">清空</button>
      </span>
    </div>
    <textarea
      v-model="ctxText"
      class="area mono"
      :class="{ invalid: !ctxValid }"
      rows="8"
      spellcheck="false"
      placeholder="{}"
    />
    <div class="ctx-hint" :class="{ err: !ctxValid }">
      {{ ctxValid ? ctxHint : "JSON 无法解析，调试时会被视为空对象。" }}
    </div>

    <div class="lbl row">
      <span>响应</span>
      <span class="hint">{{ hint }}</span>
    </div>
    <pre class="out mono">{{ responseText }}</pre>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useFlowStudioStore } from "@/stores/flowStudio";
import type { TaskNode } from "@/types/flow";

const props = defineProps<{
  path: number[];
}>();

const store = useFlowStudioStore();
const ctxText = ref("{}");
const responseText = ref("// 等待调试输出");
const pending = ref(false);
const hint = ref("");

const task = computed(() => {
  // 使用读穿视图：优先取未保存的草稿，让脚本 / 边界的即时修改能直接进入调试，
  // 避免必须先保存才能生效。
  const n = store.viewNode(props.path);
  return n && n.type === "task" ? (n as TaskNode) : null;
});

const parsedCtx = computed<{ ok: boolean; value: Record<string, unknown> }>(() => {
  const raw = ctxText.value.trim();
  if (!raw) return { ok: true, value: {} };
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return { ok: true, value: parsed as Record<string, unknown> };
    }
    return { ok: false, value: {} };
  } catch {
    return { ok: false, value: {} };
  }
});

const ctxValid = computed(() => parsedCtx.value.ok);

const ctxHint = computed(() => {
  const keys = Object.keys(parsedCtx.value.value);
  if (keys.length === 0) return "无顶层变量（等价于空环境）。";
  return `顶层变量：${keys.join(", ")}`;
});

function defaultCtxText(): string {
  return JSON.stringify(store.doc.initial_context ?? {}, null, 2);
}

/** 切换到不同节点时，从 store 读取该节点独立的调试上下文；没有则首次用 initial_context 作为种子。 */
watch(
  () => props.path.join("/"),
  () => {
    const saved = store.getDebugContextText(props.path);
    ctxText.value = saved !== undefined ? saved : defaultCtxText();
  },
  { immediate: true },
);

/** 用户每次编辑都回写到当前节点的独立调试上下文。 */
watch(ctxText, (v) => {
  store.setDebugContextText(props.path, v);
});

function resetFromInitialContext() {
  ctxText.value = defaultCtxText();
}

function clearCtx() {
  ctxText.value = "{}";
}

async function run() {
  if (!task.value) {
    hint.value = "仅 Task 节点可调试";
    return;
  }

  pending.value = true;
  hint.value = "";
  responseText.value = "";

  const body = {
    script: task.value.script,
    initial_context: parsedCtx.value.ok ? parsedCtx.value.value : {},
  };

  try {
    const res = await fetch("/api/debug/node", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    if (!res.ok) {
      responseText.value = text || `HTTP ${res.status}`;
      hint.value = "后端返回错误";
      return;
    }
    try {
      const parsed = JSON.parse(text) as { ok?: boolean; result?: unknown; error?: string };
      responseText.value = JSON.stringify(parsed, null, 2);
      hint.value = parsed.ok === false ? "Starlark 执行失败" : "后端执行成功";
    } catch {
      responseText.value = text;
      hint.value = "后端执行成功";
    }
  } catch {
    responseText.value = JSON.stringify(
      {
        note: "未检测到后端 API，以下为请求体预览（可对接 flow_engine 调试端点）",
        request: body,
      },
      null,
      2,
    );
    hint.value = "离线模式";
  } finally {
    pending.value = false;
  }
}
</script>

<style scoped>
.card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  padding: 12px;
  box-shadow: var(--shadow);
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.h {
  font-weight: 700;
  font-size: 13px;
}

.d {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
  line-height: 1.35;
}

.btn {
  border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
  background: var(--accent);
  color: #fff;
  border-radius: 10px;
  padding: 8px 12px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.lbl {
  display: block;
  font-size: 11px;
  color: var(--muted);
  margin: 8px 0 6px;
}

.lbl.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.hint {
  font-size: 11px;
  color: var(--muted);
}

.actions {
  display: inline-flex;
  gap: 6px;
}

.mini {
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
  border-radius: 8px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
}

.mini:hover {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
}

.ctx-hint {
  font-size: 11px;
  color: var(--muted);
  margin: 4px 2px 0;
}

.ctx-hint.err {
  color: #b91c1c;
}

.area.invalid {
  border-color: #fca5a5;
  background: #fff7f7;
}

.area {
  width: 100%;
  border-radius: 10px;
  border: 1px solid var(--border);
  padding: 10px;
  font-size: 12px;
  resize: vertical;
  outline: none;
  background: #fbfdff;
}

.area:focus {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.out {
  margin: 0;
  padding: 10px;
  border-radius: 10px;
  border: 1px dashed var(--border);
  background: #0b1220;
  color: #e2e8f0;
  min-height: 120px;
  overflow: auto;
  font-size: 11px;
  line-height: 1.45;
}
</style>
