<template>
  <section class="dep-create-panel">
    <header class="panel-head">
      <div class="panel-head-text">
        <div class="panel-title">{{ isEditMode ? `编辑部署 #${editDeploymentId}` : "新建部署" }}</div>
        <div class="muted small">
          <template v-if="isEditMode">
            保存后仍为当前状态；修改调度或节点策略后请在详情页重新启动
          </template>
          <template v-else>填写配置后保存；启动请在部署详情页操作</template>
        </div>
      </div>
      <div class="panel-head-actions">
        <button type="button" class="btn ghost" @click="emit('cancel')">取消</button>
        <button type="button" class="btn primary" :disabled="submitting || formLocked" @click="submit">
          {{ submitting ? "保存中…" : "保存" }}
        </button>
      </div>
    </header>

    <div v-if="formLocked && lockReason" class="dep-lock-banner">
      <p>{{ lockReason }}</p>
      <button
        v-if="editDeployment?.status === 'running'"
        type="button"
        class="btn small warn"
        @click="emit('request-stop')"
      >停止部署</button>
    </div>

    <div class="dep-create-columns" :class="{ 'dep-create-columns--locked': formLocked }">
      <div class="dep-create-main">
        <div id="dep-sec-flow" class="form-grid">
          <label class="form-field">
            <FormFieldLabel label="流程" required />
            <select v-model="form.flow_code" class="form-inp" @change="onFlowChange">
              <option value="">选择流程</option>
              <option v-for="f in flowOptions" :key="f.id" :value="f.id">{{ flowListItemLabel(f) }}</option>
            </select>
          </label>
          <label class="form-field form-field--narrow form-field--narrow-ver">
            <FormFieldLabel label="版本" tech="ver_no" tech-placement="tooltip" required />
            <select v-model.number="form.ver_no" class="form-inp" :disabled="!form.flow_code">
              <option :value="0">选择版本</option>
              <option v-for="v in versionOptions" :key="v.version" :value="v.version">
                v{{ v.version }}{{ v.description ? ` · ${v.description}` : "" }}
              </option>
            </select>
          </label>
          <label class="form-field">
            <FormFieldLabel
              label="环境"
              tech="env_profile_code"
              tech-placement="tooltip"
              tip="数据字典与中间件连接；留空为默认环境"
            />
            <select v-model="form.env_profile_code" class="form-inp">
              <option value="">（默认）</option>
              <option v-for="p in profileOptions" :key="p" :value="p">{{ p }}</option>
            </select>
          </label>
        </div>

        <div id="dep-sec-mode">
          <div class="form-sec-title">
            <span>部署类型</span>
            <InfoTip text="production 为正式运行；shadow 为灰度/影子流量。" />
          </div>
          <div class="form-option-group" role="radiogroup" aria-label="部署类型">
            <button
              type="button"
              class="form-option"
              :class="{ active: form.mode === 'production' }"
              @click="form.mode = 'production'"
            >
              生产
            </button>
            <button
              type="button"
              class="form-option"
              :class="{ active: form.mode === 'shadow' }"
              @click="form.mode = 'shadow'"
            >
              灰度
            </button>
          </div>
        </div>

        <div id="dep-sec-schedule">
          <div class="form-sec-title">
            <span>调度类型</span>
            <InfoTip text="单次：手动触发一次；定时：按 Cron 周期触发；消息触发：消费消息队列。" />
          </div>
          <div class="form-option-group" role="radiogroup" aria-label="调度类型">
            <button
              type="button"
              class="form-option"
              :class="{ active: form.schedule_type === 'once' }"
              @click="setScheduleType('once')"
            >
              单次运行
            </button>
            <button
              type="button"
              class="form-option"
              :class="{ active: form.schedule_type === 'cron' }"
              @click="setScheduleType('cron')"
            >
              定时（Cron）
            </button>
            <button
              type="button"
              class="form-option"
              :class="{ active: form.schedule_type === 'subscription' }"
              @click="setScheduleType('subscription')"
            >
              {{ scheduleTypeLabel("subscription") }}
            </button>
          </div>
          <p v-if="form.schedule_type === 'cron'" class="schedule-advanced-hint muted small">
            Cron 表达式请在「高级配置」中填写。保存后为 stopped，须在详情页启动后定时调度才会生效。
          </p>
          <p v-else-if="form.schedule_type === 'subscription'" class="schedule-advanced-hint muted small">
            消费者与上下文映射等请在「高级配置」中填写。
          </p>
        </div>

        <div id="dep-sec-runtime">
          <div class="form-sec-title">
            <span>工作节点</span>
            <InfoTip text="下方 Worker 卡片不选则自动分配在线工作节点。" />
          </div>

          <div class="run-node-toolbar">
            <div class="form-option-group" role="radiogroup" aria-label="工作节点策略">
              <button
                type="button"
                class="form-option"
                :class="{ active: workerPolicyForm.type === 'single_active' }"
                @click="setWorkerPolicyType('single_active')"
              >
                单活（同一时刻仅 1 个节点）
              </button>
              <button
                type="button"
                class="form-option"
                :class="{ active: workerPolicyForm.type === 'multi_active' }"
                @click="setWorkerPolicyType('multi_active')"
              >
                多活（多个节点同时）
              </button>
            </div>
            <label class="run-node-min">
              <FormFieldLabel
                :label="workerPolicyForm.type === 'multi_active' ? '最少节点' : '候选节点'"
                tech="min_workers"
                tech-placement="tooltip"
              />
              <input v-model.number="workerPolicyForm.min_workers" type="number" min="1" class="form-inp mono" />
            </label>
          </div>

          <div class="form-sec-title sub">
            <span>指定Worker节点</span>
            <span class="worker-meta muted small">
              在线 <span class="mono">{{ activeWorkers.length }}</span>
              · 已选 <span class="mono">{{ workerSelected.size }}</span>
            </span>
            <button
              v-if="workerSelected.size > 0"
              type="button"
              class="btn sm ghost worker-clear"
              @click="workerSelected.clear()"
            >
              清空
            </button>
          </div>

          <div v-if="workers.length === 0" class="pick-empty">
            暂无 Worker；可先保存部署，启动 <span class="mono">flow-worker</span> 后自动注册。
          </div>
          <div v-else-if="activeWorkers.length === 0" class="pick-empty">暂无在线节点，将自动分配。</div>
          <div v-else class="pick-grid">
            <button
              v-for="w in activeWorkers"
              :key="w.worker_id"
              type="button"
              class="pick-card"
              :class="{ active: workerSelected.has(w.worker_id) }"
              @click="toggleWorker(w.worker_id)"
            >
              <span class="mono pick-card-id">{{ w.worker_id }}</span>
              <span class="tag small" :class="workerStatusClass(w.status)">{{ w.status }}</span>
            </button>
          </div>
        </div>
      </div>

      <aside id="dep-sec-advanced" class="dep-create-side">
        <div class="dep-advanced-panel">
          <div class="form-block-hd">高级配置</div>
          <div class="dep-advanced-scroll scroll-area">
            <details class="advanced">
            <summary>能力策略</summary>
            <p class="side-cap-hint muted small">部署级副作用控制（JSON 数组）</p>
            <div class="form-preset-row">
              <button type="button" class="btn sm ghost" @click="capabilityPolicyText = '[]'">全部允许</button>
              <button type="button" class="btn sm ghost" @click="applySuppressWrites">压制写操作</button>
            </div>
            <textarea v-model="capabilityPolicyText" rows="5" class="form-area mono" spellcheck="false" />
            </details>

            <details
              v-if="form.schedule_type === 'cron'"
              id="dep-sec-cron"
              class="advanced"
              open
            >
                <summary>定时调度（Cron）</summary>
                <label class="form-field full cron-field">
                  <FormFieldLabel
                    label="Cron 表达式"
                    tech="cron_expr"
                    tech-placement="tooltip"
                    required
                    tip="五段式：分 时 日 月 周。例：0 */5 * * *"
                  />
                  <input v-model="form.cron_expr" class="form-inp mono" placeholder="0 */5 * * *" />
                </label>
            </details>

            <details
              v-if="form.schedule_type === 'subscription'"
              id="dep-sec-subscription"
              class="advanced"
              open
            >
                <summary>{{ scheduleTypeLabel("subscription") }}</summary>
                <SubscriptionDeploymentSection
                  v-model:form="subscriptionForm"
                  v-model:mapping="subscriptionMapping"
                  :env-profile-code="form.env_profile_code"
                  pane="consumer"
                />
                <SubscriptionDeploymentSection
                  v-model:form="subscriptionForm"
                  v-model:mapping="subscriptionMapping"
                  :env-profile-code="form.env_profile_code"
                  pane="side"
                />
            </details>
          </div>
        </div>
      </aside>
    </div>

    <p v-if="displayError" class="err">{{ displayError }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import FormFieldLabel from "@/components/FormFieldLabel.vue";
import InfoTip from "@/components/InfoTip.vue";
import SubscriptionDeploymentSection from "@/components/SubscriptionDeploymentSection.vue";
import {
  createDeployment,
  isDeploymentConfigEditable,
  updateDeploymentConfig,
  type CapabilityRule,
  type CreateDeploymentBody,
  type DeploymentDetail,
  type RunMode,
  type ScheduleType,
  type UpdateDeploymentConfigBody,
  type WorkerPolicy,
  type WorkerTargeting,
} from "@/api/deployments";
import type { FlowListItem } from "@/api/flows";
import { fetchVersionList } from "@/api/flowVersions";
import type { FlowVersionMeta } from "@/api/flowVersions";
import type { Worker } from "@/api/workers";
import { flowListItemLabel } from "@/types/flow";
import {
  DEFAULT_INGRESS_MAPPING,
  DEFAULT_SUBSCRIPTION_FORM,
  buildSubscriptionScheduleConfig,
  hydrateSubscriptionFromScheduleConfig,
  type ContextMappingState,
  type SubscriptionFormState,
} from "@/operations/subscriptionScheduleConfig";
import { scheduleTypeLabel } from "@/utils/deploymentOverview";

const props = defineProps<{
  flowOptions: FlowListItem[];
  profileOptions: string[];
  workers: Worker[];
  activeWorkers: Worker[];
  workerStatusClass: (status: string) => string;
  /** Parent-level errors (e.g. flow list load failed when opening create form). */
  externalError?: string;
  /** When set, form operates in edit mode for this deployment. */
  editDeployment?: DeploymentDetail | null;
}>();

const emit = defineEmits<{
  cancel: [];
  created: [id: number];
  saved: [id: number];
  error: [message: string];
  "request-stop": [];
}>();

const isEditMode = computed(() => props.editDeployment != null);
const editDeploymentId = computed(() => props.editDeployment?.id ?? 0);

const formLocked = computed(() => {
  if (!props.editDeployment) return false;
  return !isDeploymentConfigEditable(String(props.editDeployment.status));
});

const lockReason = computed(() => {
  if (!formLocked.value || !props.editDeployment) return "";
  const st = props.editDeployment.status;
  if (st === "running") return "运行中的部署须先停止后方可修改配置。";
  if (st === "stopping") return "部署正在停止中，请等待停止完成后再修改。";
  if (st === "pending") return "部署正在调度/启动中，请先停止后再修改。";
  return `当前状态（${st}）不可修改，请先停止部署。`;
});

const submitting = ref(false);
const formError = ref("");
const displayError = computed(() => formError.value || props.externalError || "");
const versionOptions = ref<FlowVersionMeta[]>([]);

const form = reactive({
  flow_code: "",
  ver_no: 0,
  mode: "production" as RunMode,
  schedule_type: "once" as ScheduleType,
  cron_expr: "",
  env_profile_code: "",
});

const subscriptionForm = reactive<SubscriptionFormState>({ ...DEFAULT_SUBSCRIPTION_FORM });
const subscriptionMapping = ref<ContextMappingState>({
  ...DEFAULT_INGRESS_MAPPING,
});

const workerPolicyForm = reactive({
  type: "single_active" as "single_active" | "multi_active",
  min_workers: 1,
});

const workerSelected = reactive(new Set<string>());
const capabilityPolicyText = ref("[]");

watch(
  () => props.activeWorkers.map((w) => w.worker_id),
  (activeIds) => {
    const active = new Set(activeIds);
    for (const wid of [...workerSelected]) {
      if (!active.has(wid)) workerSelected.delete(wid);
    }
  },
);

const CAPABILITY_ACTIONS = new Set(["allow", "suppress", "redirect"]);
const CAPABILITY_RULE_KEYS = new Set([
  "builtin_category",
  "builtin_name",
  "action",
  "redirect_params",
]);

function validateCapabilityPolicy(rules: unknown[]): string | null {
  for (let i = 0; i < rules.length; i++) {
    const r = rules[i];
    if (typeof r !== "object" || r === null || Array.isArray(r)) {
      return `能力策略第 ${i + 1} 条须为对象`;
    }
    const obj = r as Record<string, unknown>;
    for (const key of Object.keys(obj)) {
      if (!CAPABILITY_RULE_KEYS.has(key)) {
        return `能力策略第 ${i + 1} 条含未知字段「${key}」`;
      }
    }
    const action = obj.action;
    if (typeof action !== "string" || !CAPABILITY_ACTIONS.has(action)) {
      return `能力策略第 ${i + 1} 条 action 须为 allow、suppress 或 redirect`;
    }
  }
  return null;
}

function validateAll(): { error: string; sectionId: string } | null {
  if (!form.flow_code) return { error: "请选择流程", sectionId: "dep-sec-flow" };
  if (!form.ver_no) return { error: "请选择版本", sectionId: "dep-sec-flow" };
  if (form.schedule_type === "cron" && !form.cron_expr.trim()) {
    return { error: "定时运行须填写 Cron 表达式", sectionId: "dep-sec-cron" };
  }
  if (form.schedule_type === "subscription") {
    const built = buildSubscriptionScheduleConfig(subscriptionForm, subscriptionMapping.value);
    if (!built.ok) return { error: built.error, sectionId: "dep-sec-subscription" };
  }
  return null;
}

function scrollToSection(sectionId: string) {
  const el = document.getElementById(sectionId);
  if (!el) return;
  const scrollRoot = el.closest(".dep-advanced-scroll") as HTMLElement | null;
  if (scrollRoot) {
    const rootRect = scrollRoot.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    scrollRoot.scrollTop += elRect.top - rootRect.top - 8;
    return;
  }
  el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function onScheduleTypeChange() {
  if (
    form.schedule_type === "subscription" &&
    workerPolicyForm.type === "single_active" &&
    workerPolicyForm.min_workers > 1
  ) {
    workerPolicyForm.min_workers = 1;
  }
}

function setScheduleType(type: ScheduleType) {
  form.schedule_type = type;
  onScheduleTypeChange();
}

function setWorkerPolicyType(type: "single_active" | "multi_active") {
  workerPolicyForm.type = type;
  if (
    form.schedule_type === "subscription" &&
    type === "single_active" &&
    workerPolicyForm.min_workers > 1
  ) {
    workerPolicyForm.min_workers = 1;
  }
}

function reset() {
  form.flow_code = "";
  form.ver_no = 0;
  form.mode = "production";
  form.schedule_type = "once";
  form.cron_expr = "";
  form.env_profile_code = "";
  Object.assign(subscriptionForm, DEFAULT_SUBSCRIPTION_FORM);
  subscriptionMapping.value = { ...DEFAULT_INGRESS_MAPPING };
  workerPolicyForm.type = "single_active";
  workerPolicyForm.min_workers = 1;
  workerSelected.clear();
  capabilityPolicyText.value = "[]";
  formError.value = "";
  versionOptions.value = [];
}

function hydrateWorkerTargeting(targeting: WorkerTargeting | undefined) {
  workerSelected.clear();
  if (!targeting) return;
  if (targeting.mode === "pin") {
    workerSelected.add(targeting.worker_id);
  } else if (targeting.mode === "pool") {
    for (const id of targeting.worker_ids || []) {
      if (id) workerSelected.add(id);
    }
  }
}

async function reloadVersionOptions(flowCode: string, preferredVerNo?: number): Promise<void> {
  versionOptions.value = [];
  if (!flowCode) {
    form.ver_no = 0;
    return;
  }
  try {
    const res = await fetchVersionList(flowCode);
    let options = [...res.versions].sort((a, b) => b.version - a.version);
    if (
      preferredVerNo != null &&
      preferredVerNo > 0 &&
      !options.some((v) => v.version === preferredVerNo)
    ) {
      options = [
        {
          version: preferredVerNo,
          created_at: 0,
          description: "当前部署版本",
          display_name: "",
        },
        ...options,
      ];
    }
    versionOptions.value = options;
    if (preferredVerNo != null && options.some((v) => v.version === preferredVerNo)) {
      form.ver_no = preferredVerNo;
    } else if (options.length > 0) {
      form.ver_no = options[0]!.version;
    } else {
      form.ver_no = 0;
    }
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
    form.ver_no = preferredVerNo && preferredVerNo > 0 ? preferredVerNo : 0;
  }
}

async function loadFromDeployment(d: DeploymentDetail) {
  form.flow_code = d.flow_code;
  form.mode = (d.mode === "shadow" ? "shadow" : "production") as RunMode;
  form.schedule_type = d.schedule_type as ScheduleType;
  form.env_profile_code = d.env_profile_code || "";
  form.cron_expr =
    d.schedule_type === "cron" ? String(d.schedule_config?.cron_expr ?? "") : "";

  const wp = d.worker_policy || {};
  workerPolicyForm.type =
    wp.type === "multi_active" ? "multi_active" : "single_active";
  workerPolicyForm.min_workers = Math.max(1, Number(wp.min_workers) || 1);

  capabilityPolicyText.value = JSON.stringify(d.capability_policy ?? [], null, 2);
  hydrateWorkerTargeting(d.worker_targeting);

  if (d.schedule_type === "subscription") {
    const hydrated = hydrateSubscriptionFromScheduleConfig(
      (d.schedule_config || {}) as Record<string, unknown>,
    );
    Object.assign(subscriptionForm, hydrated.form);
    subscriptionMapping.value = { ...hydrated.mapping };
  } else {
    Object.assign(subscriptionForm, DEFAULT_SUBSCRIPTION_FORM);
    subscriptionMapping.value = { ...DEFAULT_INGRESS_MAPPING };
  }

  await reloadVersionOptions(d.flow_code, d.ver_no);
}

watch(
  () => props.editDeployment,
  (d) => {
    formError.value = "";
    if (d) void loadFromDeployment(d);
    else reset();
  },
  { immediate: true },
);

defineExpose({ reset, loadFromDeployment });

async function onFlowChange() {
  await reloadVersionOptions(form.flow_code);
}

function toggleWorker(id: string) {
  if (workerSelected.has(id)) workerSelected.delete(id);
  else workerSelected.add(id);
}

function applySuppressWrites() {
  capabilityPolicyText.value = JSON.stringify(
    [
      { builtin_category: "integration", action: "suppress" },
      { builtin_category: "db_write", action: "suppress" },
      { builtin_category: "mq_publish", action: "suppress" },
    ],
    null,
    2,
  );
}

async function submit() {
  formError.value = "";
  if (formLocked.value) {
    formError.value = lockReason.value || "当前不可保存";
    return;
  }
  const v = validateAll();
  if (v) {
    formError.value = v.error;
    scrollToSection(v.sectionId);
    return;
  }

  let schedule_config: Record<string, unknown> = {};
  if (form.schedule_type === "cron") {
    schedule_config = { cron_expr: form.cron_expr.trim() };
  } else if (form.schedule_type === "subscription") {
    const built = buildSubscriptionScheduleConfig(subscriptionForm, subscriptionMapping.value);
    if (!built.ok) {
      formError.value = built.error;
      scrollToSection("dep-sec-subscription");
      return;
    }
    schedule_config = built.config;
  }

  let capabilityPolicy: CapabilityRule[];
  try {
    const parsed = JSON.parse(capabilityPolicyText.value || "[]");
    if (!Array.isArray(parsed)) throw new Error("须为 JSON 数组");
    const capErr = validateCapabilityPolicy(parsed);
    if (capErr) throw new Error(capErr);
    capabilityPolicy = parsed as CapabilityRule[];
  } catch (e) {
    formError.value = `能力策略无效：${e instanceof Error ? e.message : String(e)}`;
    scrollToSection("dep-sec-advanced");
    return;
  }

  const selectedIds = [...workerSelected];
  const worker_targeting =
    selectedIds.length === 0
      ? { mode: "any" as const }
      : selectedIds.length === 1
        ? { mode: "pin" as const, worker_id: selectedIds[0]! }
        : { mode: "pool" as const, worker_ids: selectedIds };

  const worker_policy: WorkerPolicy = {
    type: workerPolicyForm.type,
    min_workers: Math.max(1, Number(workerPolicyForm.min_workers) || 1),
  };

  const configBody: UpdateDeploymentConfigBody = {
    flow_code: form.flow_code,
    ver_no: form.ver_no,
    mode: form.mode,
    schedule_type: form.schedule_type,
    schedule_config,
    worker_policy,
    capability_policy: capabilityPolicy,
    env_profile_code: form.env_profile_code,
    worker_targeting,
  };

  submitting.value = true;
  try {
    if (isEditMode.value && props.editDeployment) {
      await updateDeploymentConfig(props.editDeployment.id, configBody);
      emit("saved", props.editDeployment.id);
    } else {
      const created = await createDeployment({ ...configBody, auto_start: false });
      emit("created", created.id);
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    formError.value = msg;
    emit("error", msg);
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.dep-create-main .form-sec-title.sub {
  flex-wrap: wrap;
}

.worker-meta {
  margin-left: auto;
  font-size: 11px;
}

.worker-clear {
  margin-left: 4px;
}

.pick-card-id {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.dep-create-side :deep(.sub-side) {
  margin-top: 4px;
}

.dep-create-side :deep(.mapping-block) {
  border: none;
  border-radius: 8px;
  padding: 10px 0 0;
  background: transparent;
}

.dep-lock-banner {
  margin: 0;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, #d97706 45%, var(--border));
  background: color-mix(in srgb, #fef3c7 40%, var(--surface));
  color: var(--text);
  font-size: 12px;
  line-height: 1.45;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.dep-lock-banner p {
  margin: 0;
  flex: 1 1 200px;
}

.dep-create-columns--locked {
  opacity: 0.72;
  pointer-events: none;
}

.schedule-advanced-hint {
  margin: 8px 0 0;
  line-height: 1.45;
}

.side-cap-hint {
  margin: 0 0 8px;
}

.cron-field {
  display: grid;
  gap: 4px;
  margin-top: 10px;
  font-size: 11px;
  color: var(--muted);
}

.run-node-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
}

.run-node-toolbar .form-option-group {
  flex: 1 1 280px;
}

.run-node-toolbar .form-option {
  white-space: normal;
  text-align: left;
  line-height: 1.35;
  padding: 8px 12px;
}

.run-node-min {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  font-size: 11px;
  color: var(--muted);
}

.run-node-min .form-inp {
  width: 72px;
  padding: 6px 8px;
}

@media (max-width: 720px) {
  .worker-meta {
    margin-left: 0;
    width: 100%;
  }

  .run-node-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .run-node-min {
    width: 100%;
  }
}
</style>
