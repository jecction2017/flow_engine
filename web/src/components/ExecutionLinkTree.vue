<template>
  <div
    ref="rootElRef"
    class="run-trace run-trace--link"
    :class="{ 'rt-click-rows': detailOnRowClick, 'rt-no-meta': !showNodeMeta }"
  >
    <div class="rt-axis">
      <span class="rt-axis-lead">{{ axisLeadLabel }}</span>
      <div class="rt-axis-ticks">
        <span>0</span>
        <span>{{ axisMidLabel }}</span>
        <span>{{ axisMaxLabel }}</span>
      </div>
      <span class="rt-axis-trail">时间线 · 状态 · 日志</span>
    </div>
    <div v-if="$slots.toolbar" class="rt-toolbar">
      <slot name="toolbar" />
    </div>
    <div v-if="$slots.filters" class="rt-filters">
      <slot name="filters" />
    </div>
    <ul class="rt-rows">
      <li v-for="row in rows" :key="row.key" class="rt-item">
        <div
          class="rt-row"
          :class="[
            row.statusTone,
            {
              'is-branch': row.hasChildren,
              'has-logs': row.logCount > 0,
              'rt-highlight': isHighlighted(row),
              'rt-detail-open': secondaryOpenKey === row.key,
              'rt-filter-hit': row.filterMatch === true,
            },
          ]"
          :data-node-id="row.nodeId"
          :data-span-id="row.spanId != null ? String(row.spanId) : undefined"
          :title="rowTitle(row)"
          @click="onRowClick(row)"
        >
          <span class="rt-order">{{ row.orderDisplay }}</span>
          <span class="rt-dot" />
          <span class="rt-name mono">
            <span class="rt-indent" aria-hidden="true">
              <span
                v-for="(hasLine, i) in row.guides"
                :key="i"
                class="rt-guide"
                :class="{ on: hasLine }"
              />
              <span v-if="row.depth > 0" class="rt-guide elbow" :class="{ last: row.isLast }" />
            </span>
            <button
              v-if="row.hasChildren"
              type="button"
              class="rt-caret"
              :aria-expanded="!collapsed.has(row.key)"
              @click.stop="emit('toggle-collapsed', row.key)"
            >
              {{ collapsed.has(row.key) ? "▶" : "▼" }}
            </button>
            <span v-else class="rt-caret-spacer" />
            <span class="rt-id" :title="nodeTitle(row)">{{ nodeDisplayText(row) }}</span>
            <span
              v-for="(b, bi) in row.metaBadges ?? []"
              :key="bi"
              class="rt-meta"
              :title="b.title"
              >{{ b.label }}</span
            >
          </span>
          <span v-if="showNodeMeta" class="rt-type-tag mono" :title="row.nodeType">{{ row.nodeType }}</span>
          <span v-if="showNodeMeta" class="rt-scope mono" :title="row.scopeKey || ''">{{ row.scopeKey || "—" }}</span>
          <span class="rt-started mono" :title="row.startedTitle ?? row.startedDisplay">
            {{ row.startedDisplay }}
            <span
              v-if="row.startedDeltaDisplay"
              class="rt-started-delta"
              :title="row.startedDeltaTitle ?? row.startedDeltaDisplay"
            >
              {{ row.startedDeltaDisplay }}
            </span>
          </span>
          <span class="rt-dur mono">{{ row.durationDisplay }}</span>
          <div class="rt-track">
            <div class="rt-bar" :style="barStyle(row)" />
          </div>
          <span class="rt-status">{{ row.statusLabel }}</span>
          <button
            v-if="logButton && row.logCount > 0"
            type="button"
            class="rt-logs-btn"
            :aria-expanded="secondaryOpenKey === row.key"
            @click.stop="emit('toggle-secondary', row.key)"
          >
            {{ row.logCount }}
          </button>
          <span v-else-if="logButton" class="rt-logs-muted">—</span>
          <span v-else-if="row.logCount > 0" class="rt-logs-badge" title="日志条数（点击行查看）">{{ row.logCount }}</span>
          <span v-else class="rt-logs-muted">—</span>
        </div>
        <div v-if="secondaryOpenKey === row.key && $slots.secondary" class="rt-secondary">
          <slot name="secondary" :row="row" />
        </div>
      </li>
    </ul>
    <slot name="footer" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

/** One flattened row for the unified execution link tree (trial or persisted spans). */
export type ExecutionLinkRow = {
  key: string;
  orderDisplay: string;
  depth: number;
  hasChildren: boolean;
  isLast: boolean;
  guides: boolean[];
  nodeId: string;
  nodeName?: string;
  nodeType: string;
  scopeKey: string;
  startedDisplay: string;
  /** Optional longer tooltip for started column */
  startedTitle?: string;
  /** Optional delta from previous visible row's started_ms. */
  startedDeltaDisplay?: string;
  startedDeltaTitle?: string;
  durationMs: number | null;
  durationDisplay: string;
  statusLabel: string;
  statusTone: string;
  logCount: number;
  /** Timeline bar: absolute epoch ms (spans) or relative flow ms (trial). */
  barStartMs: number;
  barEndMs: number;
  spanId?: number;
  metaBadges?: { label: string; title?: string }[];
  /** True when this row directly matches active log-level filter. */
  filterMatch?: boolean;
};

const props = withDefaults(
  defineProps<{
    rows: ExecutionLinkRow[];
    timelineMinMs: number;
    timelineMaxMs: number;
    collapsed: Set<string>;
    secondaryOpenKey?: string | null;
    /** When true, clicking the row (not caret / log) emits `row-click`. */
    detailOnRowClick?: boolean;
    /** When true, show the log counter as a secondary toggle (trial). When false and detailOnRowClick, badge still shown as button that triggers row-click. */
    logButton?: boolean;
    highlightNodeId?: string | null;
    showNodeMeta?: boolean;
  }>(),
  {
    secondaryOpenKey: null,
    detailOnRowClick: false,
    logButton: true,
    highlightNodeId: null,
    showNodeMeta: true,
  },
);

const emit = defineEmits<{
  (e: "toggle-collapsed", key: string): void;
  (e: "toggle-secondary", key: string): void;
  (e: "row-click", row: ExecutionLinkRow): void;
}>();

const rootElRef = ref<HTMLElement | null>(null);
defineExpose({ rootElRef });

const rangeMs = computed(() => Math.max(1, props.timelineMaxMs - props.timelineMinMs));

const axisMidLabel = computed(() => `${Math.round(rangeMs.value / 2)}ms`);
const axisMaxLabel = computed(() => `${Math.round(rangeMs.value)}ms`);
const showNodeMeta = computed(() => props.showNodeMeta);
const axisLeadLabel = computed(() =>
  showNodeMeta.value ? "顺序 · 节点 · 类型 · 业务键 · 开始 · 耗时" : "顺序 · 节点 · 开始 · 耗时",
);

function barStyle(row: ExecutionLinkRow): Record<string, string> {
  const t0 = props.timelineMinMs;
  const total = rangeMs.value;
  const start = row.barStartMs - t0;
  const end = row.barEndMs - t0;
  const leftPct = Math.max(0, Math.min(100, (start / total) * 100));
  const rawWidth = ((end - start) / total) * 100;
  const widthPct = Math.max(2, Math.min(100 - leftPct, rawWidth || 2));
  return { left: `${leftPct}%`, width: `${widthPct}%` };
}

function isHighlighted(row: ExecutionLinkRow): boolean {
  const h = props.highlightNodeId?.trim();
  return !!h && row.nodeId === h;
}

function onRowClick(row: ExecutionLinkRow): void {
  if (props.detailOnRowClick) emit("row-click", row);
}

function rowTitle(row: ExecutionLinkRow): string {
  const nodeDisplay = nodeDisplayText(row);
  const nodeLabel = nodeDisplay === row.nodeId ? nodeDisplay : `${nodeDisplay} (${row.nodeId})`;
  const parts = [
    `${row.orderDisplay}  ${nodeLabel}`,
    `开始: ${row.startedDisplay}`,
    `耗时: ${row.durationDisplay}`,
    `状态: ${row.statusLabel}`,
  ];
  if (showNodeMeta.value) {
    parts.splice(1, 0, `类型: ${row.nodeType}`, `业务键: ${row.scopeKey || "—"}`);
  }
  if (row.logCount > 0) parts.push(`日志: ${row.logCount}`);
  return parts.join("\n");
}

function nodeDisplayText(row: ExecutionLinkRow): string {
  const name = row.nodeName?.trim();
  return name && name.length > 0 ? name : row.nodeId;
}

function nodeTitle(row: ExecutionLinkRow): string {
  const name = row.nodeName?.trim();
  return name && name.length > 0 ? `${name} (${row.nodeId})` : row.nodeId;
}
</script>

<style scoped>
.rt-logs-muted {
  font-size: 9px;
  color: var(--muted);
  text-align: center;
  justify-self: center;
}

.rt-logs-badge {
  font-size: 9px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: #1d4ed8;
  background: color-mix(in srgb, #3b82f6 10%, transparent);
  border: 1px solid color-mix(in srgb, #3b82f6 22%, transparent);
  border-radius: 4px;
  padding: 0 4px;
  text-align: center;
  justify-self: center;
}
</style>
