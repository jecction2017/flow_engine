<template>
  <ul class="sub">
    <li v-for="key in keys" :key="key" class="node">
      <button
        type="button"
        class="row"
        :class="{ active: isActive(key) }"
        @click="select(key)"
      >
        <span class="chev">{{ isMapping(key) ? ">" : "·" }}</span>
        <span class="k">{{ key }}</span>
        <span v-if="!isMapping(key)" class="v mono">{{ preview(key) }}</span>
      </button>
      <DictTreeItem
        v-if="isMapping(key)"
        :node="childNode(key)"
        :path-prefix="childPath(key)"
        :selected-path="selectedPath"
        @select="$emit('select', $event)"
      />
    </li>
  </ul>
</template>

<script setup lang="ts">
import { computed } from "vue";
import DictTreeItem from "./DictTreeItem.vue";

const props = defineProps<{
  node: Record<string, unknown>;
  pathPrefix: string[];
  selectedPath: string;
}>();

const emit = defineEmits<{ (e: "select", path: string): void }>();

const keys = computed(() => Object.keys(props.node).sort((a, b) => a.localeCompare(b)));

function childNode(key: string): Record<string, unknown> {
  const v = props.node[key];
  return typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function isMapping(key: string): boolean {
  const v = props.node[key];
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function childPath(key: string): string[] {
  return [...props.pathPrefix, key];
}

function pathDot(parts: string[]): string {
  return parts.join(".");
}

function select(key: string) {
  emit("select", pathDot(childPath(key)));
}

function isActive(key: string): boolean {
  const p = pathDot(childPath(key));
  return props.selectedPath === p || props.selectedPath.startsWith(`${p}.`);
}

function preview(key: string): string {
  const v = props.node[key];
  if (v === null || v === undefined) return "null";
  if (typeof v === "object") return Array.isArray(v) ? "[…]" : "{…}";
  const s = String(v);
  return s.length > 28 ? `${s.slice(0, 28)}…` : s;
}
</script>

<style scoped>
.sub {
  list-style: none;
  margin: 0;
  padding: 0 0 0 12px;
  border-left: 1px solid var(--border);
}

.node {
  margin: 2px 0;
}

.row {
  width: 100%;
  display: flex;
  align-items: baseline;
  gap: 6px;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 6px;
  padding: 4px 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text);
}

.row:hover {
  background: color-mix(in srgb, var(--surface) 88%, var(--accent-soft));
}

.row.active {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  background: var(--accent-soft);
}

.chev {
  width: 14px;
  color: var(--muted);
  flex-shrink: 0;
}

.k {
  font-weight: 600;
  flex-shrink: 0;
}

.v {
  color: var(--muted);
  margin-left: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
