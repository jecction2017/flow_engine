<template>
  <section :class="embedded ? 'debug-embedded' : 'card'">
    <div v-if="!hideToolbar" class="head">
      <div class="head-title">
        <span class="h">节点调试</span>
      </div>
      <button type="button" class="btn" :disabled="pending" @click="run">
        {{ pending ? "请求中…" : "▶ 调试" }}
      </button>
    </div>

    <div class="debug-settings">
      <div class="settings-panel">
        <header class="settings-panel-hd">
          <div class="settings-panel-titles">
            <span class="settings-panel-title">调试设置</span>
            <span class="settings-panel-sub">上下文、Profile 与抑制规则仅作用于本次请求，不写回流程 YAML。</span>
          </div>
        </header>

        <div class="settings-stack">
          <div class="ctx-json-block">
            <div class="ctx-json-head">
              <span class="field-line-lbl">
                调试上下文 (JSON)
                <InfoTip
                  wide
                  text="每个节点独立保存。JSON 最外层的字段名会作为 Starlark 全局变量直接注入脚本（不经过节点边界映射），仅保存在浏览器本地，不会写回流程 YAML。"
                />
              </span>
              <div class="ctx-json-actions">
                <button type="button" class="mini mini-strong" @click="resetFromInitialContext">重置</button>
                <button type="button" class="mini mini-strong" @click="clearCtx">清空</button>
              </div>
            </div>
            <textarea
              v-model="ctxText"
              class="area mono area-ctx"
              :class="{ invalid: !ctxValid }"
              rows="9"
              spellcheck="false"
              placeholder="{}"
            />
            <div v-if="ctxValid" class="ctx-hint-line">
              <template v-if="ctxInjectKeys.length">
                <span class="ctx-hint-text">注入变量</span>
                <template v-for="(k, i) in ctxInjectKeys" :key="k">
                  <span class="ctx-hint-token mono">{{ k }}</span>
                  <span v-if="i < ctxInjectKeys.length - 1" class="ctx-hint-sep">、</span>
                </template>
                <span class="ctx-hint-text">可在脚本中按全局名直接读取。</span>
              </template>
              <template v-else>
                <span class="ctx-hint-text">注入变量</span>
                <span class="ctx-hint-text ctx-hint-weak">暂无（空对象表示无可注入名）。</span>
              </template>
            </div>
            <div v-else class="ctx-hint-line err">JSON 无法解析，调试时会被视为空对象。</div>
          </div>

          <div class="profile-block-standalone">
            <div class="field-line field-line--tight">
              <span class="field-line-lbl">
                调试 Profile
                <InfoTip text="本次请求使用的数据字典 profile，由服务端 profiles 配置决定；与流程属性里的默认 profile 可能不同。" />
              </span>
            </div>
            <div class="profile-select-shell">
              <select v-model="profileText" class="inp inp-profile mono">
                <option v-for="p in profileOptions" :key="p" :value="p">{{ p }}</option>
              </select>
            </div>
          </div>

          <details class="cap-details">
            <summary class="cap-summary">
              <span class="cap-summary-lbl">副作用函数抑制（仅本次请求）</span>
              <span class="cap-summary-tip" @click.stop>
                <InfoTip
                  wide
                  text="调试模式，默认抑制副作用函数（suppress），可在此配置规则：放行（allow）或重定向（redirect + redirect_params）；此配置规则仅随本次调试发送，并与节点已保存的抑制规则合并，不写回流程。"
                />
              </span>
            </summary>
            <CapabilityRulesEditor v-model="capabilityPolicy" />
          </details>
        </div>
      </div>
    </div>

    <div class="debug-results">
      <div class="results-head">
        <div class="results-head-main">
          <span class="results-title">调试结果</span>
          <InfoTip text="包含脚本返回值（响应体）与 Starlark 运行期日志；与上方调试设置相互独立。" />
        </div>
        <div class="result-status-wrap">
          <span class="result-status" :class="resultStatusClass">{{ resultStatusText }}</span>
        </div>
      </div>

      <div class="results-body">
        <div class="result-block">
          <div class="lbl row result-block-hd">
            <span class="lbl-row">响应</span>
          </div>
          <pre class="out mono">{{ responseText }}</pre>
        </div>

        <div class="result-block">
          <div class="lbl row result-block-hd">
            <span class="lbl-row">
              运行日志
              <InfoTip text="脚本中调用 log / log_info / log_warn / log_error 产生。" />
            </span>
            <span v-if="logs.length" class="hint">{{ logs.length }} 条</span>
            <span v-else class="hint muted">暂无</span>
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
          <div v-else class="logs-empty mono">执行成功后，日志会显示在此处。</div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from "vue";
import { useFlowStudioStore } from "@/stores/flowStudio";
import type { LogEntry } from "@/api/flows";
import type { CapabilityRule, TaskNode } from "@/types/flow";
import CapabilityRulesEditor from "./CapabilityRulesEditor.vue";
import InfoTip from "./InfoTip.vue";
import { fetchProfileConfig } from "@/api/profiles";

const props = withDefaults(
  defineProps<{
    path: number[];
    /** 抽屉内嵌：去掉外层卡片边框，由容器负责布局。 */
    embedded?: boolean;
    /** 隐藏顶部标题栏与主「调试」按钮（由外层工具栏触发 run）。 */
    hideToolbar?: boolean;
  }>(),
  { embedded: false, hideToolbar: false },
);

const store = useFlowStudioStore();
const ctxText = ref("{}");
const responseText = ref("// 等待调试输出");
const pending = ref(false);
/** 调试执行状态：用于结果区醒目展示，与旧版右侧小字 hint 分离。 */
type ResultPhase = "idle" | "pending" | "ok" | "http_err" | "starlark_err" | "offline" | "blocked";
const resultPhase = ref<ResultPhase>("idle");
const logs = ref<LogEntry[]>([]);
const profileOptions = ref<string[]>(["default"]);
const profileText = ref("default");
const defaultProfile = ref("default");
// 节点调试不再暴露 run_mode：服务端永远按 DEBUG 处理。
// capability_policy 只能"放宽"（ALLOW/REDIRECT），无法切到 production。
const capabilityPolicy = ref<CapabilityRule[]>([]);

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

const resultStatusText = computed(() => {
  switch (resultPhase.value) {
    case "idle":
      return "未执行";
    case "pending":
      return "执行中…";
    case "ok":
      return "成功";
    case "http_err":
      return "请求失败";
    case "starlark_err":
      return "脚本失败";
    case "offline":
      return "离线预览";
    case "blocked":
      return "无法调试";
    default:
      return "";
  }
});

const resultStatusClass = computed(() => ({
  "is-idle": resultPhase.value === "idle",
  "is-pending": resultPhase.value === "pending",
  "is-ok": resultPhase.value === "ok",
  "is-warn": resultPhase.value === "offline",
  "is-err":
    resultPhase.value === "http_err" ||
    resultPhase.value === "starlark_err" ||
    resultPhase.value === "blocked",
}));

/** JSON 顶层 key，用于「注入变量」提示区展示。 */
const ctxInjectKeys = computed(() => {
  if (!ctxValid.value) return [] as string[];
  return Object.keys(parsedCtx.value.value);
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
    resultPhase.value = "idle";
    responseText.value = "// 等待调试输出";
    logs.value = [];
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
    resultPhase.value = "blocked";
    responseText.value = "// 仅 Task 节点可调试";
    logs.value = [];
    return;
  }

  pending.value = true;
  resultPhase.value = "pending";
  responseText.value = "";
  logs.value = [];

  const body = {
    script: task.value.script,
    initial_context: parsedCtx.value.ok ? parsedCtx.value.value : {},
    profile: profileText.value,
    // 节点级 capability_overrides + 调试面板手动添加的策略；服务端在 DEBUG 系统默认
    // 之上叠加这两层（前者来自流程定义，后者来自调试者临时白名单）。
    capability_policy: [
      ...(task.value.capability_overrides ?? []),
      ...capabilityPolicy.value,
    ],
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
      resultPhase.value = "http_err";
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
      resultPhase.value = parsed.ok === false ? "starlark_err" : "ok";
    } catch {
      responseText.value = text;
      resultPhase.value = "ok";
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
    resultPhase.value = "offline";
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

defineExpose({ run, pending });
</script>

<style scoped>
.card {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 8px 10px 10px;
  box-shadow: var(--shadow);
}

.debug-embedded {
  padding: 0;
  background: transparent;
  border: none;
  box-shadow: none;
}

.debug-settings {
  padding-bottom: 0;
}

.settings-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  padding: 0;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.settings-panel-hd {
  padding: 7px 10px;
  background: color-mix(in srgb, var(--accent-soft, #e0e7ff) 10%, #fafafa);
}

.settings-panel-titles {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.settings-panel-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.02em;
}

.settings-panel-sub {
  font-size: 10.5px;
  line-height: 1.4;
  color: var(--muted);
}

.settings-stack {
  padding: 8px 10px 9px;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.field-line {
  margin: 0 0 5px;
}

.field-line--tight {
  margin-bottom: 4px;
}

.field-line-lbl {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  font-weight: 600;
  color: #334155;
  letter-spacing: 0.01em;
}

.ctx-json-block {
  display: flex;
  flex-direction: column;
  margin-bottom: 2px;
}

.ctx-json-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px 8px;
  margin-bottom: 5px;
}

.ctx-json-head .field-line-lbl {
  min-width: 0;
  flex: 1 1 auto;
}

.ctx-json-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.profile-block-standalone {
  margin-top: 8px;
  padding-top: 0;
}

@media (max-width: 520px) {
  .ctx-json-head {
    align-items: flex-start;
  }

  .ctx-json-actions {
    width: 100%;
    justify-content: flex-end;
  }
}

.profile-select-shell {
  border-radius: 7px;
  padding: 1px;
  background: color-mix(in srgb, var(--border) 88%, var(--accent) 12%);
  max-width: min(400px, 100%);
}

.inp-profile {
  width: 100%;
  margin: 0;
  border-radius: 6px;
  font-size: 11.5px;
  padding: 6px 8px;
  border: none;
  background: #fff;
  box-shadow: none;
}

.inp-profile:focus {
  outline: none;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 35%, transparent);
}

.area-ctx {
  width: 100%;
  margin-top: 0;
  min-height: 190px;
}

.mono {
  font-family: var(--mono, ui-monospace, monospace);
}

.ctx-hint-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 3px 5px;
  margin-top: 6px;
  padding: 0 1px;
  font-size: 10.5px;
  line-height: 1.5;
}

.ctx-hint-line.err {
  color: #b91c1c;
  font-weight: 500;
}

.ctx-hint-text {
  color: #64748b;
  font-size: 10.5px;
}

.ctx-hint-weak {
  color: #94a3b8;
}

.ctx-hint-token {
  display: inline-block;
  font-family: var(--mono, ui-monospace, monospace);
  font-size: 10.5px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--accent-soft, #e0e7ff) 35%, #f1f5f9);
  border: 1px solid color-mix(in srgb, var(--border) 55%, #94a3b8);
  color: #0f172a;
  line-height: 1.35;
  vertical-align: baseline;
}

.ctx-hint-sep {
  color: #64748b;
  font-weight: 500;
  user-select: none;
}

.debug-results {
  margin-top: 8px;
  padding: 10px 10px 9px;
  border-radius: 9px;
  border: 1px solid color-mix(in srgb, var(--border) 82%, var(--accent) 14%);
  background: linear-gradient(180deg, #f8fafc 0%, #fff 52%, #fff 100%);
  box-shadow:
    0 4px 14px rgba(15, 23, 42, 0.045),
    inset 0 1px 0 rgba(255, 255, 255, 0.85);
}

.results-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px 10px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
}

.results-head-main {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  flex: 1 1 200px;
}

.results-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.02em;
}

.result-status-wrap {
  flex-shrink: 0;
}

.result-status {
  display: inline-block;
  font-size: 11px;
  font-weight: 800;
  padding: 4px 12px;
  min-width: 76px;
  text-align: center;
  border-radius: 999px;
  letter-spacing: 0.02em;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
}

.result-status.is-idle {
  background: linear-gradient(180deg, #f1f5f9, #e2e8f0);
  color: #475569;
  border: 1px solid #cbd5e1;
}

.result-status.is-pending {
  background: color-mix(in srgb, var(--accent) 14%, #fff);
  color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
  animation: dbg-pulse 1.1s ease-in-out infinite;
}

.result-status.is-ok {
  background: linear-gradient(180deg, #ecfccb, #dcfce7);
  color: #14532d;
  border: 1px solid #86efac;
}

.result-status.is-warn {
  background: linear-gradient(180deg, #fffbeb, #fef3c7);
  color: #92400e;
  border: 1px solid #fcd34d;
}

.result-status.is-err {
  background: linear-gradient(180deg, #fef2f2, #fee2e2);
  color: #991b1b;
  border: 1px solid #fca5a5;
}

@keyframes dbg-pulse {
  50% {
    opacity: 0.75;
  }
}

.results-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-block {
  padding: 7px 9px 8px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid color-mix(in srgb, var(--border) 88%, transparent);
  box-shadow: none;
}

.result-block-hd {
  margin: 0 0 5px;
}

.result-block .lbl {
  margin-top: 0;
}

.mini-strong {
  min-width: 44px;
  font-weight: 600;
  color: #475569;
  border-color: #cbd5e1;
}

.mini-strong:hover {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 40%, #cbd5e1);
  background: #fff;
}

.cap-details {
  margin-top: 8px;
  padding: 0;
  background: transparent;
  border: none;
}

.cap-details[open] {
  padding-bottom: 0;
}

.cap-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  font-size: 11.5px;
  font-weight: 700;
  color: #334155;
  cursor: pointer;
  user-select: none;
  padding: 2px 0 6px;
  list-style: none;
}

.cap-summary-lbl {
  min-width: 0;
}

.cap-summary-tip {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

.cap-summary-tip :deep(.info-tip) {
  color: #64748b;
}

.cap-summary-tip :deep(.info-tip:hover),
.cap-summary-tip :deep(.info-tip:focus-visible) {
  color: var(--accent);
}

.cap-summary::-webkit-details-marker {
  display: none;
}

.cap-summary::before {
  content: "";
  display: inline-block;
  width: 0;
  height: 0;
  margin-right: 5px;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 5px solid #64748b;
  transform: translateY(-1px);
  transition: transform 0.15s ease;
}

.cap-details[open] > .cap-summary::before {
  transform: rotate(90deg) translate(1px, 0);
}

.cap-summary:hover {
  color: var(--accent);
}

.cap-details[open] .cap-summary {
  margin-bottom: 6px;
  color: var(--text);
}

.cap-summary:hover::before {
  border-left-color: var(--accent);
}

.logs-empty {
  margin: 0;
  padding: 7px 9px;
  font-size: 10.5px;
  color: #94a3b8;
  border: 1px dashed color-mix(in srgb, var(--border) 92%, transparent);
  border-radius: 6px;
  background: #fafafa;
}

.hint.muted {
  color: #94a3b8;
  font-weight: 400;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.head-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
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
  font-size: 11px;
}

.hint {
  font-size: 10.5px;
  color: var(--muted);
}

.mini {
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
  border-radius: 5px;
  padding: 2px 7px;
  font-size: 10.5px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.mini:hover {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
}

.area.invalid {
  border-color: #fca5a5;
  background: #fff7f7;
}

.area {
  width: 100%;
  border-radius: 7px;
  border: 1px solid var(--border);
  padding: 7px 9px;
  font-size: 11.5px;
  line-height: 1.5;
  resize: vertical;
  outline: none;
  background: #fbfdff;
  color: var(--text);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.area:focus {
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}

.out {
  margin: 0;
  padding: 8px;
  border-radius: 7px;
  border: 1px solid color-mix(in srgb, #1e293b 55%, var(--border));
  background: #0f172a;
  color: #e2e8f0;
  min-height: 56px;
  max-height: 200px;
  overflow: auto;
  font-size: 10.5px;
  line-height: 1.45;
}

.logs {
  list-style: none;
  padding: 0;
  margin: 0;
  border: 1px solid var(--border);
  border-radius: 7px;
  max-height: 140px;
  overflow: auto;
  background: #fff;
}

.log-row {
  display: grid;
  grid-template-columns: 58px 44px 88px 1fr auto;
  gap: 6px;
  align-items: baseline;
  padding: 3px 8px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
  font-size: 10.5px;
  line-height: 1.4;
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
