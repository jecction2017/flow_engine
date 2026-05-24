<template>
  <div class="sid-inline">
    <pre v-if="span.error" class="sid-err mono">{{ span.error }}</pre>
    <section v-if="hasLogs" class="sid-block">
      <div class="sid-head">
        <span>日志（{{ logs.length }}）</span>
        <div class="lvl-toolbar">
          <button
            v-for="lvl in ALL_LOG_LEVELS"
            :key="lvl"
            type="button"
            class="chip-btn"
            :class="[`lvl-${lvl}`, { active: levelFilter.has(lvl) }]"
            @click="toggleLevelFilter(lvl)"
          >
            {{ lvl }}
          </button>
          <button v-if="levelFilter.size > 0" type="button" class="link small" @click="clearLevelFilter">清除</button>
        </div>
      </div>
      <ul v-if="filteredLogs.length" class="sid-logs mono">
        <li v-for="(entry, i) in filteredLogs" :key="i" class="sid-log" :class="`lvl-${entry.level}`">
          <span class="sid-ts">+{{ entry.t_ms }}ms</span>
          <span class="sid-lvl">{{ entry.level }}</span>
          <span class="sid-src" :title="entry.source">{{ entry.source }}</span>
          <span class="sid-msg">{{ entry.msg ?? entry.message }}</span>
        </li>
      </ul>
      <p v-else class="muted small">当前日志级别过滤下无条目</p>
    </section>
    <section v-if="hasAttrs" class="sid-block">
      <div class="sid-head"><span>自定义 KV（attributes）</span></div>
      <table class="sid-kv">
        <tbody>
          <tr v-for="(val, key) in span.attributes" :key="key">
            <td class="mono sid-k">{{ key }}</td>
            <td class="mono sid-v">{{ formatAttrVal(val) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
    <p v-if="!hasLogs && !hasAttrs && !span.error" class="muted small">暂无日志与扩展字段</p>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive } from "vue";
import type { SpanDetail, SpanLogEntry } from "@/api/spans";

const ALL_LOG_LEVELS = ["debug", "info", "warn", "error"] as const;
type KnownLevel = (typeof ALL_LOG_LEVELS)[number];

const props = defineProps<{ span: SpanDetail }>();

const levelFilter = reactive(new Set<KnownLevel>());

const logs = computed<SpanLogEntry[]>(() =>
  Array.isArray(props.span.logs) ? (props.span.logs as SpanLogEntry[]) : [],
);

const hasLogs = computed(() => logs.value.length > 0);

const hasAttrs = computed(() => {
  const a = props.span.attributes;
  return a != null && Object.keys(a).length > 0;
});

const filteredLogs = computed(() => {
  if (levelFilter.size === 0) return logs.value;
  return logs.value.filter((e) => levelFilter.has(e.level as KnownLevel));
});

function toggleLevelFilter(lvl: KnownLevel): void {
  if (levelFilter.has(lvl)) levelFilter.delete(lvl);
  else levelFilter.add(lvl);
}

function clearLevelFilter(): void {
  levelFilter.clear();
}

function formatAttrVal(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}
</script>

<style scoped>
.sid-inline {
  font-size: 11px;
  line-height: 1.45;
}

.sid-err {
  margin: 0 0 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: color-mix(in srgb, #fecaca 35%, transparent);
  color: #b91c1c;
  white-space: pre-wrap;
  word-break: break-word;
}

.sid-block {
  margin-bottom: 8px;
}

.sid-block:last-child {
  margin-bottom: 0;
}

.sid-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--text, #0f172a);
}

.lvl-toolbar {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 3px;
  align-items: center;
}

.chip-btn {
  text-transform: uppercase;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.03em;
  border-radius: 999px;
  padding: 0 6px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
  cursor: pointer;
}

.chip-btn.active.lvl-info {
  background: color-mix(in srgb, #3b82f6 18%, transparent);
  color: #1d4ed8;
}
.chip-btn.active.lvl-warn {
  background: color-mix(in srgb, #f59e0b 22%, transparent);
  color: #92400e;
}
.chip-btn.active.lvl-error {
  background: color-mix(in srgb, #ef4444 20%, transparent);
  color: #b91c1c;
}
.chip-btn.active.lvl-debug {
  background: color-mix(in srgb, #94a3b8 22%, transparent);
  color: #475569;
}

.sid-logs {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  max-height: 220px;
  overflow: auto;
  background: #fff;
}

.sid-log {
  display: grid;
  grid-template-columns: 52px 40px 88px 1fr;
  gap: 4px 6px;
  padding: 3px 6px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 55%, transparent);
  align-items: baseline;
}

.sid-log:last-child {
  border-bottom: none;
}

.sid-ts {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.sid-lvl {
  text-transform: uppercase;
  font-weight: 700;
  font-size: 9px;
  padding: 0 4px;
  border-radius: 3px;
  background: #e2e8f0;
  color: #475569;
  text-align: center;
}

.sid-log.lvl-info .sid-lvl {
  background: color-mix(in srgb, #3b82f6 15%, transparent);
  color: #1d4ed8;
}
.sid-log.lvl-warn .sid-lvl {
  background: color-mix(in srgb, #f59e0b 20%, transparent);
  color: #92400e;
}
.sid-log.lvl-error .sid-lvl {
  background: color-mix(in srgb, #ef4444 18%, transparent);
  color: #b91c1c;
}
.sid-log.lvl-debug .sid-lvl {
  background: color-mix(in srgb, #94a3b8 20%, transparent);
  color: #475569;
}

.sid-src {
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
}

.sid-msg {
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text, #0f172a);
}

.sid-kv {
  width: 100%;
  border-collapse: collapse;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
}

.sid-kv td {
  padding: 3px 6px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 55%, transparent);
  vertical-align: top;
}

.sid-kv tr:last-child td {
  border-bottom: none;
}

.sid-k {
  width: 34%;
  color: var(--muted);
  font-size: 10px;
}

.sid-v {
  font-size: 10px;
  word-break: break-all;
}

.muted {
  color: var(--muted);
}

.small {
  font-size: 10px;
}

.link {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  padding: 0;
  font-size: 10px;
}

.link:hover {
  text-decoration: underline;
}

.mono {
  font-family: var(--mono);
}
</style>
