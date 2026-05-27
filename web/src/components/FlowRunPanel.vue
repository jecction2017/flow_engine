<template>
  <Teleport to="body">
    <div
      v-show="visible"
      class="frp-backdrop"
      aria-hidden="true"
      @click.self="$emit('close')"
    />
    <aside
      class="frp-drawer"
      :class="{ 'frp-drawer--open': visible }"
      role="dialog"
      aria-modal="true"
      aria-label="流程试运行"
      @click.stop
    >
      <div class="frp-drawer-hd">
        <div class="frp-drawer-title-block">
          <span class="frp-drawer-title">流程试运行</span>
        </div>
        <div class="frp-drawer-hd-actions">
          <button
            type="button"
            class="btn primary sm"
            :disabled="pending || !flowId"
            @click="run"
          >
            {{ pending ? "运行中…" : "▶ 试运行" }}
          </button>
          <button type="button" class="btn ghost sm" @click="$emit('close')">关闭</button>
        </div>
      </div>

      <div class="frp-drawer-body">
        <div class="trial-run-columns">
          <div class="trial-settings-col">
            <div class="debug-settings">
              <div class="settings-panel">
                <header class="settings-panel-hd">
                  <div class="settings-panel-titles">
                    <span class="settings-panel-title">试运行设置</span>
                    <span class="settings-panel-sub">
                      Profile、试运行上下文、数据字典覆盖与附加策略仅作用于本次试运行请求，不写回流程 YAML。
                    </span>
                  </div>
                </header>
                <div class="settings-stack">
                  <div class="trial-settings-stack">
                    <section class="trial-settings-field">
                      <div class="field-line field-line--tight">
                        <span class="field-line-lbl">
                          试运行 Profile
                          <InfoTip
                            text="对应请求字段 profile，决定数据字典从哪套 Profile 加载。留空时使用服务端全局默认（见选项首行）；与流程文档里的默认 profile 可能不同。技术名：profile。"
                          />
                        </span>
                      </div>
                      <div class="profile-select-shell">
                        <select v-model="profileText" class="inp inp-profile mono">
                          <option value="">使用全局默认（{{ defaultProfile || "default" }}）</option>
                          <option v-for="p in profileOptions" :key="p" :value="p">{{ p }}</option>
                        </select>
                      </div>
                    </section>

                    <section class="trial-settings-field trial-settings-field--timeout">
                      <div class="field-line field-line--tight">
                        <span class="field-line-lbl">
                          超时（秒）
                          <InfoTip text="单次试运行请求在服务端等待完成的最长时间（timeout_sec），超出可能返回错误或终止状态。" />
                        </span>
                      </div>
                      <div class="profile-select-shell profile-select-shell--narrow">
                        <input
                          v-model.number="timeoutSec"
                          class="inp inp-profile mono trial-timeout-inp"
                          type="number"
                          min="1"
                          max="600"
                          step="1"
                        />
                      </div>
                    </section>

                    <section class="trial-settings-field">
                      <div class="ctx-json-block">
                        <div class="ctx-json-head">
                          <span class="field-line-lbl">
                            试运行上下文 (JSON)
                            <InfoTip
                              wide
                              text="打开抽屉时默认填入流程文档中的 initial_context。可任意编辑；试运行时将该 JSON 对象作为请求体 initial_context 原样提交，不再与文档做合并或「覆盖」计算。须为 JSON 对象；空对象 {} 表示空上下文。与 Task 节点边界映射无关。"
                            />
                          </span>
                          <div class="ctx-json-actions">
                            <button type="button" class="mini mini-strong" @click="resetCtxFromFlow">重置</button>
                            <button type="button" class="mini mini-strong" @click="clearCtx">清空</button>
                          </div>
                        </div>
                        <JsonEditor
                          v-model="ctxText"
                          :height="220"
                          :invalid="!ctxJsonValid"
                          placeholder="{}"
                        />
                        <div class="ctx-hint-footer">
                          <template v-if="ctxJsonValid">
                            <div class="ctx-hint-line">
                              <span class="ctx-hint-text">顶层键</span>
                              <template v-if="ctxTopKeys.length">
                                <template v-for="(k, i) in ctxTopKeys" :key="k">
                                  <span class="ctx-hint-token mono">{{ k }}</span>
                                  <span v-if="i < ctxTopKeys.length - 1" class="ctx-hint-sep">、</span>
                                </template>
                                <span class="ctx-hint-text">将随本次请求一并提交。</span>
                              </template>
                              <template v-else>
                                <span class="ctx-hint-text ctx-hint-weak">空对象：本次试运行以空 initial_context 提交。</span>
                              </template>
                            </div>
                          </template>
                          <div v-else class="ctx-hint-line err">JSON 无法解析，试运行前请修正或清空。</div>
                        </div>
                      </div>
                    </section>

                    <section class="trial-settings-field">
                      <div class="dict-yaml-block">
                        <div class="ctx-json-head">
                          <span class="field-line-lbl">
                            数据字典覆盖 (YAML)
                            <InfoTip
                              wide
                              text="对应请求体字段 runtime_patch：在当前选择的 Profile 解析得到的数据字典树之上做深度合并，写法与数据字典 YAML 配置一致（根须为映射）。用于本次试运行临时调整字典模块/路径；留空表示不追加覆盖。填写错误可能导致服务端解析失败或执行异常。"
                            />
                          </span>
                          <div class="ctx-json-actions">
                            <button type="button" class="mini mini-strong" @click="clearDictOverrideYaml">清空</button>
                          </div>
                        </div>
                        <textarea
                          v-model="dictOverrideYaml"
                          class="area mono area-ctx area-ctx--yaml"
                          :class="{ invalid: !dictYamlValid }"
                          spellcheck="false"
                          placeholder="# 可选，根须为映射；与数据字典 YAML 结构一致"
                        />
                        <div v-if="dictYamlValid" class="ctx-hint-line">
                          <span class="ctx-hint-text ctx-hint-weak">留空则不对 Profile 字典做额外合并。</span>
                        </div>
                        <div v-else class="ctx-hint-line err">{{ dictYamlError || "YAML 无法解析" }}</div>
                      </div>
                    </section>

                    <section class="trial-settings-field trial-settings-field--cap">
                      <details class="cap-details">
                        <summary class="cap-summary">
                          <span class="cap-summary-lbl">副作用函数抑制（仅本次试运行）</span>
                          <span class="cap-summary-tip" @click.stop>
                            <InfoTip
                              wide
                              text="试运行固定为调试模式，默认抑制副作用类内置函数。此处规则仅随本次请求发送，可放行或配置重定向参数；与流程节点上已保存的规则在服务端叠加。不写回 YAML。"
                            />
                          </span>
                        </summary>
                        <CapabilityRulesEditor v-model="capabilityPolicy" />
                      </details>
                    </section>
                  </div>
                  <p v-if="error" class="err">{{ error }}</p>
                </div>
              </div>
            </div>
          </div>

          <div class="trial-results-col">
            <div class="trial-results debug-results">
              <div class="results-head">
              <div class="results-head-main">
                <span class="results-title">试运行结果</span>
                <InfoTip
                  text="包含流程状态、节点时间线、全局上下文 global_ns 与流程级日志；与左侧试运行设置相互独立。"
                />
              </div>
              <div class="result-status-wrap">
                <span class="result-status" :class="trialResultStatusClass">{{ trialResultStatusText }}</span>
              </div>
            </div>
            <div v-if="response" class="results-meta">
              <span class="badge meta-badge" :class="stateClass(response.state)">{{ response.state }}</span>
              <span class="muted">· {{ response.elapsed_ms }}ms</span>
              <template v-if="summary">
                <span class="chip ok" title="成功节点">✓ {{ summary.ok }}</span>
                <span v-if="summary.failed" class="chip bad" title="失败节点">✗ {{ summary.failed }}</span>
                <span v-if="summary.skipped" class="chip skipped" title="跳过节点">⊘ {{ summary.skipped }}</span>
                <span v-if="summary.running" class="chip running" title="未完成节点">◌ {{ summary.running }}</span>
              </template>
              <span v-if="response" class="muted">· {{ rawRuns.length }} 条执行记录</span>
            </div>

            <div class="results-body">
              <div v-if="trialRunAlertVisible" class="trial-flow-alert" :class="trialRunAlertToneClass" role="alert">
                <span class="trial-flow-alert-title">{{ trialRunAlertTitle }}</span>
                <span class="trial-flow-alert-msg">{{ trialRunAlertBody }}</span>
              </div>
              <div class="results-panes">
                <div class="result-block result-block--timeline">
                  <div class="lbl row result-block-hd">
                    <span class="lbl-row">
                      节点执行时间线
                      <InfoTip text="各节点起止时间与状态；可展开子节点、按日志级别筛选后查看节点内日志。区域最高 380px，超出部分在内部滚动。" />
                    </span>
                  </div>
                  <div class="result-pane-scroll">
                    <div v-if="!response" class="hint">未运行</div>
                    <div v-else-if="rawRuns.length === 0" class="hint">没有节点被调度</div>
                    <ExecutionLinkTree
                      v-else
                      class="trial-exec-tree"
                    :rows="trialLinkRows"
                    :timeline-min-ms="0"
                    :timeline-max-ms="maxMs"
                    :collapsed="collapsed"
                    :secondary-open-key="openLogsFor"
                    :detail-on-row-click="false"
                    :log-button="true"
                    :show-node-meta="false"
                    @toggle-collapsed="toggleCollapsed"
                    @toggle-secondary="toggleLogDrawer"
                  >
                    <template #toolbar>
                      <button class="link" type="button" @click="expandAll">全部展开</button>
                      <span class="sep">·</span>
                      <button class="link" type="button" @click="collapseAll">全部折叠</button>
                      <span class="sep">·</span>
                      <span class="rt-filter-lbl">日志级别</span>
                      <button
                        v-for="lvl in LOG_LEVELS"
                        :key="lvl"
                        type="button"
                        class="rt-chip-btn"
                        :class="[`lvl-${lvl}`, { active: levelFilter.has(lvl) }]"
                        @click="toggleLevelFilter(lvl)"
                      >
                        {{ lvl }}
                      </button>
                      <button v-if="levelFilter.size > 0" type="button" class="link" @click="clearLevelFilter">清除</button>
                      <span v-if="levelFilter.size > 0" class="muted">命中 {{ filterHitCount }} / 总计 {{ rawRuns.length }}</span>
                    </template>
                    <template #secondary="{ row }">
                      <div class="rt-logs-drawer">
                        <div class="rt-logs-head">
                          <span>{{ row.nodeId }} 日志</span>
                          <span class="muted">
                            共 {{ logCountsByRunOrder.get(row.key) ?? 0 }} 条
                            <template v-if="levelFilter.size > 0">· 已过滤 {{ filteredLogsFor(row.key).length }} 条</template>
                          </span>
                        </div>
                        <ul v-if="filteredLogsFor(row.key).length" class="rt-logs-list mono">
                          <li
                            v-for="(entry, i) in filteredLogsFor(row.key)"
                            :key="i"
                            class="rt-log-row"
                            :class="`lvl-${entry.level}`"
                          >
                            <span class="rt-log-ts">+{{ entry.ts_ms }}ms</span>
                            <span class="rt-log-lvl">{{ entry.level }}</span>
                            <span class="rt-log-src" :title="`来源: ${entry.source}`">
                              {{ entry.source }}<span v-if="entry.attempt" class="rt-log-attempt">#{{ entry.attempt }}</span>
                            </span>
                            <span class="rt-log-msg">{{ entry.message }}</span>
                            <span v-if="entry.truncated" class="rt-log-trunc" title="达到日志上限，后续条目被丢弃">...</span>
                          </li>
                        </ul>
                        <div v-else class="muted rt-logs-empty">当前过滤条件下没有可显示的日志</div>
                      </div>
                    </template>
                    <template #footer>
                      <div v-if="trialLinkRows.length === 0" class="rt-filter-empty muted">
                        当前日志级别筛选下没有执行记录
                      </div>
                      <section v-if="flowLogs.length" class="rt-flow-logs">
                        <div class="rt-flow-logs-head">
                          <span>流程级日志</span>
                          <span class="muted">{{ flowLogs.length }} 条 · on_start / on_complete / on_failure</span>
                        </div>
                        <ul v-if="filteredFlowLogs.length" class="rt-logs-list mono">
                          <li
                            v-for="(entry, i) in filteredFlowLogs"
                            :key="i"
                            class="rt-log-row"
                            :class="`lvl-${entry.level}`"
                          >
                            <span class="rt-log-ts">+{{ entry.ts_ms }}ms</span>
                            <span class="rt-log-lvl">{{ entry.level }}</span>
                            <span class="rt-log-src" :title="`来源: ${entry.source}`">{{ entry.source }}</span>
                            <span class="rt-log-msg">{{ entry.message }}</span>
                            <span v-if="entry.truncated" class="rt-log-trunc" title="达到日志上限">...</span>
                          </li>
                        </ul>
                        <div v-else class="muted rt-logs-empty">当前过滤条件下没有可显示的日志</div>
                      </section>
                    </template>
                  </ExecutionLinkTree>
                  </div>
                </div>

                <div
                  ref="globalsPaneBlockRef"
                  class="result-block result-block--globals"
                  :style="{ height: `${globalsPaneHeight}px` }"
                >
                  <div class="lbl row result-block-hd">
                    <span class="lbl-row">
                      全局上下文 (global_ns)
                      <InfoTip text="试运行完成后按内容自动增高（最高 380px）；可拖动右下角继续调整高度，超出部分在内部滚动。" />
                    </span>
                  </div>
                  <div class="result-pane-scroll">
                    <pre ref="globalsPreRef" class="out mono">{{ globalsText }}</pre>
                    <p v-if="response?.message && !responseMessageAsFailureNotice" class="msg">{{ response.message }}</p>
                  </div>
                  <button
                    type="button"
                    class="pane-resize-corner"
                    aria-label="拖动调整全局上下文区域高度"
                    :class="{ 'pane-resize-corner--active': globalsResizeActive }"
                    @mousedown="startGlobalsResize($event)"
                  />
                </div>
              </div>
            </div>
            </div>
          </div>
        </div>
      </div>
    </aside>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onUnmounted, reactive, ref, watch } from "vue";
import { parseDocument } from "yaml";
import { runFlow } from "@/api/flows";
import type { LogEntry, NodeRunInfo, RunFlowResponse } from "@/api/flows";
import { fetchProfileConfig } from "@/api/profiles";
import CapabilityRulesEditor from "@/components/CapabilityRulesEditor.vue";
import ExecutionLinkTree, { type ExecutionLinkRow } from "@/components/ExecutionLinkTree.vue";
import InfoTip from "@/components/InfoTip.vue";
import JsonEditor from "@/components/JsonEditor.vue";
import type { CapabilityRule } from "@/types/flow";

const LOG_LEVELS = ["debug", "info", "warn", "error"] as const;
type KnownLogLevel = (typeof LOG_LEVELS)[number];

function normalizeKnownLevel(level: string | undefined): KnownLogLevel | null {
  const s = typeof level === "string" ? level.trim().toLowerCase() : "";
  return (LOG_LEVELS as readonly string[]).includes(s) ? (s as KnownLogLevel) : null;
}

type TreeRow = NodeRunInfo & {
  depth: number;
  hasChildren: boolean;
  isLast: boolean;
  /**
   * Per-ancestor vertical guide lines (one per ancestor depth). ``true``
   * means the ancestor at that depth still has further siblings below,
   * so we should draw a continuing line; ``false`` means empty space.
   */
  guides: boolean[];
};

const props = defineProps<{
  flowId: string | null;
  visible: boolean;
  initialContext: Record<string, unknown> | null | undefined;
}>();
const emit = defineEmits<{ (e: "close"): void }>();

function onRunEscape(ev: KeyboardEvent) {
  if (ev.key !== "Escape" || !props.visible) return;
  emit("close");
}

watch(
  () => props.visible,
  (v) => {
    if (v) document.addEventListener("keydown", onRunEscape);
    else document.removeEventListener("keydown", onRunEscape);
  },
  { immediate: true },
);

onUnmounted(() => {
  document.removeEventListener("keydown", onRunEscape);
  stopGlobalsResize();
});

const ctxText = ref("");
const profileText = ref("");
const profileOptions = ref<string[]>(["default"]);
const defaultProfile = ref("default");
/** 数据字典覆盖：YAML → 解析为对象后作为 runtime_patch 提交 */
const dictOverrideYaml = ref("");
const timeoutSec = ref(30);
const pending = ref(false);
const response = ref<RunFlowResponse | null>(null);
const error = ref<string | null>(null);
// 试运行临时附加策略（高级）；服务端永远 RunMode.DEBUG，此处只能 ALLOW / REDIRECT。
const capabilityPolicy = ref<CapabilityRule[]>([]);
const collapsed = reactive(new Set<string>());
/** id of the currently open log drawer, or null when none is open. */
const openLogsFor = ref<string | null>(null);
/** Active log-level filter. Empty set = show all. */
const levelFilter = reactive(new Set<KnownLogLevel>());

const GLOBALS_PANE_MIN = 100;
const GLOBALS_PANE_DEFAULT = 200;
const GLOBALS_PANE_AUTO_MAX = 380;
const globalsPaneHeight = ref(GLOBALS_PANE_DEFAULT);
const globalsPaneBlockRef = ref<HTMLElement | null>(null);
const globalsPreRef = ref<HTMLElement | null>(null);
const globalsResizeActive = ref(false);
let globalsHeightManuallySet = false;

let globalsResizeStartY = 0;
let globalsResizeStartHeight = 0;

function resetGlobalsPaneHeight() {
  globalsHeightManuallySet = false;
  globalsPaneHeight.value = GLOBALS_PANE_DEFAULT;
}

function measureGlobalsPaneHeight(): number {
  const block = globalsPaneBlockRef.value;
  const pre = globalsPreRef.value;
  if (!block || !pre) return GLOBALS_PANE_DEFAULT;
  const header = block.querySelector<HTMLElement>(".result-block-hd");
  const msg = block.querySelector<HTMLElement>(".msg");
  const headerH = header?.offsetHeight ?? 0;
  const preH = pre.scrollHeight;
  const msgH = msg?.offsetHeight ?? 0;
  const chrome = 20;
  const desired = headerH + preH + msgH + chrome;
  return Math.min(
    GLOBALS_PANE_AUTO_MAX,
    Math.max(GLOBALS_PANE_DEFAULT, desired),
  );
}

async function syncGlobalsPaneAutoHeight() {
  if (globalsHeightManuallySet || !response.value) return;
  await nextTick();
  globalsPaneHeight.value = measureGlobalsPaneHeight();
}

function onGlobalsResizeMove(ev: MouseEvent) {
  const dy = ev.clientY - globalsResizeStartY;
  globalsPaneHeight.value = Math.max(
    GLOBALS_PANE_MIN,
    globalsResizeStartHeight + dy,
  );
}

function stopGlobalsResize() {
  globalsResizeActive.value = false;
  document.removeEventListener("mousemove", onGlobalsResizeMove);
  document.removeEventListener("mouseup", stopGlobalsResize);
  document.body.style.removeProperty("user-select");
  document.body.style.removeProperty("cursor");
}

function startGlobalsResize(ev: MouseEvent) {
  ev.preventDefault();
  globalsHeightManuallySet = true;
  globalsResizeActive.value = true;
  globalsResizeStartY = ev.clientY;
  globalsResizeStartHeight = globalsPaneHeight.value;
  document.body.style.userSelect = "none";
  document.body.style.cursor = "nwse-resize";
  document.addEventListener("mousemove", onGlobalsResizeMove);
  document.addEventListener("mouseup", stopGlobalsResize);
}

function parseJsonObject(text: string): { ok: boolean; keys: string[] } {
  const raw = text.trim();
  if (!raw) return { ok: true, keys: [] };
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return { ok: true, keys: Object.keys(parsed as Record<string, unknown>) };
    }
    return { ok: false, keys: [] };
  } catch {
    return { ok: false, keys: [] };
  }
}

const ctxJsonParsed = computed(() => parseJsonObject(ctxText.value));
const ctxJsonValid = computed(() => ctxJsonParsed.value.ok);
const ctxTopKeys = computed(() => ctxJsonParsed.value.keys);

function parseYamlRootMapping(text: string): { ok: boolean; value: Record<string, unknown> | null; err: string } {
  const raw = text.trim();
  if (!raw) return { ok: true, value: null, err: "" };
  try {
    const doc = parseDocument(raw);
    if (doc.errors.length) {
      return { ok: false, value: null, err: doc.errors[0]!.message };
    }
    const js = doc.toJS();
    if (js === null || js === undefined) return { ok: true, value: null, err: "" };
    if (typeof js !== "object" || Array.isArray(js)) {
      return { ok: false, value: null, err: "根节点须为 YAML 映射（对象），不能为序列或标量" };
    }
    return { ok: true, value: js as Record<string, unknown>, err: "" };
  } catch (e) {
    return { ok: false, value: null, err: e instanceof Error ? e.message : String(e) };
  }
}

const dictYamlResult = computed(() => parseYamlRootMapping(dictOverrideYaml.value));
const dictYamlValid = computed(() => dictYamlResult.value.ok);
const dictYamlError = computed(() => dictYamlResult.value.err);

type TrialResultPhase = "idle" | "pending" | "blocked" | "ok" | "flow_err" | "warn";

const trialResultPhase = computed<TrialResultPhase>(() => {
  if (pending.value) return "pending";
  if (error.value && !response.value) return "blocked";
  const r = response.value;
  if (!r) return "idle";
  const st = (r.state ?? "").toUpperCase();
  if (st === "COMPLETED") return "ok";
  if (st === "FAILED") return "flow_err";
  if (st === "TERMINATED") return "warn";
  return "warn";
});

const trialResultStatusText = computed(() => {
  switch (trialResultPhase.value) {
    case "idle":
      return "未运行";
    case "pending":
      return "执行中…";
    case "blocked":
      return "无法执行";
    case "ok":
      return "已完成";
    case "flow_err":
      return "失败";
    case "warn":
      return response.value?.state?.trim() || "已结束";
    default:
      return "";
  }
});

const trialResultStatusClass = computed(() => ({
  "is-idle": trialResultPhase.value === "idle",
  "is-pending": trialResultPhase.value === "pending",
  "is-ok": trialResultPhase.value === "ok",
  "is-warn": trialResultPhase.value === "warn",
  "is-err": trialResultPhase.value === "blocked" || trialResultPhase.value === "flow_err",
}));

const responseFlowMessageTrimmed = computed(() => {
  const m = response.value?.message;
  return typeof m === "string" && m.trim() ? m.trim() : null;
});

/** 流程 FAILED / TERMINATED：服务端 message 在结果区顶部横幅展示，避免埋在 global_ns 下方 */
const responseMessageAsFailureNotice = computed(() => {
  const r = response.value;
  if (!r) return false;
  const st = (r.state ?? "").toUpperCase();
  return st === "FAILED" || st === "TERMINATED";
});

const trialRunAlertVisible = computed(() => {
  if (error.value?.trim() && !response.value) return true;
  if (response.value && responseMessageAsFailureNotice.value) return true;
  return false;
});

const trialRunAlertBody = computed(() => {
  if (error.value?.trim() && !response.value) return error.value.trim();
  const msg = responseFlowMessageTrimmed.value;
  if (msg) return msg;
  if (response.value && responseMessageAsFailureNotice.value) {
    return "未返回具体说明；请查看节点时间线与流程级日志。";
  }
  return "";
});

const trialRunAlertTitle = computed(() => {
  if (error.value?.trim() && !response.value) return "无法执行";
  const st = response.value?.state?.trim();
  return st && st.length ? st : "流程提示";
});

const trialRunAlertToneClass = computed(() => {
  if (error.value?.trim() && !response.value) return "trial-flow-alert--err";
  const st = (response.value?.state ?? "").toUpperCase();
  if (st === "FAILED") return "trial-flow-alert--err";
  return "trial-flow-alert--warn";
});

function resetCtxFromFlow() {
  const v = props.initialContext;
  ctxText.value = v ? JSON.stringify(v, null, 2) : "";
}

function clearCtx() {
  ctxText.value = "{}";
}

function clearDictOverrideYaml() {
  dictOverrideYaml.value = "";
}

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
    dictOverrideYaml.value = "";
    collapsed.clear();
    openLogsFor.value = null;
    resetGlobalsPaneHeight();
  },
);

watch(
  () => response.value,
  (r) => {
    if (!r) {
      if (!globalsHeightManuallySet) globalsPaneHeight.value = GLOBALS_PANE_DEFAULT;
      return;
    }
    void syncGlobalsPaneAutoHeight();
  },
);

void (async () => {
  try {
    const res = await fetchProfileConfig();
    defaultProfile.value = res.default_profile || "default";
    profileOptions.value = Array.isArray(res.profiles) && res.profiles.length ? [...res.profiles] : ["default"];
  } catch {
    // fallback keep default option only
  }
})();

const globalsText = computed(() =>
  response.value ? JSON.stringify(response.value.global_ns, null, 2) : "// 未运行",
);

// Raw per-node runs. If the backend didn't return `node_runs` (older server),
// fall back to synthesising rows from `node_state` so the UI stays useful
// against mixed deployments.
const rawRuns = computed<NodeRunInfo[]>(() => {
  const r = response.value;
  if (!r) return [];
  if (Array.isArray(r.node_runs) && r.node_runs.length > 0) {
    return [...r.node_runs].sort((a, b) => a.order - b.order);
  }
  const entries = Object.entries(r.node_state ?? {});
  return entries.map(([nid, st], i) => ({
    node_id: nid,
    order: i,
    first_seen_ms: 0,
    started_ms: null,
    finished_ms: null,
    duration_ms: null,
    final_state: st,
    parent_id: null,
    transitions: [],
  }));
});

/** Parent row key: ``parent_order`` when present, else latest preceding row with ``parent_id``. */
function resolveParentRunKey(r: NodeRunInfo, sorted: NodeRunInfo[]): string | null {
  const po = r.parent_order;
  if (po != null && Number.isFinite(Number(po))) {
    return String(po);
  }
  const pid = r.parent_id?.trim();
  if (!pid) return null;
  for (let i = sorted.length - 1; i >= 0; i--) {
    const cand = sorted[i]!;
    if (cand.order >= r.order) continue;
    if (cand.node_id === pid) return String(cand.order);
  }
  return null;
}

function runMatchesLevelFilter(run: NodeRunInfo): boolean {
  if (levelFilter.size === 0) return true;
  const all = Array.isArray(run.logs) ? run.logs : [];
  return all.some((e) => {
    const nk = normalizeKnownLevel(e.level);
    return nk != null && levelFilter.has(nk);
  });
}

/**
 * Flatten the parent/child tree (keys = ``order`` strings) so repeated
 * ``node_id`` across loop iterations stay distinct — aligned with persisted spans.
 */
const treeRows = computed<TreeRow[]>(() => {
  const runs = rawRuns.value;
  if (runs.length === 0) return [];
  const sorted = [...runs].sort((a, b) => a.order - b.order);
  const byOrder = new Map(sorted.map((rr) => [rr.order, rr]));
  const childrenByParent = new Map<string | null, number[]>();
  const parentByOrder = new Map<number, string | null>();
  for (const r of sorted) {
    const pk = resolveParentRunKey(r, sorted);
    parentByOrder.set(r.order, pk);
    if (!childrenByParent.has(pk)) childrenByParent.set(pk, []);
    childrenByParent.get(pk)!.push(r.order);
  }
  for (const arr of childrenByParent.values()) {
    arr.sort((a, b) => a - b);
  }
  let visibleOrderSet: Set<number> | null = null;
  if (levelFilter.size > 0) {
    visibleOrderSet = new Set<number>();
    for (const r of sorted) {
      if (!runMatchesLevelFilter(r)) continue;
      visibleOrderSet.add(r.order);
      let parentKey = parentByOrder.get(r.order) ?? null;
      while (parentKey != null) {
        const po = Number(parentKey);
        if (!Number.isFinite(po) || visibleOrderSet.has(po)) break;
        visibleOrderSet.add(po);
        parentKey = parentByOrder.get(po) ?? null;
      }
    }
  }
  const out: TreeRow[] = [];
  const walk = (orderIds: number[], depth: number, ancestorGuides: boolean[]) => {
    const visibleOrders = visibleOrderSet
      ? orderIds.filter((ord) => visibleOrderSet!.has(ord))
      : orderIds;
    visibleOrders.forEach((ord, idx) => {
      const run = byOrder.get(ord)!;
      const isLast = idx === visibleOrders.length - 1;
      const childOrders = childrenByParent.get(String(ord)) ?? [];
      out.push({
        ...run,
        depth,
        hasChildren: childOrders.length > 0,
        isLast,
        guides: [...ancestorGuides],
      });
      if (childOrders.length > 0 && !collapsed.has(String(ord))) {
        walk(childOrders, depth + 1, [...ancestorGuides, !isLast]);
      }
    });
  };
  walk(childrenByParent.get(null) ?? [], 0, []);
  return out;
});

const maxMs = computed(() => {
  const r = response.value;
  if (!r) return 0;
  let m = r.elapsed_ms || 0;
  for (const row of rawRuns.value) {
    if (row.finished_ms != null) m = Math.max(m, row.finished_ms);
    if (row.started_ms != null) m = Math.max(m, row.started_ms);
  }
  return Math.max(1, m);
});

function formatDur(ms: number | null): string {
  if (ms == null) return "-";
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatOffset(ms: number): string {
  if (ms < 1000) return `+${ms}ms`;
  if (ms < 60_000) return `+${(ms / 1000).toFixed(3)}s`;
  const mins = Math.floor(ms / 60_000);
  const sec = ((ms % 60_000) / 1000).toFixed(3);
  return `+${mins}m${sec}s`;
}

function formatDelta(ms: number): string {
  if (ms < 1000) return `Δ+${ms}ms`;
  if (ms < 60_000) return `Δ+${(ms / 1000).toFixed(3)}s`;
  const mins = Math.floor(ms / 60_000);
  const sec = ((ms % 60_000) / 1000).toFixed(3);
  return `Δ+${mins}m${sec}s`;
}

function trialTone(st: string): string {
  if (st === "SUCCESS") return "ok";
  if (st === "FAILED") return "bad";
  if (st === "SKIPPED") return "skipped";
  if (st === "RUNNING" || st === "DISPATCHED" || st === "STAGING") return "running";
  return "info";
}

const trialLinkRows = computed<ExecutionLinkRow[]>(() => {
  const m = maxMs.value;
  let prevStartedMs: number | null = null;
  return treeRows.value.map((tr) => {
    const start = tr.started_ms ?? tr.first_seen_ms ?? 0;
    const end = tr.finished_ms ?? (tr.started_ms != null ? Math.max(tr.started_ms, m) : start + 1);
    let startedDeltaDisplay: string | undefined;
    let startedDeltaTitle: string | undefined;
    if (tr.started_ms != null && prevStartedMs != null) {
      const delta = Math.max(0, tr.started_ms - prevStartedMs);
      startedDeltaDisplay = formatDelta(delta);
      startedDeltaTitle = `相对上一行开始时间 +${delta}ms`;
    }
    if (tr.started_ms != null) prevStartedMs = tr.started_ms;
    const badges: { label: string; title?: string }[] = [];
    if (tr.iterations != null) badges.push({ label: `×${tr.iterations}`, title: "迭代次数" });
    else if (tr.execution_count && tr.execution_count > 1) {
      badges.push({ label: `×${tr.execution_count}`, title: "执行次数" });
    }
    const logCount = filteredLogsFor(String(tr.order)).length;
    return {
      key: String(tr.order),
      orderDisplay: String(tr.order + 1),
      depth: tr.depth,
      hasChildren: tr.hasChildren,
      isLast: tr.isLast,
      guides: tr.guides,
      nodeId: tr.node_id,
      nodeType: "",
      scopeKey: "",
      startedDisplay: tr.started_ms != null ? formatOffset(tr.started_ms) : "—",
      startedTitle: tr.started_ms != null ? `相对流程起点 +${tr.started_ms}ms` : undefined,
      startedDeltaDisplay,
      startedDeltaTitle,
      durationMs: tr.duration_ms,
      durationDisplay: formatDur(tr.duration_ms),
      statusLabel: tr.final_state,
      statusTone: trialTone(tr.final_state),
      filterMatch: levelFilter.size > 0 && logCount > 0,
      logCount,
      barStartMs: start,
      barEndMs: Math.max(end, start + 1),
      metaBadges: badges.length ? badges : undefined,
    };
  });
});

const filterHitCount = computed(() =>
  levelFilter.size === 0 ? 0 : trialLinkRows.value.reduce((n, r) => n + (r.logCount > 0 ? 1 : 0), 0),
);

const summary = computed(() => {
  if (!response.value) return null;
  const s = { ok: 0, failed: 0, skipped: 0, running: 0 };
  for (const row of rawRuns.value) {
    const st = row.final_state;
    if (st === "SUCCESS") s.ok += 1;
    else if (st === "FAILED") s.failed += 1;
    else if (st === "SKIPPED") s.skipped += 1;
    else s.running += 1;
  }
  return s;
});

const flowLogs = computed<LogEntry[]>(() => {
  const r = response.value;
  return Array.isArray(r?.flow_logs) ? (r!.flow_logs as LogEntry[]) : [];
});

const logCountsByRunOrder = computed<Map<string, number>>(() => {
  const m = new Map<string, number>();
  for (const r of rawRuns.value) {
    m.set(String(r.order), Array.isArray(r.logs) ? r.logs.length : 0);
  }
  return m;
});

function entryMatchesFilter(e: LogEntry): boolean {
  if (levelFilter.size === 0) return true;
  const nk = normalizeKnownLevel(e.level);
  return nk != null && levelFilter.has(nk);
}

function filteredLogsFor(runOrderKey: string): LogEntry[] {
  const ord = Number(runOrderKey);
  const run = rawRuns.value.find((r) => r.order === ord);
  const all = Array.isArray(run?.logs) ? (run!.logs as LogEntry[]) : [];
  return all.filter(entryMatchesFilter);
}

const filteredFlowLogs = computed<LogEntry[]>(() =>
  flowLogs.value.filter(entryMatchesFilter),
);

function toggleLevelFilter(lvl: KnownLogLevel): void {
  if (levelFilter.has(lvl)) levelFilter.delete(lvl);
  else levelFilter.add(lvl);
}

function clearLevelFilter(): void {
  levelFilter.clear();
}

function toggleLogDrawer(runOrderKey: string): void {
  openLogsFor.value = openLogsFor.value === runOrderKey ? null : runOrderKey;
}

function toggleCollapsed(runOrderKey: string): void {
  if (collapsed.has(runOrderKey)) collapsed.delete(runOrderKey);
  else collapsed.add(runOrderKey);
}

function expandAll(): void {
  collapsed.clear();
}

function collapseAll(): void {
  const sorted = [...rawRuns.value].sort((a, b) => a.order - b.order);
  const parents = new Set<string>();
  for (const c of sorted) {
    const pk = resolveParentRunKey(c, sorted);
    if (pk != null) parents.add(pk);
  }
  parents.forEach((k) => collapsed.add(k));
}

function stateClass(state: string): string {
  if (state === "COMPLETED") return "ok";
  if (state === "FAILED") return "bad";
  if (state === "TERMINATED") return "warn";
  return "info";
}

async function run() {
  if (!props.flowId) return;
  error.value = null;
  if (!ctxJsonValid.value) {
    error.value = "试运行上下文 JSON 格式不正确";
    response.value = null;
    return;
  }
  if (!dictYamlValid.value) {
    error.value = dictYamlError.value || "数据字典覆盖 YAML 格式不正确";
    response.value = null;
    return;
  }
  let initialContext: Record<string, unknown>;
  const raw = ctxText.value.trim();
  try {
    if (!raw) {
      initialContext = {};
    } else {
      const parsed: unknown = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("须为 JSON 对象");
      }
      initialContext = parsed as Record<string, unknown>;
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    return;
  }
  const runtimePatch = dictYamlResult.value.value;
  resetGlobalsPaneHeight();
  pending.value = true;
  try {
    response.value = await runFlow(props.flowId, {
      initial_context: initialContext,
      merge: false,
      timeout_sec: timeoutSec.value,
      profile: profileText.value.trim() || null,
      runtime_patch: runtimePatch,
      capability_policy: capabilityPolicy.value as unknown as Array<Record<string, unknown>>,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    response.value = null;
  } finally {
    pending.value = false;
  }
}
</script>

<style scoped>
.frp-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: color-mix(in srgb, #0f172a 32%, transparent);
}

.frp-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 51;
  width: min(1180px, calc(100vw - 16px));
  max-width: 100%;
  background: var(--surface);
  border-left: 1px solid var(--border);
  box-shadow: -8px 0 28px rgba(15, 23, 42, 0.14);
  display: flex;
  flex-direction: column;
  transform: translateX(100%);
  transition: transform 0.22s ease-out, visibility 0.22s;
  pointer-events: none;
  visibility: hidden;
}

.frp-drawer--open {
  transform: translateX(0);
  pointer-events: auto;
  visibility: visible;
}

.frp-drawer-hd {
  flex: 0 0 auto;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}

.frp-drawer-title-block {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  min-width: 0;
  flex: 1 1 auto;
}

.frp-drawer-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.01em;
}

.frp-drawer-hd-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.frp-drawer-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  padding: 10px 12px 12px;
  display: flex;
  flex-direction: column;
}

.trial-run-columns {
  display: flex;
  flex: 1 1 auto;
  gap: 12px;
  min-height: 0;
  align-items: stretch;
}

.trial-settings-col {
  flex: 0 0 min(360px, 34%);
  min-width: 260px;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;
}

.trial-results-col {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

@media (max-width: 900px) {
  .trial-run-columns {
    flex-direction: column;
    overflow-y: auto;
  }

  .trial-settings-col {
    flex: 0 0 auto;
    max-height: min(42vh, 420px);
  }

  .trial-results-col {
    flex: 1 1 auto;
    min-height: min(48vh, 480px);
  }
}

.debug-settings {
  padding-bottom: 0;
}

.settings-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  padding: 0;
  overflow: visible;
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
  min-width: 0;
}

.trial-settings-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.trial-settings-field {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-width: 0;
}

.trial-settings-field--cap .cap-details {
  margin-top: 0;
}

.trial-settings-stack .profile-select-shell:not(.profile-select-shell--narrow) {
  width: fit-content;
  min-width: 200px;
  max-width: min(300px, 100%);
}

.trial-settings-stack .profile-select-shell--narrow {
  max-width: 112px;
}

.dict-yaml-block {
  display: flex;
  flex-direction: column;
  margin-top: 0;
  padding-top: 0;
  border-top: none;
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
}

.inp-profile {
  width: 100%;
  margin: 0;
  border-radius: 6px;
  font-size: 11.5px;
  line-height: 1.35;
  padding: 6px 8px;
  border: none;
  background: #fff;
  box-shadow: none;
  min-height: 30px;
  box-sizing: border-box;
}

.inp-profile:focus {
  outline: none;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 35%, transparent);
}

input.inp-profile.trial-timeout-inp {
  appearance: textfield;
  -moz-appearance: textfield;
}

input.inp-profile.trial-timeout-inp::-webkit-outer-spin-button,
input.inp-profile.trial-timeout-inp::-webkit-inner-spin-button {
  appearance: none;
  margin: 0;
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

.area.invalid {
  border-color: #fca5a5;
  background: #fff7f7;
}

.area:focus {
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}

.area-ctx {
  width: 100%;
  margin-top: 0;
  min-height: 88px;
}


/* 与节点调试一致：标题与框 5px（ctx-json-head），框与提示 6px（.ctx-hint-line） */
.area-ctx--trial-run {
  height: 112px;
  min-height: 112px;
  box-sizing: border-box;
}

.area-ctx--yaml {
  height: 96px;
  min-height: 96px;
  box-sizing: border-box;
}

.mono {
  font-family: var(--mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace);
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

.debug-results {
  margin-top: 0;
  padding: 10px 10px 9px;
  border-radius: 9px;
  border: 1px solid color-mix(in srgb, var(--border) 82%, var(--accent) 14%);
  background: linear-gradient(180deg, #f8fafc 0%, #fff 52%, #fff 100%);
  box-shadow:
    0 4px 14px rgba(15, 23, 42, 0.045),
    inset 0 1px 0 rgba(255, 255, 255, 0.85);
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
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
  animation: trial-pulse 1.1s ease-in-out infinite;
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

@keyframes trial-pulse {
  50% {
    opacity: 0.75;
  }
}

.results-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  margin: -2px 0 8px;
  font-size: 11px;
}

.results-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1 1 auto;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding-bottom: 2px;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;
}

.trial-flow-alert {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 9px 11px;
  border-radius: 8px;
  border: 1px solid;
  font-size: 11.5px;
  line-height: 1.45;
  flex-shrink: 0;
}

.trial-flow-alert-title {
  font-weight: 800;
  letter-spacing: 0.02em;
  color: inherit;
}

.trial-flow-alert-msg {
  font-weight: 500;
  white-space: pre-wrap;
  word-break: break-word;
  color: inherit;
  opacity: 0.95;
}

.trial-flow-alert--err {
  background: linear-gradient(180deg, #fef2f2, #fee2e2);
  border-color: #fca5a5;
  color: #7f1d1d;
}

.trial-flow-alert--warn {
  background: linear-gradient(180deg, #fffbeb, #fef3c7);
  border-color: #fcd34d;
  color: #92400e;
}

.results-panes {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pane-resize-corner {
  position: absolute;
  right: 2px;
  bottom: 2px;
  z-index: 2;
  width: 14px;
  height: 14px;
  padding: 0;
  border: none;
  border-radius: 0 0 6px 0;
  background: transparent;
  cursor: nwse-resize;
  touch-action: none;
}

.pane-resize-corner::after {
  content: "";
  position: absolute;
  right: 2px;
  bottom: 2px;
  width: 8px;
  height: 8px;
  border-right: 2px solid #94a3b8;
  border-bottom: 2px solid #94a3b8;
  border-radius: 0 0 2px 0;
  opacity: 0.75;
  pointer-events: none;
}

.pane-resize-corner:hover::after,
.pane-resize-corner--active::after {
  border-color: var(--accent);
  opacity: 1;
}

.result-pane-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;
}

.result-block {
  padding: 7px 9px 8px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid color-mix(in srgb, var(--border) 88%, transparent);
  box-shadow: none;
  min-width: 0;
}

.result-block-hd {
  margin: 0 0 5px;
}

.result-block .lbl {
  margin-top: 0;
}

.result-block--timeline,
.result-block--globals {
  flex: 0 0 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.result-block--timeline {
  flex: 0 0 auto;
  max-height: 380px;
}

.result-block--globals {
  position: relative;
  flex-shrink: 0;
}

.result-block--timeline .trial-exec-tree {
  min-height: 0;
}

.result-block--globals .result-pane-scroll {
  display: flex;
  flex-direction: column;
}

.result-block--globals .out {
  flex: 1 1 auto;
  min-height: 56px;
  margin: 0;
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
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-weight: 500;
  color: #475569;
  font-size: 11px;
}

.hint {
  font-size: 12px;
  color: var(--muted);
  padding: 8px;
}

.out {
  margin: 0;
  padding: 8px;
  border-radius: 7px;
  border: 1px solid color-mix(in srgb, #1e293b 55%, var(--border));
  background: #0f172a;
  color: #e2e8f0;
  min-height: 56px;
  overflow: auto;
  font-size: 10.5px;
  line-height: 1.45;
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

.badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
}

.badge.meta-badge {
  font-size: 10px;
  padding: 1px 7px;
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

.badge.info {
  background: color-mix(in srgb, #3b82f6 12%, transparent);
  color: #1d4ed8;
  border-color: color-mix(in srgb, #3b82f6 30%, transparent);
}

.chip {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  letter-spacing: 0.02em;
}

.chip.ok {
  background: color-mix(in srgb, #10b981 12%, transparent);
  color: #047857;
  border-color: color-mix(in srgb, #10b981 30%, transparent);
}

.chip.bad {
  background: color-mix(in srgb, #ef4444 12%, transparent);
  color: #b91c1c;
  border-color: color-mix(in srgb, #ef4444 30%, transparent);
}

.chip.skipped {
  background: color-mix(in srgb, #94a3b8 16%, transparent);
  color: #475569;
  border-color: color-mix(in srgb, #94a3b8 30%, transparent);
}

.chip.running {
  background: color-mix(in srgb, #3b82f6 12%, transparent);
  color: #1d4ed8;
  border-color: color-mix(in srgb, #3b82f6 30%, transparent);
}

.muted {
  color: var(--muted);
  font-weight: 400;
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

.btn.sm {
  border-radius: 7px;
  padding: 5px 10px;
  font-size: 11.5px;
  font-weight: 500;
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

.btn.ghost {
  background: #fff;
}

.btn.ghost:hover {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  color: var(--accent);
}
</style>

