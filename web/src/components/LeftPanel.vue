<template>
  <div class="panel">
    <section class="block">
      <div class="block-title">流程</div>
      <button type="button" class="sel" :class="{ on: store.selection.kind === 'flow' }" @click="store.select({ kind: 'flow' })">
        <span class="dot" />
        <span class="txt">
          <span class="n">{{ store.doc.name }}</span>
          <span class="v">v{{ store.doc.version }}</span>
        </span>
      </button>
    </section>

    <section class="block">
      <div class="block-title row">
        <span>运行策略</span>
        <button type="button" class="mini" @click="addStrategy">＋</button>
      </div>
      <div class="list">
        <button
          v-for="k in store.strategiesList"
          :key="k"
          type="button"
          class="sel small"
          :class="{ on: store.selection.kind === 'strategy' && store.selection.key === k }"
          @click="store.select({ kind: 'strategy', key: k })"
        >
          <span class="mono">{{ k }}</span>
          <span class="mode">{{ store.modeOf(k) }}</span>
        </button>
      </div>
    </section>

    <section class="block grow">
      <div class="block-title row">
        <span>节点拓扑</span>
        <span class="hint">相邻非同步且无屏障 → 并行带</span>
      </div>

      <div class="toolbar">
        <button type="button" class="tb" @click="store.addRoot('task')">＋ Task</button>
        <button type="button" class="tb" @click="store.addRoot('loop')">＋ Loop</button>
        <button type="button" class="tb" @click="store.addRoot('subflow')">＋ Subflow</button>
      </div>

      <div class="tree">
        <FlowTreeItem :nodes="store.doc.nodes" :path-prefix="[]" :depth="0" />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useFlowStudioStore } from "@/stores/flowStudio";
import FlowTreeItem from "./FlowTreeItem.vue";

const store = useFlowStudioStore();

function addStrategy() {
  const name = prompt("策略 key（英文标识）", "strategy_new");
  if (!name) return;
  store.upsertStrategy(name, {
    name,
    mode: "async",
    concurrency: 4,
    timeout: 120,
    retry_count: 0,
  });
  store.select({ kind: "strategy", key: name });
}
</script>

<style scoped>
.panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  min-height: 0;
}

.block {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  padding: 10px;
  box-shadow: var(--shadow);
}

.block.grow {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.block-title {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 8px;
  font-weight: 700;
}

.block-title.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.mini {
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 8px;
  width: 26px;
  height: 26px;
  cursor: pointer;
}

.sel {
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 10px;
  padding: 10px;
  display: flex;
  gap: 10px;
  align-items: center;
  cursor: pointer;
}

.sel.small {
  padding: 8px 10px;
  margin-bottom: 6px;
  justify-content: space-between;
}

.sel.on {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  background: linear-gradient(180deg, #ffffff, var(--accent-soft));
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: radial-gradient(circle at 30% 30%, #fff, var(--accent));
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.txt {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.n {
  font-weight: 700;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.v {
  font-size: 11px;
  color: var(--muted);
}

.mode {
  font-size: 10px;
  color: var(--muted);
}

.list {
  max-height: 180px;
  overflow: auto;
  padding-right: 2px;
}

.hint {
  font-size: 10px;
  color: var(--muted);
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.tb {
  border: 1px dashed color-mix(in srgb, var(--border) 80%, var(--accent));
  background: #fff;
  border-radius: 999px;
  padding: 5px 8px;
  font-size: 11px;
  cursor: pointer;
}

.tree {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}
</style>
