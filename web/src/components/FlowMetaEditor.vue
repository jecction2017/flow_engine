<template>
  <div class="page">
    <header class="hd">
      <div>
        <div class="t">流程属性</div>
        <div class="s">名称、版本与初始全局上下文</div>
      </div>
    </header>

    <div class="grid">
      <label class="field">
        <span>名称</span>
        <input v-model="name" class="inp" />
      </label>
      <label class="field">
        <span>版本</span>
        <input v-model="version" class="inp" />
      </label>
    </div>

    <label class="field">
      <span>initial_context（JSON）</span>
      <textarea v-model="ctx" class="area mono" rows="10" spellcheck="false" />
    </label>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useFlowStudioStore } from "@/stores/flowStudio";

const store = useFlowStudioStore();

const name = computed({
  get: () => store.doc.name,
  set: (v: string) => store.setFlowMeta({ name: v }),
});

const version = computed({
  get: () => store.doc.version,
  set: (v: string) => store.setFlowMeta({ version: v }),
});

const ctx = computed({
  get: () => JSON.stringify(store.doc.initial_context ?? {}, null, 2),
  set: (v: string) => {
    try {
      store.setInitialContextJson(v);
    } catch {
      // 允许编辑过程中的临时非法 JSON
    }
  },
});
</script>

<style scoped>
.page {
  padding: 16px;
  max-width: 980px;
}

.hd {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.t {
  font-size: 16px;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.s {
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.field {
  display: grid;
  gap: 6px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--muted);
}

.inp {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 10px;
  outline: none;
  font-size: 13px;
}

.area {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px;
  outline: none;
  resize: vertical;
  background: #fbfdff;
}

.inp:focus,
.area:focus {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

@media (max-width: 720px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
