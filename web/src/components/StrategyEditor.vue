<template>
  <div class="page">
    <header class="hd">
      <div>
        <div class="t">运行策略</div>
        <div class="s mono">{{ key }}</div>
      </div>
      <button v-if="key !== 'default_sync'" type="button" class="danger" @click="remove">删除策略</button>
    </header>

    <div class="grid">
      <label class="field">
        <span>显示名称</span>
        <input v-model="st.name" class="inp" @change="save" />
      </label>
      <label class="field">
        <span>模式</span>
        <select v-model="st.mode" class="inp" @change="save">
          <option value="sync">sync（同步阻塞）</option>
          <option value="async">async（协程派发）</option>
          <option value="thread">thread（线程池）</option>
          <option value="process">process（进程池）</option>
        </select>
      </label>
      <label class="field">
        <span>并发 / 池大小</span>
        <input v-model.number="st.concurrency" class="inp" type="number" min="1" @change="save" />
      </label>
      <label class="field">
        <span>超时（秒，可选）</span>
        <input v-model.number="timeout" class="inp" type="number" min="0" step="1" @change="save" />
      </label>
      <label class="field">
        <span>重试次数</span>
        <input v-model.number="st.retry_count" class="inp" type="number" min="0" @change="save" />
      </label>
    </div>

    <div class="note">
      相邻节点若引用非 <span class="mono">sync</span> 策略，且右侧节点未设置
      <span class="mono">wait_before</span>，左侧拓扑会出现「隐式并行」提示带。
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from "vue";
import type { ExecutionStrategy } from "@/types/flow";
import { useFlowStudioStore } from "@/stores/flowStudio";

const store = useFlowStudioStore();

const key = computed(() => (store.selection.kind === "strategy" ? store.selection.key : ""));

const st = reactive<ExecutionStrategy>({
  name: "default_sync",
  mode: "sync",
  concurrency: 4,
  timeout: undefined,
  retry_count: 0,
});

const timeout = computed({
  get: () => (st.timeout == null ? "" : String(st.timeout)),
  set: (v: string) => {
    st.timeout = v === "" ? null : Number(v);
  },
});

watch(
  key,
  (k) => {
    if (!k) return;
    const cur = store.doc.strategies[k];
    if (!cur) return;
    Object.assign(st, cur);
  },
  { immediate: true },
);

function save() {
  if (!key.value) return;
  store.upsertStrategy(key.value, { ...st });
}

function remove() {
  if (!key.value) return;
  store.removeStrategy(key.value);
}
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
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
}

.inp {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 10px;
  outline: none;
  font-size: 13px;
  background: #fff;
}

.inp:focus {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.danger {
  border: 1px solid color-mix(in srgb, #ef4444 35%, transparent);
  background: #fff;
  color: #b91c1c;
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 12px;
  cursor: pointer;
}

.note {
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px dashed var(--border);
  background: color-mix(in srgb, var(--accent-soft) 55%, #fff);
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
}

@media (max-width: 720px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
