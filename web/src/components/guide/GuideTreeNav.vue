<template>
  <nav class="guide-tree" aria-label="帮助文档目录">
    <GuideTreeNavNode
      v-for="node in nodes"
      :key="nodeKey(node)"
      :node="node"
      :active-path="activePath"
      :expanded="expanded"
      :depth="0"
      @select="(path) => emit('select', path)"
      @toggle="toggleDir"
    />
  </nav>
</template>

<script setup lang="ts">
import { reactive, watch } from "vue";
import type { GuideTreeNode } from "@/api/guide";
import GuideTreeNavNode from "./GuideTreeNavNode.vue";

const props = defineProps<{
  nodes: GuideTreeNode[];
  activePath: string;
}>();

const emit = defineEmits<{
  (e: "select", path: string): void;
}>();

const expanded = reactive(new Set<string>());

function nodeKey(node: GuideTreeNode): string {
  return `${node.kind}:${node.path || node.name}`;
}

function parentPrefixes(path: string): string[] {
  const parts = path.split("/").filter(Boolean);
  if (parts.length <= 1) return [];
  const out: string[] = [];
  for (let i = 1; i < parts.length; i += 1) {
    out.push(parts.slice(0, i).join("/"));
  }
  return out;
}

function ensureExpandedForPath(path: string): void {
  for (const p of parentPrefixes(path)) {
    expanded.add(p);
  }
}

function toggleDir(path: string): void {
  if (expanded.has(path)) expanded.delete(path);
  else expanded.add(path);
}

watch(
  () => props.activePath,
  (path) => {
    ensureExpandedForPath(path);
  },
  { immediate: true },
);

watch(
  () => props.nodes,
  () => {
    ensureExpandedForPath(props.activePath);
  },
  { immediate: true },
);
</script>

<style scoped>
.guide-tree {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
</style>
