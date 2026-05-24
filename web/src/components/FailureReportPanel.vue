<template>
  <div class="failure-report">
    <table v-if="rows.length" class="fr-table">
      <tbody>
        <tr v-for="(row, i) in rows" :key="i">
          <th>{{ row.label }}</th>
          <td class="mono pre">{{ row.value }}</td>
        </tr>
      </tbody>
    </table>

    <div v-if="detailText" class="fr-block">
      <div class="fr-block-head">详情</div>
      <pre class="fr-pre mono">{{ detailText }}</pre>
    </div>

    <div v-if="scriptExcerpt" class="fr-block">
      <div class="fr-block-head">脚本摘录</div>
      <pre class="fr-pre mono script">{{ scriptExcerpt }}</pre>
    </div>

    <div v-if="causeChain.length" class="fr-block">
      <div class="fr-block-head">因果链</div>
      <ol class="fr-chain">
        <li v-for="(item, i) in causeChain" :key="i" class="mono small">{{ item }}</li>
      </ol>
    </div>

    <pre v-if="fallbackText && !rows.length" class="fr-pre mono fallback">{{ fallbackText }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  formatFailureDetailRows,
  hasFailureDetail,
  type FailureDetail,
} from "@/utils/formatFailureReport";

const props = defineProps<{
  failureDetail?: FailureDetail | null;
  /** Legacy plain ``error`` when structured detail is absent. */
  fallbackText?: string | null;
}>();

const rows = computed(() =>
  hasFailureDetail(props.failureDetail)
    ? formatFailureDetailRows(props.failureDetail)
    : [],
);

const detailText = computed(() => {
  const d = props.failureDetail;
  if (!hasFailureDetail(d)) return "";
  const text = (d.detail ?? "").trim();
  if (!text || text === (d.summary ?? "").trim()) return "";
  return text;
});

const scriptExcerpt = computed(() =>
  hasFailureDetail(props.failureDetail)
    ? (props.failureDetail.script_excerpt ?? "").trim()
    : "",
);

const causeChain = computed(() =>
  hasFailureDetail(props.failureDetail)
    ? (props.failureDetail.cause_chain ?? []).filter(Boolean)
    : [],
);
</script>

<style scoped>
.failure-report {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fr-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.fr-table th {
  text-align: left;
  vertical-align: top;
  width: 72px;
  padding: 4px 10px 4px 0;
  color: var(--muted);
  font-weight: 600;
  white-space: nowrap;
}

.fr-table td {
  padding: 4px 0;
  color: #1e293b;
  word-break: break-word;
}

.fr-block-head {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.fr-pre {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, #fecaca 22%, transparent);
  color: #7f1d1d;
  font-size: 11px;
  line-height: 1.45;
  max-height: 280px;
  overflow: auto;
}

.fr-pre.script {
  background: #0b1220;
  color: #e2e8f0;
}

.fr-pre.fallback {
  background: color-mix(in srgb, #fecaca 30%, transparent);
}

.fr-chain {
  margin: 0;
  padding-left: 20px;
  font-size: 11px;
  color: #7f1d1d;
}

.pre {
  white-space: pre-wrap;
}

.mono {
  font-family: var(--mono);
}

.small {
  font-size: 11px;
}
</style>
