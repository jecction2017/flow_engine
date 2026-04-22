<template>
  <div class="pub-root">
    <!-- Header -->
    <header class="pub-header">
      <div class="pub-brand">
        <span class="pub-logo">⬡</span>
        <div>
          <div class="pub-title">发布管理</div>
          <div class="pub-subtitle">版本发布 · 灰度/生产通道 · 运行实例</div>
        </div>
      </div>
      <div class="pub-toolbar">
        <select v-model="selectedFlowId" class="sel" @change="onSelectFlow">
          <option value="" disabled>选择流程…</option>
          <option
            v-for="f in flowList"
            :key="(f as any).id"
            :value="(f as any).id"
            :title="(f as any).id"
          >
            {{ flowOptionLabel(f) }}
          </option>
        </select>
        <button class="btn ghost" :disabled="!selectedFlowId || pStore.loading" @click="pStore.refresh()">
          刷新
        </button>
      </div>
    </header>

    <!-- Error -->
    <div v-if="pStore.error" class="err-bar">{{ pStore.error }}</div>

    <!-- No flow selected -->
    <div v-if="!selectedFlowId" class="empty-hint">请先选择一个流程。</div>

    <div v-else class="pub-body">
      <!-- Channel cards -->
      <section class="channels">
        <ChannelCard
          label="生产版本"
          channel="production"
          :state="pStore.publishState?.production"
          :versions="pStore.versions"
          :latest-version="pStore.latestVersion"
          :loading="pStore.loading"
          @publish="onPublish"
          @stop="onStop"
        />
        <ChannelCard
          label="灰度版本"
          channel="gray"
          :state="pStore.publishState?.gray"
          :versions="pStore.versions"
          :latest-version="pStore.latestVersion"
          :loading="pStore.loading"
          @publish="onPublish"
          @stop="onStop"
        />
      </section>

      <!-- Instances table -->
      <section class="inst-section">
        <div class="section-header">
          <span class="section-title">运行实例</span>
          <span class="inst-count">共 {{ pStore.instances.length }} 个（运行中 {{ pStore.runningInstances.length }}）</span>
        </div>
        <div v-if="pStore.instances.length === 0" class="no-inst">暂无运行实例。</div>
        <table v-else class="inst-table">
          <thead>
            <tr>
              <th>实例 ID</th>
              <th>版本</th>
              <th>通道</th>
              <th>状态</th>
              <th>启动时间</th>
              <th>最后心跳</th>
              <th>进程 / 主机</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="inst in pStore.instances" :key="inst.instance_id" :class="`row-${inst.status}`">
              <td class="mono">{{ inst.instance_id.slice(0, 12) }}…</td>
              <td>V{{ inst.version }}</td>
              <td>{{ channelLabel(inst.channel) }}</td>
              <td><StatusBadge :status="inst.status" /></td>
              <td>{{ fmtTime(inst.started_at) }}</td>
              <td>{{ fmtAgo(inst.last_heartbeat) }}</td>
              <td class="mono">{{ inst.pid ?? "—" }} / {{ inst.host ?? "—" }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>

    <!-- Publish dialog -->
    <div v-if="publishDialog" class="overlay" @click.self="publishDialog = null">
      <div class="dialog">
        <h3 class="dialog-title">发布版本到{{ publishDialog.channel === "production" ? "生产" : "灰度" }}通道</h3>
        <label class="dialog-label">选择版本</label>
        <select v-model="publishDialog.selectedVersion" class="sel full">
          <option v-for="v in pStore.versions" :key="v.version" :value="v.version">
            V{{ v.version }}{{ v.version === pStore.latestVersion ? " (最新)" : "" }}
            {{ v.description ? " – " + v.description : "" }}
          </option>
        </select>
        <div v-if="pStore.versions.length === 0" class="dialog-warn">该流程尚无版本，请先在 Flow Studio 中提交版本。</div>
        <div class="dialog-actions">
          <button class="btn ghost" @click="publishDialog = null">取消</button>
          <button
            class="btn primary"
            :disabled="!publishDialog.selectedVersion || pStore.loading"
            @click="confirmPublish"
          >
            {{ pStore.loading ? "发布中…" : "确认发布" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { useFlowStudioStore } from "@/stores/flowStudio";
import { usePublishStore } from "@/stores/publish";
import type { ChannelState, FlowVersionMeta } from "@/api/publish";
import { defineComponent, computed, h } from "vue";

const flowStudioStore = useFlowStudioStore();
const pStore = usePublishStore();

const selectedFlowId = ref("");
const flowList = computed(() => flowStudioStore.flowList);

type PublishDialog = { channel: "production" | "gray"; selectedVersion: number | null };
const publishDialog = ref<PublishDialog | null>(null);

onMounted(async () => {
  await flowStudioStore.refreshFlowList();
});

onUnmounted(() => {
  pStore.closeSse();
});

async function onSelectFlow() {
  if (!selectedFlowId.value) return;
  await pStore.selectFlow(selectedFlowId.value);
}

function onPublish(channel: "production" | "gray") {
  publishDialog.value = {
    channel,
    selectedVersion: pStore.latestVersion || null,
  };
}

async function confirmPublish() {
  if (!publishDialog.value?.selectedVersion) return;
  try {
    await pStore.publish(publishDialog.value.selectedVersion, publishDialog.value.channel);
    publishDialog.value = null;
  } catch {
    // error displayed via pStore.error
  }
}

async function onStop(channel: "production" | "gray") {
  if (!confirm(`确认停止${channel === "production" ? "生产" : "灰度"}通道的发布？\n所有运行实例将接收停止消息。`)) return;
  await pStore.stop(channel);
}

function fmtTime(epoch: number): string {
  return new Date(epoch * 1000).toLocaleString("zh-CN", { hour12: false });
}

function fmtAgo(epoch: number): string {
  const secs = Math.floor(Date.now() / 1000 - epoch);
  if (secs < 60) return `${secs}s 前`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m 前`;
  return `${Math.floor(secs / 3600)}h 前`;
}

function channelLabel(ch: string): string {
  return ch === "production" ? "生产" : ch === "gray" ? "灰度" : ch;
}

function flowOptionLabel(f: unknown): string {
  const item = f as { id: string; display_name?: string };
  const dn = (item.display_name ?? "").trim();
  if (!dn || dn === item.id) return item.id;
  return `${dn} (${item.id})`;
}
</script>

<!-- ChannelCard sub-component (inline) -->
<script lang="ts">
import { defineComponent, computed, h, PropType } from "vue";

const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  unpublished: { label: "未发布", cls: "s-off" },
  publishing:  { label: "发布中", cls: "s-pub" },
  running:     { label: "运行中", cls: "s-run" },
  stopped:     { label: "已停止", cls: "s-off" },
  failed:      { label: "发布失败", cls: "s-fail" },
};

export const StatusBadge = defineComponent({
  name: "StatusBadge",
  props: { status: { type: String, required: true } },
  setup(props) {
    return () => {
      const s = STATUS_MAP[props.status] ?? { label: props.status, cls: "s-off" };
      return h("span", { class: ["status-badge", s.cls] }, s.label);
    };
  },
});

export const ChannelCard = defineComponent({
  name: "ChannelCard",
  props: {
    label:         { type: String, required: true },
    channel:       { type: String as PropType<"production" | "gray">, required: true },
    state:         { type: Object as PropType<ChannelState | undefined>, default: undefined },
    versions:      { type: Array as PropType<FlowVersionMeta[]>, default: () => [] },
    latestVersion: { type: Number, default: 0 },
    loading:       { type: Boolean, default: false },
  },
  emits: ["publish", "stop"],
  setup(props, { emit }) {
    const st = computed(() => props.state ?? { version: null, status: "unpublished", published_at: null, stopped_at: null });
    const info = computed(() => STATUS_MAP[st.value.status] ?? { label: st.value.status, cls: "s-off" });
    const canPublish = computed(() => !["publishing", "running"].includes(st.value.status));
    const canStop = computed(() => ["publishing", "running"].includes(st.value.status));

    function fmtTime(epoch: number | null): string {
      if (!epoch) return "—";
      return new Date(epoch * 1000).toLocaleString("zh-CN", { hour12: false });
    }

    return () =>
      h("div", { class: ["channel-card", info.value.cls] }, [
        h("div", { class: "card-head" }, [
          h("span", { class: "card-label" }, props.label),
          h("span", { class: ["status-badge", info.value.cls] }, info.value.label),
        ]),
        h("div", { class: "card-version" }, [
          st.value.version != null
            ? h("span", { class: "ver-num" }, `V${st.value.version}`)
            : h("span", { class: "ver-none" }, "—"),
        ]),
        h("div", { class: "card-time" }, [
          st.value.published_at
            ? h("span", null, `发布时间：${fmtTime(st.value.published_at)}`)
            : null,
          st.value.stopped_at
            ? h("span", null, `停止时间：${fmtTime(st.value.stopped_at)}`)
            : null,
        ]),
        h("div", { class: "card-actions" }, [
          canPublish.value
            ? h("button", { class: "btn primary sm", disabled: props.loading, onClick: () => emit("publish", props.channel) }, "发布版本")
            : null,
          canStop.value
            ? h("button", { class: "btn danger sm", disabled: props.loading, onClick: () => emit("stop", props.channel) }, "停止发布")
            : null,
        ]),
      ]);
  },
});
</script>

<style scoped>
.pub-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.pub-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 86%, transparent);
  backdrop-filter: blur(10px);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.pub-brand {
  display: flex;
  gap: 10px;
  align-items: center;
}

.pub-logo {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: linear-gradient(145deg, #e0e7ff, #fff);
  border: 1px solid var(--border);
  color: #6366f1;
  font-size: 18px;
}

.pub-title {
  font-weight: 700;
  font-size: 15px;
  letter-spacing: -0.02em;
}

.pub-subtitle {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}

.pub-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
}

.sel {
  min-width: 200px;
  max-width: 280px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 12px;
  background: #fff;
}

.sel.full {
  width: 100%;
  max-width: 100%;
}

.err-bar {
  padding: 6px 20px;
  font-size: 12px;
  color: #b45309;
  background: color-mix(in srgb, #fbbf24 12%, transparent);
  border-bottom: 1px solid color-mix(in srgb, #f59e0b 25%, transparent);
}

.empty-hint {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  font-size: 14px;
}

.pub-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Channel cards */
.channels {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

:global(.channel-card) {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  background: var(--surface);
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

:global(.channel-card.s-run) {
  border-color: color-mix(in srgb, #10b981 30%, transparent);
  background: color-mix(in srgb, #10b981 4%, var(--surface));
}

:global(.channel-card.s-pub) {
  border-color: color-mix(in srgb, #3b82f6 30%, transparent);
  background: color-mix(in srgb, #3b82f6 4%, var(--surface));
}

:global(.channel-card.s-fail) {
  border-color: color-mix(in srgb, #ef4444 30%, transparent);
  background: color-mix(in srgb, #ef4444 4%, var(--surface));
}

:global(.card-head) {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

:global(.card-label) {
  font-weight: 700;
  font-size: 14px;
}

:global(.card-version) {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.04em;
}

:global(.ver-num) { color: var(--accent); }
:global(.ver-none) { color: var(--muted); font-size: 22px; }

:global(.card-time) {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: var(--muted);
}

:global(.card-actions) {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

/* Status badge */
:global(.status-badge) {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}

:global(.status-badge.s-off) { background: #f1f5f9; color: #64748b; }
:global(.status-badge.s-pub) { background: #dbeafe; color: #1d4ed8; }
:global(.status-badge.s-run) { background: #d1fae5; color: #065f46; }
:global(.status-badge.s-fail) { background: #fee2e2; color: #991b1b; }

/* Buttons */
.btn {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}

.btn:disabled { opacity: 0.55; cursor: not-allowed; }

.btn.ghost:hover:not(:disabled) { border-color: var(--border-strong); }

.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.btn.primary:hover:not(:disabled) { opacity: 0.9; }

:global(.btn.danger) {
  background: #ef4444;
  color: #fff;
  border-color: #ef4444;
}

:global(.btn.danger:hover:not(:disabled)) { background: #dc2626; }

:global(.btn.sm) { padding: 5px 10px; font-size: 11px; }

/* Instances table */
.inst-section {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 60%, transparent);
}

.section-title {
  font-weight: 600;
  font-size: 13px;
}

.inst-count {
  font-size: 12px;
  color: var(--muted);
}

.no-inst {
  padding: 24px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

.inst-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.inst-table th {
  padding: 8px 12px;
  text-align: left;
  font-weight: 600;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 60%, transparent);
}

.inst-table td {
  padding: 8px 12px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 50%, transparent);
}

.inst-table tbody tr:last-child td { border-bottom: none; }
.inst-table tbody tr:hover { background: color-mix(in srgb, var(--accent-soft) 30%, transparent); }

.row-stopped td { color: var(--muted); }
.row-failed td { color: #b91c1c; }

.mono { font-family: monospace; font-size: 11px; }

/* Dialog */
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.dialog {
  background: #fff;
  border-radius: 16px;
  padding: 28px;
  min-width: 360px;
  max-width: 480px;
  width: 90%;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.dialog-title {
  font-size: 15px;
  font-weight: 700;
  margin: 0;
}

.dialog-label {
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
}

.dialog-warn {
  font-size: 12px;
  color: #b45309;
  background: color-mix(in srgb, #fbbf24 12%, transparent);
  padding: 8px 10px;
  border-radius: 8px;
}

.dialog-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 4px;
}
</style>
