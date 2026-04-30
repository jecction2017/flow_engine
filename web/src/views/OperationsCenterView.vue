<template>
  <div class="ops-page">
    <header class="top">
      <div>
        <div class="title">运行中心</div>
        <div class="subtitle">部署管理 · 运行历史 · 工作节点状态</div>
      </div>
      <button type="button" class="btn ghost" @click="reloadActive">刷新</button>
    </header>

    <nav class="tabs" role="tablist">
      <button
        v-for="t in TABS"
        :key="t.id"
        role="tab"
        :aria-selected="tab === t.id"
        :class="['tab', { active: tab === t.id }]"
        type="button"
        @click="switchTab(t.id)"
      >
        {{ t.label }}
      </button>
    </nav>

    <p v-if="error" class="err">{{ error }}</p>

    <!-- ===================== 部署管理 ===================== -->
    <section v-if="tab === 'deployments'" class="tab-body">
      <div class="toolbar">
        <label class="ctl">
          <span>flow_code</span>
          <input v-model="depFilters.flow_code" class="inp mono" placeholder="（全部）" />
        </label>
        <label class="ctl">
          <span>状态</span>
          <select v-model="depFilters.status" class="inp">
            <option value="">全部</option>
            <option value="pending">pending</option>
            <option value="running">running</option>
            <option value="stopping">stopping</option>
            <option value="stopped">stopped</option>
            <option value="failed">failed</option>
          </select>
        </label>
        <label class="ctl">
          <span>模式</span>
          <select v-model="depFilters.mode" class="inp">
            <option value="">全部</option>
            <option value="debug">debug</option>
            <option value="shadow">shadow</option>
            <option value="production">production</option>
          </select>
        </label>
        <button type="button" class="btn ghost" :disabled="loadingDep" @click="loadDeployments">查询</button>
        <span class="spacer" />
        <button type="button" class="btn primary" @click="openCreateForm">+ 新建部署</button>
      </div>

      <table class="grid-table">
        <thead>
          <tr>
            <th style="width:60px">ID</th>
            <th>flow / version</th>
            <th style="width:90px">mode</th>
            <th style="width:90px">schedule</th>
            <th style="width:110px">状态</th>
            <th>profile</th>
            <th style="width:160px">created_at</th>
            <th style="width:240px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loadingDep">
            <td colspan="8" class="muted center">加载中…</td>
          </tr>
          <tr v-else-if="deployments.length === 0">
            <td colspan="8" class="muted center">暂无部署</td>
          </tr>
          <tr
            v-for="d in deployments"
            :key="d.id"
            :class="{ active: selectedDeploymentId === d.id }"
            @click="selectDeployment(d.id)"
          >
            <td class="mono">#{{ d.id }}</td>
            <td>
              <div class="mono">{{ d.flow_code }}</div>
              <div class="muted">v{{ d.ver_no }}</div>
            </td>
            <td><span class="tag mode">{{ d.mode }}</span></td>
            <td>
              <span class="tag">{{ d.schedule_type }}</span>
              <span v-if="d.schedule_type === 'cron' && d.schedule_config?.cron_expr" class="muted mono">
                {{ d.schedule_config.cron_expr }}
              </span>
            </td>
            <td><span class="tag" :class="statusTag(d.status)">{{ d.status }}</span></td>
            <td class="mono">{{ d.env_profile_code || "—" }}</td>
            <td class="mono small">{{ formatTs(d.created_at) }}</td>
            <td class="row-actions" @click.stop>
              <button
                v-if="d.status === 'running'"
                type="button"
                class="btn small warn"
                @click="patchStatus(d.id, 'stopping')"
              >停止</button>
              <button
                v-else-if="d.status === 'stopping' || d.status === 'stopped' || d.status === 'failed'"
                type="button"
                class="btn small"
                @click="patchStatus(d.id, 'pending')"
              >重启</button>
              <button type="button" class="btn small ghost" @click="viewRuns(d)">运行记录</button>
              <button type="button" class="btn small danger" @click="removeDeployment(d.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 部署详情侧栏 -->
      <aside v-if="selectedDeployment" class="side-panel">
        <header class="side-head">
          <div>
            <div class="side-title mono">#{{ selectedDeployment.id }} · {{ selectedDeployment.flow_code }}</div>
            <div class="muted">v{{ selectedDeployment.ver_no }} · {{ selectedDeployment.mode }} · {{ selectedDeployment.schedule_type }}</div>
          </div>
          <button type="button" class="btn ghost small" @click="selectedDeploymentId = null">关闭</button>
        </header>
        <div class="side-section">
          <div class="lbl">分配的 Worker</div>
          <ul v-if="selectedDeployment.assignments?.length" class="assn-list">
            <li v-for="a in selectedDeployment.assignments" :key="a.id">
              <span class="mono">{{ a.worker_id }}</span>
              <span class="tag small">{{ a.role }}</span>
              <span v-if="a.lease_expires_at" class="muted small">lease: {{ formatTs(a.lease_expires_at) }}</span>
            </li>
          </ul>
          <div v-else class="muted small pad">尚未分配 worker</div>
        </div>
        <div class="side-section">
          <div class="lbl">配置</div>
          <pre class="cfg mono">{{ deploymentCfgText(selectedDeployment) }}</pre>
        </div>
      </aside>

      <!-- 新建部署面板 -->
      <aside v-if="creatingDeployment" class="side-panel form-panel">
        <header class="side-head">
          <div class="side-title">新建部署</div>
          <button type="button" class="btn ghost small" @click="creatingDeployment = false">取消</button>
        </header>
        <div class="form-grid">
          <label class="field">
            <span>flow_code <em class="req">*</em></span>
            <select v-model="form.flow_code" class="inp" @change="onFlowChange">
              <option value="">选择流程</option>
              <option v-for="f in flowOptions" :key="f.id" :value="f.id">{{ f.id }}{{ f.display_name ? ` · ${f.display_name}` : "" }}</option>
            </select>
          </label>
          <label class="field">
            <span>ver_no <em class="req">*</em></span>
            <select v-model.number="form.ver_no" class="inp" :disabled="!form.flow_code">
              <option :value="0">选择版本</option>
              <option v-for="v in versionOptions" :key="v.version" :value="v.version">v{{ v.version }}{{ v.description ? ` · ${v.description}` : "" }}</option>
            </select>
          </label>
          <label class="field">
            <span>mode <em class="req">*</em></span>
            <select v-model="form.mode" class="inp">
              <option value="debug">debug</option>
              <option value="shadow">shadow</option>
              <option value="production">production</option>
            </select>
          </label>
          <label class="field">
            <span>schedule_type <em class="req">*</em></span>
            <select v-model="form.schedule_type" class="inp">
              <option value="once">once</option>
              <option value="cron">cron</option>
              <option value="resident">resident</option>
            </select>
          </label>
          <label v-if="form.schedule_type === 'cron'" class="field">
            <span>cron_expr <em class="req">*</em></span>
            <input v-model="form.cron_expr" class="inp mono" placeholder="0 */5 * * *" />
          </label>
          <label class="field">
            <span>env_profile_code</span>
            <select v-model="form.env_profile_code" class="inp">
              <option value="">（默认）</option>
              <option v-for="p in profileOptions" :key="p" :value="p">{{ p }}</option>
            </select>
          </label>
        </div>
        <details class="advanced">
          <summary>worker_policy（高级）</summary>
          <textarea v-model="workerPolicyText" rows="6" class="ta mono" spellcheck="false" />
        </details>
        <details class="advanced">
          <summary>capability_policy（高级）</summary>
          <textarea v-model="capabilityPolicyText" rows="6" class="ta mono" spellcheck="false" placeholder="[\n  { &quot;builtin_category&quot;: &quot;io&quot;, &quot;action&quot;: &quot;suppress&quot; }\n]" />
        </details>
        <p v-if="formError" class="err">{{ formError }}</p>
        <div class="form-actions">
          <button type="button" class="btn primary" :disabled="creating" @click="submitDeployment">
            {{ creating ? "创建中…" : "创建并入队" }}
          </button>
        </div>
      </aside>
    </section>

    <!-- ===================== 运行历史 ===================== -->
    <section v-if="tab === 'runs'" class="tab-body">
      <div class="toolbar">
        <label class="ctl">
          <span>deployment_id</span>
          <input v-model="runFilters.deployment_id" type="number" class="inp mono" placeholder="（全部）" />
        </label>
        <label class="ctl">
          <span>flow_code</span>
          <input v-model="runFilters.flow_code" class="inp mono" placeholder="（全部）" />
        </label>
        <label class="ctl">
          <span>mode</span>
          <select v-model="runFilters.mode" class="inp">
            <option value="">全部</option>
            <option value="debug">debug</option>
            <option value="shadow">shadow</option>
            <option value="production">production</option>
          </select>
        </label>
        <label class="ctl">
          <span>状态</span>
          <select v-model="runFilters.status" class="inp">
            <option value="">全部</option>
            <option value="running">running</option>
            <option value="completed">completed</option>
            <option value="failed">failed</option>
            <option value="terminated">terminated</option>
          </select>
        </label>
        <button type="button" class="btn ghost" :disabled="loadingRuns" @click="loadRuns">查询</button>
        <span class="spacer" />
        <span class="muted small">共 {{ runsResp?.total ?? 0 }} 条 · 第 {{ Math.floor((runsResp?.offset ?? 0) / runPageSize) + 1 }} 页</span>
        <button type="button" class="btn small ghost" :disabled="(runsResp?.offset ?? 0) === 0" @click="prevPage">上一页</button>
        <button type="button" class="btn small ghost" :disabled="!hasNextPage" @click="nextPage">下一页</button>
      </div>

      <table class="grid-table">
        <thead>
          <tr>
            <th style="width:80px">run_id</th>
            <th>flow</th>
            <th style="width:80px">mode</th>
            <th style="width:110px">状态</th>
            <th style="width:160px">started_at</th>
            <th style="width:120px">耗时</th>
            <th>worker</th>
            <th style="width:100px">deployment</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loadingRuns"><td colspan="8" class="muted center">加载中…</td></tr>
          <tr v-else-if="!runsResp || runsResp.runs.length === 0">
            <td colspan="8" class="muted center">暂无运行记录</td>
          </tr>
          <tr
            v-for="r in runsResp?.runs ?? []"
            :key="r.id"
            :class="{ active: selectedRunId === r.id }"
            @click="selectRun(r.id)"
          >
            <td class="mono">#{{ r.id }}</td>
            <td>
              <div class="mono">{{ r.flow_code }}</div>
              <div class="muted small">v{{ r.ver_no }}</div>
            </td>
            <td><span class="tag mode">{{ r.mode }}</span></td>
            <td><span class="tag" :class="runStatusTag(r.status)">{{ r.status }}</span></td>
            <td class="mono small">{{ formatTs(r.started_at) }}</td>
            <td class="mono small">{{ runElapsed(r) }}</td>
            <td class="mono small">{{ r.worker_id ?? "—" }}</td>
            <td class="mono small">{{ r.deployment_id ? `#${r.deployment_id}` : "—" }}</td>
          </tr>
        </tbody>
      </table>

      <aside v-if="selectedRunDetail" class="side-panel wide">
        <header class="side-head">
          <div class="side-title">运行详情</div>
          <button type="button" class="btn ghost small" @click="selectedRunId = null">关闭</button>
        </header>
        <RunDetailPanel :detail="selectedRunDetail" />
      </aside>
      <p v-else-if="loadingRunDetail" class="muted small pad">加载中…</p>
    </section>

    <!-- ===================== 工作节点 ===================== -->
    <section v-if="tab === 'workers'" class="tab-body">
      <div class="toolbar">
        <span class="muted small">共 {{ workers.length }} 个 worker</span>
        <span class="spacer" />
        <button type="button" class="btn ghost" :disabled="loadingWorkers" @click="loadWorkers">刷新</button>
      </div>
      <div class="worker-grid">
        <article v-for="w in workers" :key="w.worker_id" class="worker-card" :class="workerStatusClass(w.status)">
          <header class="worker-head">
            <span class="worker-id mono">{{ w.worker_id }}</span>
            <span class="tag" :class="workerStatusClass(w.status)">{{ w.status }}</span>
          </header>
          <dl class="worker-meta">
            <div><dt>host</dt><dd class="mono">{{ w.host || "—" }}</dd></div>
            <div><dt>pid</dt><dd class="mono">{{ w.pid ?? "—" }}</dd></div>
            <div><dt>last_heartbeat</dt><dd class="mono small">{{ formatRelative(w.last_heartbeat) }}</dd></div>
            <div><dt>分配部署</dt><dd>{{ w.assigned_deployments.length }}</dd></div>
          </dl>
          <div v-if="w.assigned_deployments.length" class="worker-deps">
            <span v-for="id in w.assigned_deployments" :key="id" class="dep-chip">#{{ id }}</span>
          </div>
        </article>
        <p v-if="!loadingWorkers && workers.length === 0" class="muted center pad">暂无 worker（启动 ``flow-worker start`` 后自动注册）</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import {
  createDeployment,
  deleteDeployment,
  getDeployment,
  listDeployments,
  patchDeployment,
  type CapabilityRule,
  type CreateDeploymentBody,
  type Deployment,
  type DeploymentDetail,
  type RunMode,
  type ScheduleType,
  type WorkerPolicy,
} from "@/api/deployments";
import { listWorkers, type Worker } from "@/api/workers";
import {
  getFlowRun,
  listFlowRuns,
  type FlowRunDetail,
  type FlowRunSummary,
  type FlowRunsListResponse,
} from "@/api/flowRuns";
import { fetchFlowList, type FlowListItem } from "@/api/flows";
import { fetchVersionList, type FlowVersionMeta } from "@/api/flowVersions";
import { fetchProfiles } from "@/api/profiles";
import RunDetailPanel from "@/components/RunDetailPanel.vue";

type TabId = "deployments" | "runs" | "workers";

const TABS: { id: TabId; label: string }[] = [
  { id: "deployments", label: "部署管理" },
  { id: "runs", label: "运行历史" },
  { id: "workers", label: "工作节点" },
];

const tab = ref<TabId>("deployments");
const error = ref("");

// ---------------- Deployments ----------------

const deployments = ref<Deployment[]>([]);
const loadingDep = ref(false);
const depFilters = reactive<{ flow_code: string; status: string; mode: string }>({
  flow_code: "",
  status: "",
  mode: "",
});
const selectedDeploymentId = ref<number | null>(null);
const selectedDeployment = ref<DeploymentDetail | null>(null);

const creatingDeployment = ref(false);
const creating = ref(false);
const formError = ref("");
const flowOptions = ref<FlowListItem[]>([]);
const versionOptions = ref<FlowVersionMeta[]>([]);
const profileOptions = ref<string[]>([]);

const DEFAULT_WORKER_POLICY: WorkerPolicy = {
  type: "single_active",
  min_workers: 1,
  max_restarts: 5,
  restart_backoff_s: 30,
};

const form = reactive<{
  flow_code: string;
  ver_no: number;
  mode: RunMode;
  schedule_type: ScheduleType;
  cron_expr: string;
  env_profile_code: string;
}>({
  flow_code: "",
  ver_no: 0,
  mode: "production",
  schedule_type: "once",
  cron_expr: "",
  env_profile_code: "",
});
const workerPolicyText = ref(JSON.stringify(DEFAULT_WORKER_POLICY, null, 2));
const capabilityPolicyText = ref("[]");

async function loadDeployments() {
  loadingDep.value = true;
  error.value = "";
  try {
    const res = await listDeployments({
      flow_code: depFilters.flow_code.trim() || undefined,
      status: depFilters.status || undefined,
      mode: depFilters.mode || undefined,
    });
    deployments.value = res.deployments;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingDep.value = false;
  }
}

async function selectDeployment(id: number) {
  selectedDeploymentId.value = id;
  try {
    selectedDeployment.value = await getDeployment(id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function patchStatus(id: number, status: "stopping" | "pending") {
  try {
    await patchDeployment(id, status);
    await loadDeployments();
    if (selectedDeploymentId.value === id) {
      await selectDeployment(id);
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function removeDeployment(id: number) {
  if (!confirm(`确认删除部署 #${id}（软删除）？`)) return;
  try {
    await deleteDeployment(id);
    if (selectedDeploymentId.value === id) {
      selectedDeploymentId.value = null;
      selectedDeployment.value = null;
    }
    await loadDeployments();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

function viewRuns(d: Deployment) {
  runFilters.deployment_id = d.id;
  runFilters.flow_code = "";
  runFilters.mode = "";
  runFilters.status = "";
  switchTab("runs");
}

async function openCreateForm() {
  creatingDeployment.value = true;
  formError.value = "";
  if (flowOptions.value.length === 0) {
    try {
      const res = await fetchFlowList();
      flowOptions.value = res.flows;
    } catch (e) {
      formError.value = e instanceof Error ? e.message : String(e);
    }
  }
  if (profileOptions.value.length === 0) {
    try {
      const res = await fetchProfiles();
      profileOptions.value = res.profiles;
    } catch {
      // best effort
    }
  }
}

async function onFlowChange() {
  versionOptions.value = [];
  form.ver_no = 0;
  if (!form.flow_code) return;
  try {
    const res = await fetchVersionList(form.flow_code);
    versionOptions.value = res.versions;
    if (res.versions.length > 0) {
      form.ver_no = res.versions[0].version;
    }
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
  }
}

async function submitDeployment() {
  formError.value = "";
  if (!form.flow_code) {
    formError.value = "请选择 flow_code";
    return;
  }
  if (!form.ver_no) {
    formError.value = "请选择 ver_no";
    return;
  }
  if (form.schedule_type === "cron" && !form.cron_expr.trim()) {
    formError.value = "cron 调度必须指定 cron_expr";
    return;
  }

  let workerPolicy: WorkerPolicy;
  try {
    const parsed = JSON.parse(workerPolicyText.value);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new Error("worker_policy 必须是 JSON 对象");
    }
    workerPolicy = parsed as WorkerPolicy;
  } catch (e) {
    formError.value = `worker_policy 解析失败: ${e instanceof Error ? e.message : String(e)}`;
    return;
  }

  let capabilityPolicy: CapabilityRule[];
  try {
    const parsed = JSON.parse(capabilityPolicyText.value || "[]");
    if (!Array.isArray(parsed)) throw new Error("capability_policy 必须是 JSON 数组");
    capabilityPolicy = parsed as CapabilityRule[];
  } catch (e) {
    formError.value = `capability_policy 解析失败: ${e instanceof Error ? e.message : String(e)}`;
    return;
  }

  const body: CreateDeploymentBody = {
    flow_code: form.flow_code,
    ver_no: form.ver_no,
    mode: form.mode,
    schedule_type: form.schedule_type,
    schedule_config: form.schedule_type === "cron" ? { cron_expr: form.cron_expr.trim() } : {},
    worker_policy: workerPolicy,
    capability_policy: capabilityPolicy,
    env_profile_code: form.env_profile_code,
  };

  creating.value = true;
  try {
    const created = await createDeployment(body);
    creatingDeployment.value = false;
    await loadDeployments();
    selectDeployment(created.id);
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
  } finally {
    creating.value = false;
  }
}

function deploymentCfgText(d: DeploymentDetail): string {
  return JSON.stringify(
    {
      schedule_config: d.schedule_config,
      worker_policy: d.worker_policy,
      capability_policy: d.capability_policy,
    },
    null,
    2,
  );
}

// ---------------- Flow runs ----------------

const runFilters = reactive<{
  deployment_id: number | null;
  flow_code: string;
  mode: string;
  status: string;
}>({
  deployment_id: null,
  flow_code: "",
  mode: "",
  status: "",
});
const runPageSize = 50;
const runOffset = ref(0);
const loadingRuns = ref(false);
const runsResp = ref<FlowRunsListResponse | null>(null);
const selectedRunId = ref<number | null>(null);
const selectedRunDetail = ref<FlowRunDetail | null>(null);
const loadingRunDetail = ref(false);

const hasNextPage = computed(() => {
  if (!runsResp.value) return false;
  return runsResp.value.offset + runsResp.value.runs.length < runsResp.value.total;
});

async function loadRuns() {
  loadingRuns.value = true;
  error.value = "";
  try {
    runsResp.value = await listFlowRuns({
      deployment_id: runFilters.deployment_id != null && Number(runFilters.deployment_id) > 0
        ? Number(runFilters.deployment_id)
        : undefined,
      flow_code: runFilters.flow_code.trim() || undefined,
      mode: runFilters.mode || undefined,
      status: runFilters.status || undefined,
      offset: runOffset.value,
      limit: runPageSize,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingRuns.value = false;
  }
}

function prevPage() {
  runOffset.value = Math.max(0, runOffset.value - runPageSize);
  loadRuns();
}

function nextPage() {
  if (!hasNextPage.value) return;
  runOffset.value += runPageSize;
  loadRuns();
}

async function selectRun(id: number) {
  selectedRunId.value = id;
  loadingRunDetail.value = true;
  try {
    selectedRunDetail.value = await getFlowRun(id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingRunDetail.value = false;
  }
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
  if (diff < 3600_000) return `${(diff / 60_000).toFixed(1)}min`;
  return `${(diff / 3600_000).toFixed(1)}h`;
}

watch(
  () => runFilters.deployment_id,
  () => {
    runOffset.value = 0;
  },
);

// ---------------- Workers ----------------

const workers = ref<Worker[]>([]);
const loadingWorkers = ref(false);

async function loadWorkers() {
  loadingWorkers.value = true;
  error.value = "";
  try {
    const res = await listWorkers();
    workers.value = res.workers;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingWorkers.value = false;
  }
}

// ---------------- Helpers ----------------

function switchTab(id: TabId) {
  tab.value = id;
  if (id === "deployments" && deployments.value.length === 0) loadDeployments();
  if (id === "runs") loadRuns();
  if (id === "workers" && workers.value.length === 0) loadWorkers();
}

function reloadActive() {
  if (tab.value === "deployments") loadDeployments();
  else if (tab.value === "runs") loadRuns();
  else loadWorkers();
}

function statusTag(status: string): string {
  if (status === "running") return "running";
  if (status === "completed" || status === "stopped") return "ok";
  if (status === "failed") return "bad";
  if (status === "stopping") return "warn";
  return "info";
}

function runStatusTag(status: string): string {
  if (status === "running") return "running";
  if (status === "completed") return "ok";
  if (status === "failed") return "bad";
  if (status === "terminated") return "warn";
  return "info";
}

function workerStatusClass(status: string): string {
  if (status === "active") return "ok";
  if (status === "dead") return "bad";
  if (status === "idle") return "warn";
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

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const diff = Date.now() - t;
  if (diff < 0) return formatTs(iso);
  if (diff < 60_000) return `${Math.round(diff / 1000)}s 前`;
  if (diff < 3600_000) return `${Math.round(diff / 60_000)}min 前`;
  if (diff < 86400_000) return `${Math.round(diff / 3600_000)}h 前`;
  return formatTs(iso);
}

void loadDeployments();
</script>

<style scoped>
.ops-page {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
  overflow: auto;
}

.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  font-size: 16px;
  font-weight: 700;
}

.subtitle {
  font-size: 12px;
  color: var(--muted);
}

.tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border);
}

.tab {
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 6px 14px;
  font-size: 12px;
  color: var(--muted);
  cursor: pointer;
}

.tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  font-weight: 700;
}

.tab-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.spacer {
  flex: 1;
}

.ctl {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: var(--muted);
}

.inp {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 9px;
  background: #fff;
  font-size: 12px;
  min-width: 140px;
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

.btn.small {
  padding: 4px 8px;
  font-size: 11px;
}

.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
}

.btn.warn {
  background: color-mix(in srgb, #f59e0b 18%, transparent);
  color: #92400e;
  border-color: color-mix(in srgb, #f59e0b 35%, transparent);
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

.err {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, #fecaca 30%, transparent);
  color: #b91c1c;
  font-size: 12px;
}

.grid-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
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

.muted {
  color: var(--muted);
}

.center {
  text-align: center;
}

.small {
  font-size: 11px;
}

.row-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
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

.tag.small {
  font-size: 9px;
}

.tag.mode {
  background: color-mix(in srgb, #6366f1 12%, transparent);
  color: #4338ca;
  border-color: color-mix(in srgb, #6366f1 30%, transparent);
}

.tag.ok {
  background: color-mix(in srgb, #10b981 14%, transparent);
  color: #047857;
  border-color: color-mix(in srgb, #10b981 35%, transparent);
}

.tag.bad {
  background: color-mix(in srgb, #ef4444 14%, transparent);
  color: #b91c1c;
  border-color: color-mix(in srgb, #ef4444 35%, transparent);
}

.tag.warn {
  background: color-mix(in srgb, #f59e0b 18%, transparent);
  color: #92400e;
  border-color: color-mix(in srgb, #f59e0b 35%, transparent);
}

.tag.running {
  background: color-mix(in srgb, #3b82f6 14%, transparent);
  color: #1d4ed8;
  border-color: color-mix(in srgb, #3b82f6 35%, transparent);
}

.side-panel {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.side-panel.wide {
  padding: 12px;
}

.side-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.side-title {
  font-weight: 700;
  font-size: 13px;
}

.side-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lbl {
  font-size: 11px;
  color: var(--muted);
  font-weight: 600;
}

.assn-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.assn-list li {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfdff;
  font-size: 11px;
  flex-wrap: wrap;
}

.cfg {
  margin: 0;
  padding: 10px;
  border-radius: 8px;
  background: #0b1220;
  color: #e2e8f0;
  font-size: 11px;
  line-height: 1.4;
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.form-panel {
  max-width: 720px;
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

.req {
  color: #e11d48;
  font-style: normal;
  margin-left: 2px;
}

.advanced {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  background: #fbfdff;
}

.advanced summary {
  font-size: 12px;
  cursor: pointer;
  font-weight: 600;
  color: var(--text);
}

.ta {
  width: 100%;
  margin-top: 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  font-size: 11px;
  background: #fff;
  resize: vertical;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
}

.worker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.worker-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.worker-card.ok { border-left: 4px solid #10b981; }
.worker-card.bad { border-left: 4px solid #ef4444; }
.worker-card.warn { border-left: 4px solid #f59e0b; }
.worker-card.info { border-left: 4px solid #94a3b8; }

.worker-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.worker-id {
  font-weight: 700;
  font-size: 12px;
}

.worker-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 10px;
  margin: 0;
  font-size: 11px;
}

.worker-meta dt {
  color: var(--muted);
  font-weight: 500;
  margin: 0;
}

.worker-meta dd {
  margin: 0;
  font-weight: 600;
}

.worker-deps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.dep-chip {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}

.pad {
  padding: 12px;
}

.mono {
  font-family: var(--mono);
}
</style>
