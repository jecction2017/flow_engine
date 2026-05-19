<template>
  <section v-if="logs.length" class="flow-logs-panel">
    <div class="flow-logs-head">
      <span>{{ title }}</span>
      <span class="muted">{{ logs.length }} 条</span>
    </div>
    <ul class="logs-list mono">
      <li
        v-for="(entry, i) in logs"
        :key="i"
        class="log-row"
        :class="`lvl-${normalizeLevel(entry.level)}`"
      >
        <span class="log-ts">+{{ entry.ts_ms }}ms</span>
        <span class="log-lvl">{{ entry.level }}</span>
        <span class="log-src" :title="`来源: ${entry.source}`">{{ entry.source }}</span>
        <span class="log-msg">{{ entry.message }}</span>
        <span v-if="entry.truncated" class="log-trunc" title="截断">…</span>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import type { LogEntry } from "@/api/flows";

withDefaults(
  defineProps<{
    logs: LogEntry[];
    title?: string;
  }>(),
  { title: "流程级钩子日志" },
);

function normalizeLevel(level: string): string {
  const l = (level || "").toLowerCase();
  if (l === "debug" || l === "info" || l === "warn" || l === "error") return l;
  return "info";
}
</script>

<style scoped>
.flow-logs-panel {
  margin-top: 8px;
}
.flow-logs-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 500;
}
.muted {
  color: #64748b;
  font-weight: 400;
  font-size: 12px;
}
.logs-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 280px;
  overflow: auto;
  font-size: 12px;
}
.log-row {
  display: grid;
  grid-template-columns: 72px 52px 100px 1fr auto;
  gap: 8px;
  padding: 4px 6px;
  border-radius: 4px;
  background: #f8fafc;
}
.log-row.lvl-error {
  background: #fef2f2;
}
.log-row.lvl-warn {
  background: #fffbeb;
}
.log-ts {
  color: #64748b;
}
.log-lvl {
  text-transform: uppercase;
  font-size: 11px;
}
.log-src {
  color: #475569;
  overflow: hidden;
  text-overflow: ellipsis;
}
.log-msg {
  word-break: break-word;
}
.log-trunc {
  color: #94a3b8;
}
</style>
