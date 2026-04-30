<template>
  <div class="test-page">
    <header class="top">
      <div>
        <div class="title">测试中心</div>
        <div class="subtitle">基于 lookup namespace 驱动的批量回归测试</div>
      </div>
      <div class="head-actions">
        <button type="button" class="btn ghost" @click="newBatch">+ 新建批次</button>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="layout">
      <!-- 左侧：批次列表 -->
      <aside class="sidebar">
        <div class="side-head">
          <span class="side-title">最近批次</span>
          <button type="button" class="btn ghost small" @click="refreshBatches">刷新</button>
        </div>
        <div class="open-by-id">
          <input v-model.number="openByIdInput" type="number" min="1" class="inp mono" placeholder="batch_id" />
          <button type="button" class="btn small" :disabled="!openByIdInput" @click="openById">打开</button>
        </div>
        <ul v-if="batches.length" class="batch-list">
          <li
            v-for="b in batches"
            :key="b.id"
            :class="{ active: selectedBatchId === b.id }"
            @click="selectBatch(b.id)"
          >
            <div class="batch-row1">
              <span class="batch-id mono">#{{ b.id }}</span>
              <span class="tag" :class="batchStatusTag(b.status)">{{ b.status }}</span>
            </div>
            <div class="batch-row2 mono">{{ b.flow_code }} · v{{ b.ver_no }}</div>
            <div class="batch-row3">
              <span class="muted small">{{ b.completed_runs }}/{{ b.total_runs }} 完成</span>
              <span v-if="b.error_runs" class="muted small bad">· {{ b.error_runs }} 失败</span>
            </div>
          </li>
        </ul>
        <div v-else class="muted small pad center">暂无批次记录</div>
      </aside>

      <!-- 右侧：详情或表单 -->
      <main class="main">
        <!-- 新建批次表单 -->
        <section v-if="mode === 'create'" class="panel">
          <header class="panel-head">
            <span class="panel-title">新建批次</span>
            <span class="muted small">每行 lookup 数据 → 一次 RunMode.DEBUG 流程运行</span>
          </header>
          <div class="form-grid">
            <label class="field">
              <span>flow_code <em class="req">*</em></span>
              <select v-model="form.flow_code" class="inp" @change="onFlowChange">
                <option value="">选择流程</option>
                <option v-for="f in flowOptions" :key="f.id" :value="f.id">
                  {{ f.id }}{{ f.display_name ? ` · ${f.display_name}` : "" }}
                </option>
              </select>
            </label>
            <label class="field">
              <span>ver_no <em class="req">*</em></span>
              <select v-model.number="form.ver_no" class="inp" :disabled="!form.flow_code">
                <option :value="0">选择版本</option>
                <option v-for="v in versionOptions" :key="v.version" :value="v.version">
                  v{{ v.version }}{{ v.description ? ` · ${v.description}` : "" }}
                </option>
              </select>
            </label>
            <label class="field">
              <span>test_ns_code <em class="req">*</em></span>
              <select v-model="form.test_ns_code" class="inp">
                <option value="">选择测试 lookup namespace</option>
                <option v-for="ns in lookupNamespaces" :key="ns" :value="ns">{{ ns }}</option>
              </select>
            </label>
            <label class="field">
              <span>profile_code <em class="req">*</em></span>
              <select v-model="form.profile_code" class="inp">
                <option v-for="p in profileOptions" :key="p" :value="p">{{ p }}</option>
              </select>
            </label>
            <label class="field">
              <span>concurrency · {{ form.concurrency }}</span>
              <input v-model.number="form.concurrency" type="range" min="1" max="64" step="1" />
            </label>
          </div>

          <details class="advanced">
            <summary>mock_config（节点级 Mock，按 node_id 配置）</summary>
            <div class="mock-list">
              <div v-for="(item, idx) in mockEntries" :key="idx" class="mock-card">
                <div class="mock-card-head">
                  <input
                    v-model="item.nodeId"
                    class="inp mono"
                    placeholder="node_id"
                    style="flex:1"
                  />
                  <select v-model="item.cfg.mode" class="inp" @change="resetCfg(item)">
                    <option value="script">script</option>
                    <option value="fixed">fixed</option>
                    <option value="record_replay">record_replay</option>
                    <option value="fault">fault</option>
                  </select>
                  <button type="button" class="btn small danger" @click="removeMockEntry(idx)">移除</button>
                </div>
                <textarea
                  v-if="item.cfg.mode === 'script'"
                  v-model="item.scriptText"
                  class="ta mono"
                  rows="4"
                  placeholder="Starlark script returning the mock result"
                  spellcheck="false"
                />
                <textarea
                  v-else-if="item.cfg.mode === 'fixed'"
                  v-model="item.resultText"
                  class="ta mono"
                  rows="4"
                  placeholder='{"output": "..."}'
                  spellcheck="false"
                />
                <div v-else-if="item.cfg.mode === 'record_replay'" class="rr-grid">
                  <label class="field">
                    <span>lookup_ns <em class="req">*</em></span>
                    <input v-model="item.cfg.lookup_ns" class="inp mono" placeholder="ns_code" />
                  </label>
                  <label class="field">
                    <span>profile_code</span>
                    <input v-model="item.cfg.profile_code" class="inp mono" />
                  </label>
                  <label class="field full">
                    <span>key_expr</span>
                    <input v-model="item.cfg.key_expr" class="inp mono" placeholder="ctx.input.id" />
                  </label>
                  <label class="check">
                    <input v-model="item.cfg.record_on_miss" type="checkbox" />
                    <span>未命中时录制</span>
                  </label>
                </div>
                <div v-else class="rr-grid">
                  <label class="field">
                    <span>fault_type <em class="req">*</em></span>
                    <select v-model="item.cfg.fault_type" class="inp">
                      <option value="timeout">timeout</option>
                      <option value="exception">exception</option>
                      <option value="dirty_data">dirty_data</option>
                    </select>
                  </label>
                  <label class="field full">
                    <span>fault_params (JSON)</span>
                    <textarea v-model="item.faultParamsText" class="ta mono" rows="3" spellcheck="false" />
                  </label>
                </div>
              </div>
              <button type="button" class="btn small ghost" @click="addMockEntry">+ 添加节点 mock</button>
            </div>
          </details>

          <p v-if="formError" class="err">{{ formError }}</p>
          <div class="form-actions">
            <button type="button" class="btn ghost" @click="cancelCreate">取消</button>
            <button type="button" class="btn primary" :disabled="creating" @click="submitBatch">
              {{ creating ? "创建中…" : "创建批次" }}
            </button>
          </div>
        </section>

        <!-- 批次详情 -->
        <section v-else-if="selectedBatch" class="panel">
          <header class="panel-head">
            <div>
              <div class="panel-title">
                <span class="mono">#{{ selectedBatch.id }}</span>
                · {{ selectedBatch.flow_code }} v{{ selectedBatch.ver_no }}
                <span class="tag" :class="batchStatusTag(selectedBatch.status)">{{ selectedBatch.status }}</span>
              </div>
              <div class="muted small">
                test_ns: <span class="mono">{{ selectedBatch.test_ns_code }}</span>
                · profile: <span class="mono">{{ selectedBatch.profile_code }}</span>
                <span v-if="selectedBatch.started_at"> · 开始 {{ formatTs(selectedBatch.started_at) }}</span>
                <span v-if="selectedBatch.finished_at"> · 结束 {{ formatTs(selectedBatch.finished_at) }}</span>
              </div>
            </div>
            <button type="button" class="btn ghost small" @click="refreshSelected">刷新</button>
          </header>

          <div class="progress">
            <div class="progress-info">
              <span><strong>{{ selectedBatch.completed_runs }}</strong> / {{ selectedBatch.total_runs }} 完成</span>
              <span v-if="selectedBatch.error_runs" class="bad">{{ selectedBatch.error_runs }} 失败</span>
              <span v-if="selectedBatch.total_runs > 0" class="muted small">{{ progressPct(selectedBatch) }}%</span>
            </div>
            <div class="progress-bar">
              <div class="progress-fill ok" :style="{ width: `${(selectedBatch.completed_runs - selectedBatch.error_runs) / Math.max(1, selectedBatch.total_runs) * 100}%` }" />
              <div class="progress-fill bad" :style="{ width: `${selectedBatch.error_runs / Math.max(1, selectedBatch.total_runs) * 100}%` }" />
            </div>
          </div>

          <div class="run-toolbar">
            <label class="ctl">
              <span>状态</span>
              <select v-model="runStatusFilter" class="inp" @change="loadBatchRuns">
                <option value="">全部</option>
                <option value="running">running</option>
                <option value="completed">completed</option>
                <option value="failed">failed</option>
                <option value="terminated">terminated</option>
              </select>
            </label>
            <span class="spacer" />
            <span class="muted small">共 {{ runs?.total ?? 0 }} 条</span>
          </div>

          <table class="grid-table">
            <thead>
              <tr>
                <th style="width:80px">run_id</th>
                <th style="width:110px">状态</th>
                <th style="width:160px">started_at</th>
                <th style="width:110px">耗时</th>
                <th>error</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loadingRuns"><td colspan="5" class="muted center">加载中…</td></tr>
              <tr v-else-if="!runs || runs.runs.length === 0">
                <td colspan="5" class="muted center">暂无运行记录</td>
              </tr>
              <tr
                v-for="r in runs?.runs ?? []"
                :key="r.id"
                :class="{ active: selectedRunId === r.id }"
                @click="selectRun(r.id)"
              >
                <td class="mono">#{{ r.id }}</td>
                <td><span class="tag" :class="runStatusTag(r.status)">{{ r.status }}</span></td>
                <td class="mono small">{{ formatTs(r.started_at) }}</td>
                <td class="mono small">{{ runElapsed(r) }}</td>
                <td class="mono small err-cell" :title="r.error || ''">{{ r.error || "—" }}</td>
              </tr>
            </tbody>
          </table>

          <section v-if="selectedRunDetail" class="run-detail-wrap">
            <header class="side-head">
              <span class="side-title">运行详情</span>
              <button type="button" class="btn ghost small" @click="selectedRunId = null">关闭</button>
            </header>
            <RunDetailPanel :detail="selectedRunDetail" />
          </section>
        </section>

        <!-- 空状态 -->
        <section v-else class="panel empty">
          <p class="muted center pad">从左侧选择批次，或点击「新建批次」</p>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, reactive, ref, watch } from "vue";
import {
  createTestBatch,
  getBatchRun,
  getTestBatch,
  listBatchRuns,
  type CreateTestBatchBody,
  type FaultType,
  type MockConfig,
  type MockMode,
  type TestBatchDetail,
} from "@/api/testBatches";
import type { FlowRunDetail, FlowRunSummary, FlowRunsListResponse } from "@/api/flowRuns";
import { fetchFlowList, type FlowListItem } from "@/api/flows";
import { fetchVersionList, type FlowVersionMeta } from "@/api/flowVersions";
import { fetchProfileConfig } from "@/api/profiles";
import { fetchLookupList } from "@/api/lookups";
import RunDetailPanel from "@/components/RunDetailPanel.vue";

type Mode = "list" | "create";
type MockEntry = {
  nodeId: string;
  cfg: MockConfig;
  scriptText: string;
  resultText: string;
  faultParamsText: string;
};

const STORAGE_KEY = "flow_engine.test_center.recent_batches";

function loadRecentIds(): number[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    if (Array.isArray(arr)) return arr.filter((n) => typeof n === "number");
  } catch {
    // ignore
  }
  return [];
}

function saveRecentIds(ids: number[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids.slice(0, 30)));
  } catch {
    // ignore
  }
}

const error = ref("");
const mode = ref<Mode>("list");
const batches = ref<TestBatchDetail[]>([]);
const recentIds = ref<number[]>(loadRecentIds());

const selectedBatchId = ref<number | null>(null);
const selectedBatch = computed<TestBatchDetail | null>(() =>
  batches.value.find((b) => b.id === selectedBatchId.value) ?? null,
);

const openByIdInput = ref<number | null>(null);

// ---------------- form state ----------------

const flowOptions = ref<FlowListItem[]>([]);
const versionOptions = ref<FlowVersionMeta[]>([]);
const profileOptions = ref<string[]>([]);
const lookupNamespaces = ref<string[]>([]);

const form = reactive<{
  flow_code: string;
  ver_no: number;
  test_ns_code: string;
  profile_code: string;
  concurrency: number;
}>({
  flow_code: "",
  ver_no: 0,
  test_ns_code: "",
  profile_code: "default",
  concurrency: 4,
});
const mockEntries = reactive<MockEntry[]>([]);
const creating = ref(false);
const formError = ref("");

function emptyCfg(m: MockMode): MockConfig {
  if (m === "script") return { mode: "script", script: "" };
  if (m === "fixed") return { mode: "fixed", result: {} };
  if (m === "record_replay")
    return { mode: "record_replay", lookup_ns: "", profile_code: "", key_expr: "", record_on_miss: true };
  return { mode: "fault", fault_type: "timeout", fault_params: {} };
}

function newMockEntry(): MockEntry {
  return {
    nodeId: "",
    cfg: emptyCfg("script"),
    scriptText: "",
    resultText: "{}",
    faultParamsText: "{}",
  };
}

function addMockEntry() {
  mockEntries.push(newMockEntry());
}

function removeMockEntry(idx: number) {
  mockEntries.splice(idx, 1);
}

function resetCfg(entry: MockEntry) {
  entry.cfg = emptyCfg(entry.cfg.mode);
  if (entry.cfg.mode === "script") entry.scriptText = "";
  if (entry.cfg.mode === "fixed") entry.resultText = "{}";
  if (entry.cfg.mode === "fault") entry.faultParamsText = "{}";
}

// ---------------- batch runs state ----------------

const runs = ref<FlowRunsListResponse | null>(null);
const loadingRuns = ref(false);
const runStatusFilter = ref("");
const selectedRunId = ref<number | null>(null);
const selectedRunDetail = ref<FlowRunDetail | null>(null);

let pollTimer: ReturnType<typeof setInterval> | null = null;

function startPolling(batchId: number) {
  stopPolling();
  pollTimer = setInterval(async () => {
    try {
      const updated = await getTestBatch(batchId);
      const idx = batches.value.findIndex((b) => b.id === batchId);
      if (idx >= 0) batches.value[idx] = updated;
      else batches.value.unshift(updated);
      if (updated.status !== "running") {
        stopPolling();
      }
      await loadBatchRuns();
    } catch {
      // network blip — keep polling
    }
  }, 3000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

onUnmounted(stopPolling);

// ---------------- actions ----------------

async function refreshBatches() {
  error.value = "";
  const ids = [...recentIds.value];
  const out: TestBatchDetail[] = [];
  const stillExisting: number[] = [];
  for (const id of ids) {
    try {
      const b = await getTestBatch(id);
      out.push(b);
      stillExisting.push(id);
    } catch {
      // batch may have been deleted; drop from recent list
    }
  }
  batches.value = out;
  recentIds.value = stillExisting;
  saveRecentIds(stillExisting);
}

async function openById() {
  if (!openByIdInput.value) return;
  const id = Number(openByIdInput.value);
  try {
    const b = await getTestBatch(id);
    if (!batches.value.some((x) => x.id === id)) {
      batches.value.unshift(b);
      recentIds.value = [id, ...recentIds.value.filter((x) => x !== id)];
      saveRecentIds(recentIds.value);
    }
    selectBatch(id);
    openByIdInput.value = null;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function selectBatch(id: number) {
  selectedBatchId.value = id;
  mode.value = "list";
  selectedRunId.value = null;
  selectedRunDetail.value = null;
  await refreshSelected();
  await loadBatchRuns();
  if (selectedBatch.value?.status === "running") {
    startPolling(id);
  } else {
    stopPolling();
  }
}

async function refreshSelected() {
  if (selectedBatchId.value == null) return;
  try {
    const updated = await getTestBatch(selectedBatchId.value);
    const idx = batches.value.findIndex((b) => b.id === updated.id);
    if (idx >= 0) batches.value[idx] = updated;
    else batches.value.unshift(updated);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function loadBatchRuns() {
  if (selectedBatchId.value == null) return;
  loadingRuns.value = true;
  try {
    runs.value = await listBatchRuns(selectedBatchId.value, {
      status: runStatusFilter.value || undefined,
      offset: 0,
      limit: 100,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingRuns.value = false;
  }
}

async function selectRun(runId: number) {
  if (selectedBatchId.value == null) return;
  selectedRunId.value = runId;
  try {
    selectedRunDetail.value = await getBatchRun(selectedBatchId.value, runId);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function newBatch() {
  mode.value = "create";
  selectedBatchId.value = null;
  stopPolling();
  formError.value = "";
  if (flowOptions.value.length === 0) {
    try {
      const r = await fetchFlowList();
      flowOptions.value = r.flows;
    } catch (e) {
      formError.value = e instanceof Error ? e.message : String(e);
    }
  }
  if (profileOptions.value.length === 0) {
    try {
      const r = await fetchProfileConfig();
      profileOptions.value = r.profiles.length ? r.profiles : ["default"];
      form.profile_code = r.default_profile || profileOptions.value[0] || "default";
    } catch {
      profileOptions.value = ["default"];
    }
  }
  if (lookupNamespaces.value.length === 0) {
    try {
      const r = await fetchLookupList();
      lookupNamespaces.value = r.namespaces;
    } catch {
      // best effort
    }
  }
}

function cancelCreate() {
  mode.value = "list";
}

async function onFlowChange() {
  versionOptions.value = [];
  form.ver_no = 0;
  if (!form.flow_code) return;
  try {
    const r = await fetchVersionList(form.flow_code);
    versionOptions.value = r.versions;
    if (r.versions.length > 0) form.ver_no = r.versions[0].version;
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
  }
}

function buildMockConfig(): { ok: true; data: Record<string, MockConfig> } | { ok: false; err: string } {
  const out: Record<string, MockConfig> = {};
  for (const item of mockEntries) {
    const nid = item.nodeId.trim();
    if (!nid) return { ok: false, err: "mock 配置必须填写 node_id" };
    const cfg = { ...item.cfg };
    if (cfg.mode === "script") {
      cfg.script = item.scriptText;
      if (!cfg.script) return { ok: false, err: `node ${nid}: script 模式必须填写脚本` };
    } else if (cfg.mode === "fixed") {
      try {
        cfg.result = JSON.parse(item.resultText || "null");
      } catch (e) {
        return { ok: false, err: `node ${nid}: result JSON 解析失败 — ${e instanceof Error ? e.message : String(e)}` };
      }
      if (cfg.result === null || cfg.result === undefined) {
        return { ok: false, err: `node ${nid}: fixed 模式必须提供 result` };
      }
    } else if (cfg.mode === "record_replay") {
      if (!cfg.lookup_ns) return { ok: false, err: `node ${nid}: record_replay 需要 lookup_ns` };
    } else if (cfg.mode === "fault") {
      try {
        cfg.fault_params = JSON.parse(item.faultParamsText || "{}");
      } catch (e) {
        return { ok: false, err: `node ${nid}: fault_params JSON 解析失败 — ${e instanceof Error ? e.message : String(e)}` };
      }
      if (!cfg.fault_type) return { ok: false, err: `node ${nid}: fault 模式必须选择 fault_type` };
      cfg.fault_type = cfg.fault_type as FaultType;
    }
    out[nid] = cfg;
  }
  return { ok: true, data: out };
}

async function submitBatch() {
  formError.value = "";
  if (!form.flow_code) {
    formError.value = "请选择 flow_code";
    return;
  }
  if (!form.ver_no) {
    formError.value = "请选择 ver_no";
    return;
  }
  if (!form.test_ns_code) {
    formError.value = "请选择 test_ns_code";
    return;
  }
  if (!form.profile_code) {
    formError.value = "请选择 profile_code";
    return;
  }
  const mockResult = buildMockConfig();
  if (!mockResult.ok) {
    formError.value = mockResult.err;
    return;
  }
  const body: CreateTestBatchBody = {
    flow_code: form.flow_code,
    ver_no: form.ver_no,
    test_ns_code: form.test_ns_code,
    profile_code: form.profile_code,
    concurrency: form.concurrency,
    mock_config: mockResult.data,
  };
  creating.value = true;
  try {
    const res = await createTestBatch(body);
    recentIds.value = [res.batch_id, ...recentIds.value.filter((x) => x !== res.batch_id)];
    saveRecentIds(recentIds.value);
    await refreshBatches();
    await selectBatch(res.batch_id);
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
  } finally {
    creating.value = false;
  }
}

// ---------------- helpers ----------------

function batchStatusTag(status: string): string {
  if (status === "running") return "running";
  if (status === "completed") return "ok";
  if (status === "failed") return "bad";
  return "info";
}

function runStatusTag(status: string): string {
  if (status === "running") return "running";
  if (status === "completed") return "ok";
  if (status === "failed") return "bad";
  if (status === "terminated") return "warn";
  return "info";
}

function formatTs(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function progressPct(b: TestBatchDetail): number {
  if (b.total_runs <= 0) return 0;
  return Math.round((b.completed_runs / b.total_runs) * 100);
}

function runElapsed(r: FlowRunSummary): string {
  if (!r.started_at) return "—";
  const start = Date.parse(r.started_at);
  if (Number.isNaN(start)) return "—";
  const end = r.finished_at ? Date.parse(r.finished_at) : Date.now();
  if (Number.isNaN(end)) return "—";
  const diff = end - start;
  if (diff < 0) return "—";
  if (diff < 1000) return `${diff}ms`;
  if (diff < 60_000) return `${(diff / 1000).toFixed(2)}s`;
  return `${(diff / 60_000).toFixed(1)}min`;
}

watch(
  () => selectedBatch.value?.status,
  (s) => {
    if (s === "running" && selectedBatchId.value != null) startPolling(selectedBatchId.value);
    else stopPolling();
  },
);

void refreshBatches();
</script>

<style scoped>
.test-page {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}

.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}

.title {
  font-size: 16px;
  font-weight: 700;
}

.subtitle {
  font-size: 12px;
  color: var(--muted);
}

.head-actions {
  display: flex;
  gap: 8px;
}

.err {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, #fecaca 30%, transparent);
  color: #b91c1c;
  font-size: 12px;
}

.layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 12px;
}

.sidebar {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: auto;
}

.side-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.side-title {
  font-weight: 700;
  font-size: 12px;
}

.open-by-id {
  display: flex;
  gap: 6px;
}

.batch-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.batch-list li {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  background: #fbfdff;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.batch-list li:hover {
  background: color-mix(in srgb, var(--accent-soft) 60%, transparent);
}

.batch-list li.active {
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
}

.batch-row1 {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}

.batch-id {
  font-weight: 700;
}

.batch-row2 {
  font-size: 11px;
  color: var(--text);
}

.batch-row3 {
  display: flex;
  gap: 6px;
}

.main {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: auto;
}

.panel {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel.empty {
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.panel-title {
  font-weight: 700;
  font-size: 13px;
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: var(--muted);
}

.field.full {
  grid-column: 1 / -1;
}

.req {
  color: #e11d48;
  font-style: normal;
  margin-left: 2px;
}

.inp {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 9px;
  background: #fff;
  font-size: 12px;
}

.btn {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}

.btn.small {
  padding: 4px 8px;
  font-size: 11px;
}

.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
}

.btn.danger {
  background: color-mix(in srgb, #ef4444 12%, transparent);
  color: #b91c1c;
  border-color: color-mix(in srgb, #ef4444 30%, transparent);
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.advanced {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  background: #fbfdff;
}

.advanced summary {
  cursor: pointer;
  font-weight: 600;
  font-size: 12px;
}

.mock-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.mock-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  background: #fff;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mock-card-head {
  display: flex;
  gap: 6px;
  align-items: center;
}

.ta {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  font-size: 11px;
  resize: vertical;
}

.rr-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.progress {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  background: #fbfdff;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-info {
  display: flex;
  gap: 12px;
  align-items: baseline;
  font-size: 12px;
}

.progress-bar {
  display: flex;
  height: 8px;
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
}

.progress-fill {
  transition: width 0.3s ease;
}

.progress-fill.ok {
  background: linear-gradient(180deg, #34d399, #10b981);
}

.progress-fill.bad {
  background: linear-gradient(180deg, #f87171, #ef4444);
}

.run-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.spacer { flex: 1; }

.ctl {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: var(--muted);
}

.grid-table {
  width: 100%;
  border-collapse: collapse;
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  background: var(--surface);
}

.grid-table th,
.grid-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  font-size: 12px;
  vertical-align: middle;
}

.grid-table th {
  background: #fbfdff;
  color: var(--muted);
  font-weight: 600;
  font-size: 11px;
}

.grid-table tbody tr {
  cursor: pointer;
}

.grid-table tbody tr:hover {
  background: color-mix(in srgb, var(--accent-soft) 50%, transparent);
}

.grid-table tbody tr.active {
  background: var(--accent-soft);
}

.grid-table tbody tr:last-child td {
  border-bottom: none;
}

.tag {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.tag.ok { background: color-mix(in srgb, #10b981 14%, transparent); color: #047857; border-color: color-mix(in srgb, #10b981 35%, transparent); }
.tag.bad { background: color-mix(in srgb, #ef4444 14%, transparent); color: #b91c1c; border-color: color-mix(in srgb, #ef4444 35%, transparent); }
.tag.warn { background: color-mix(in srgb, #f59e0b 18%, transparent); color: #92400e; border-color: color-mix(in srgb, #f59e0b 35%, transparent); }
.tag.running { background: color-mix(in srgb, #3b82f6 14%, transparent); color: #1d4ed8; border-color: color-mix(in srgb, #3b82f6 35%, transparent); }

.muted {
  color: var(--muted);
}

.bad {
  color: #b91c1c;
}

.center {
  text-align: center;
}

.small {
  font-size: 11px;
}

.pad {
  padding: 16px 12px;
  margin: 0;
}

.err-cell {
  color: #b91c1c;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-detail-wrap {
  border-top: 1px dashed var(--border);
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mono {
  font-family: var(--mono);
}
</style>
