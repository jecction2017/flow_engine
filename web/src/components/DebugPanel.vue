<template>
  <section class="card">
    <div class="head">
      <div>
        <div class="h">节点调试</div>
        <div class="d">构造上下文 JSON，可选连接后端 `/api/debug/node` 执行 Starlark</div>
      </div>
      <button type="button" class="btn" :disabled="pending" @click="run">
        {{ pending ? "请求中…" : "发送调试" }}
      </button>
    </div>

    <label class="lbl">调试上下文（JSON）</label>
    <textarea v-model="ctxText" class="area mono" rows="7" spellcheck="false" />

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
  const n = store.getNode(props.path);
  return n && n.type === "task" ? (n as TaskNode) : null;
});

watch(
  () => store.doc.initial_context,
  (v) => {
    ctxText.value = JSON.stringify(v ?? {}, null, 2);
  },
  { immediate: true },
);

async function run() {
  if (!task.value) {
    hint.value = "仅 Task 节点可调试";
    return;
  }
  let payload: unknown;
  try {
    payload = JSON.parse(ctxText.value || "{}");
  } catch {
    hint.value = "上下文 JSON 无效";
    return;
  }

  pending.value = true;
  hint.value = "";
  responseText.value = "";

  const body = {
    script: task.value.script,
    boundary_inputs: task.value.boundary.inputs,
    initial_context: payload,
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
      hint.value = "后端返回错误（可仅使用本地校验）";
      return;
    }
    responseText.value = text;
    hint.value = "后端执行成功";
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
