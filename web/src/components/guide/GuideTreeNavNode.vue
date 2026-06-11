<template>
  <div v-if="node.kind === 'dir'" class="dir">
    <button
      type="button"
      class="dir-btn"
      :style="{ paddingLeft: `${8 + depth * 10}px` }"
      @click="emit('toggle', node.path)"
    >
      <span class="fold">{{ isOpen ? "▼" : "▶" }}</span>
      <span class="label">{{ node.title }}</span>
    </button>
    <div v-show="isOpen" class="children">
      <GuideTreeNavNode
        v-for="child in node.children"
        :key="`${child.kind}:${child.path || child.name}`"
        :node="child"
        :active-path="activePath"
        :expanded="expanded"
        :depth="depth + 1"
        @select="(path) => emit('select', path)"
        @toggle="(path) => emit('toggle', path)"
      />
    </div>
  </div>
  <button
    v-else
    type="button"
    class="doc-btn"
    :class="{ active: activePath === node.path }"
    :style="{ paddingLeft: `${22 + depth * 10}px` }"
    @click="emit('select', node.path)"
  >
    {{ node.title }}
  </button>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { GuideTreeDirNode, GuideTreeNode } from "@/api/guide";

const props = defineProps<{
  node: GuideTreeNode;
  activePath: string;
  expanded: Set<string>;
  depth: number;
}>();

const emit = defineEmits<{
  (e: "select", path: string): void;
  (e: "toggle", path: string): void;
}>();

const isOpen = computed(() => {
  const dir = props.node as GuideTreeDirNode;
  if (dir.kind !== "dir") return false;
  if (!dir.path) return true;
  return props.expanded.has(dir.path);
});
</script>

<style scoped>
.dir-btn,
.doc-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  border: none;
  background: transparent;
  color: var(--muted);
  font-size: 13px;
  text-align: left;
  padding: 6px 8px;
  border-radius: 8px;
  cursor: pointer;
}

.doc-btn:hover,
.dir-btn:hover {
  color: var(--text);
  background: color-mix(in srgb, var(--bg) 80%, var(--surface));
}

.doc-btn.active {
  color: var(--accent);
  background: var(--accent-soft);
  font-weight: 600;
}

.fold {
  width: 12px;
  font-size: 10px;
  flex-shrink: 0;
}

.label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.children {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
</style>
