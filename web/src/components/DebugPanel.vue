<template>
  <section class="card">
    <div class="head">
      <div class="head-title">
        <span class="h">节点调试</span>
        <InfoTip
          wide
          text="每个节点拥有独立的调试上下文。顶层 key 会直接绑定为 Starlark 全局变量（不走边界映射），仅前端保存，不写回流程定义。"
        />
      </div>
      <button type="button" class="btn" :disabled="pending" @click="run">
        {{ pending ? "请求中…" : "▶ 调试" }}
      </button>
    </div>

    <div class="lbl row">
      <span class="lbl-row">调试上下文 (JSON)</span>
      <span class="actions">
        <select v-model="profileText" class="mini sel-mini mono" title="调试使用的字典 profile">
          <option v-for="p in profileOptions" :key="p" :value="p">{{ p }}</option>
        </select>
        <button type="button" class="mini" @click="resetFromInitialContext">重置</button>
        <button type="button" class="mini" @click="clearCtx">清空</button>
      </span>
    </div>
    <textarea
      v-model="ctxText"
      class="area mono"
      :class="{ invalid: !ctxValid }"
      rows="4"
      spellcheck="false"
      placeholder="{}"
    />
    <div class="ctx-hint" :class="{ err: !ctxValid }">
      {{ ctxValid ? ctxHint : "JSON 无法解析，调试时会被视为空对象" }}
    </div>

    <div class="lbl row">
      <span class="lbl-row">响应</span>
      <span class="hint">{{ hint }}</span>
    </div>
    <pre class="out mono">{{ responseText }}</pre>

    <div v-if="logs.length" class="lbl row">
      <span class="lbl-row">
        运行日志
        <InfoTip text="脚本中调用 log / log_info / log_warn / log_error 产生。" />
      </span>
      <span class="hint">{{ logs.length }} 条</span>
    </div>
    <ul v-if="logs.length" class="logs mono">
      <li v-for="(entry, i) in logs" :key="i" class="log-row" :class="`lvl-${entry.level}`">
        <span class="log-ts">+{{ entry.ts_ms }}ms</span>
        <span class="log-lvl">{{ entry.level }}</span>
        <span class="log-src" :title="`来源: ${entry.source}`">{{ entry.source }}</span>
        <span class="log-msg">{{ entry.message }}</span>
        <span v-if="entry.truncated" class="log-trunc" title="达到日志上限，后续条目被丢弃">…</span>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from "vue";
import { useFlowStudioStore } from "@/stores/flowStudio";
import type { LogEntry } from "@/api/flows";
import type { TaskNode } from "@/types/flow";
import InfoTip from "./InfoTip.vue";
import { fetchProfileConfig } from "@/api/profiles";

const props = defineProps<{
  path: number[];
}>();

const store = useFlowStudioStore();
const ctxText = ref("{}");
const responseText = ref("// 等待调试输出");
const pending = ref(false);
const hint = ref("");
const logs = ref<LogEntry[]>([]);
const profileOptions = ref<string[]>(["default"]);
const profileText = ref("default");
const defaultProfile = ref("default");

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
  logs.value = [];

  const body = {
    script: task.value.script,
    initial_context: parsedCtx.value.ok ? parsedCtx.value.value : {},
    profile: profileText.value,
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
      const parsed = JSON.parse(text) as {
        ok?: boolean;
        result?: unknown;
        error?: string;
        logs?: LogEntry[];
      };
      // Separate the log stream from the result payload for display:
      // the "响应" block stays focused on the script's return value
      // while logs get their own structured row list below.
      logs.value = Array.isArray(parsed.logs) ? parsed.logs : [];
      const { logs: _logs, ...rest } = parsed;
      void _logs;
      responseText.value = JSON.stringify(rest, null, 2);
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

onMounted(async () => {
  try {
    const res = await fetchProfileConfig();
    defaultProfile.value = res.default_profile || "default";
    if (Array.isArray(res.profiles) && res.profiles.length) profileOptions.value = [...res.profiles];
    profileText.value = defaultProfile.value;
    if (!profileOptions.value.includes(profileText.value)) profileOptions.value.push(profileText.value);
  } catch {
    // keep defaults
  }
});
</script>

<style scoped>
.card {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  padding: 10px 14px 12px;
  box-shadow: var(--shadow);
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}

.head-title {
  display: inline-flex;
  align-items: center;
}

.h {
  font-weight: 700;
  font-size: 12px;
  color: var(--text);
  letter-spacing: 0.01em;
}

.btn {
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #fff;
  border-radius: 7px;
  padding: 5px 12px;
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s ease;
}

.btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 88%, #000);
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.lbl {
  display: block;
  font-size: 11px;
  color: var(--muted);
  margin: 8px 0 4px;
}

.lbl.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.lbl .lbl-row {
  font-weight: 500;
  color: #475569;
  font-size: 11.5px;
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
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.mini:hover {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
}

.sel-mini {
  max-width: 150px;
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
  border-radius: 8px;
  border: 1px solid var(--border);
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

.out {
  margin: 0;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: #0f172a;
  color: #e2e8f0;
  min-height: 72px;
  max-height: 200px;
  overflow: auto;
  font-size: 11px;
  line-height: 1.5;
}

.logs {
  list-style: none;
  padding: 0;
  margin: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  max-height: 180px;
  overflow: auto;
  background: #fff;
}

.log-row {
  display: grid;
  grid-template-columns: 62px 46px 92px 1fr auto;
  gap: 8px;
  align-items: baseline;
  padding: 4px 10px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
  font-size: 11px;
  line-height: 1.45;
}

.log-row:last-child {
  border-bottom: none;
}

.log-ts {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.log-lvl {
  text-transform: uppercase;
  font-weight: 700;
  font-size: 10px;
  letter-spacing: 0.04em;
  border-radius: 4px;
  padding: 1px 6px;
  background: #e2e8f0;
  color: #475569;
  text-align: center;
}

.log-row.lvl-info .log-lvl {
  background: color-mix(in srgb, #3b82f6 15%, transparent);
  color: #1d4ed8;
}

.log-row.lvl-warn .log-lvl {
  background: color-mix(in srgb, #f59e0b 20%, transparent);
  color: #92400e;
}

.log-row.lvl-error .log-lvl {
  background: color-mix(in srgb, #ef4444 18%, transparent);
  color: #b91c1c;
}

.log-row.lvl-debug .log-lvl {
  background: color-mix(in srgb, #94a3b8 20%, transparent);
  color: #475569;
}

.log-src {
  color: var(--muted);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-msg {
  color: var(--text, #0f172a);
  white-space: pre-wrap;
  word-break: break-word;
}

.log-trunc {
  color: #b45309;
  font-weight: 700;
}
</style>
