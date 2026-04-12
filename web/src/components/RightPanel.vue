<template>
  <div class="wrap">
    <FlowMetaEditor v-if="store.selection.kind === 'flow'" />
    <StrategyEditor v-else-if="store.selection.kind === 'strategy'" />
    <NodeEditor v-else-if="store.selection.kind === 'node'" :path="store.selection.path" />
    <div v-else class="empty">
      <div class="t">选择左侧对象开始编辑</div>
      <div class="d">流程、策略或节点</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useFlowStudioStore } from "@/stores/flowStudio";
import FlowMetaEditor from "./FlowMetaEditor.vue";
import NodeEditor from "./NodeEditor.vue";
import StrategyEditor from "./StrategyEditor.vue";

const store = useFlowStudioStore();
</script>

<style scoped>
.wrap {
  height: 100%;
  min-height: 0;
  overflow: auto;
}

.empty {
  height: 100%;
  display: grid;
  place-items: center;
  padding: 40px 16px;
  color: var(--muted);
  text-align: center;
}

.t {
  font-weight: 800;
  color: var(--text);
  letter-spacing: -0.02em;
}

.d {
  margin-top: 6px;
  font-size: 12px;
}
</style>
