<template>
  <Teleport to="body">
    <div
      v-show="open"
      class="rdd-backdrop"
      aria-hidden="true"
      @click.self="emit('close')"
    />
    <aside
      v-show="open"
      class="rdd-drawer"
      :class="{ 'rdd-drawer--open': open }"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
      @click.stop
    >
      <div class="rdd-drawer-hd">
        <span class="rdd-drawer-title">{{ title }}</span>
        <button type="button" class="btn ghost small" @click="emit('close')">关闭</button>
      </div>
      <div class="rdd-drawer-body">
        <p v-if="loading" class="muted small pad">加载中…</p>
        <RunDetailPanel v-else-if="detail" :detail="detail" />
      </div>
    </aside>
  </Teleport>
</template>

<script setup lang="ts">
import { onUnmounted, watch } from "vue";
import type { FlowRunDetail } from "@/api/flowRuns";
import RunDetailPanel from "@/components/RunDetailPanel.vue";

const props = defineProps<{
  open: boolean;
  title: string;
  loading?: boolean;
  detail: FlowRunDetail | null;
}>();

const emit = defineEmits<{ (e: "close"): void }>();

function onEscape(ev: KeyboardEvent) {
  if (ev.key !== "Escape" || !props.open) return;
  emit("close");
}

watch(
  () => props.open,
  (v) => {
    if (v) document.addEventListener("keydown", onEscape);
    else document.removeEventListener("keydown", onEscape);
  },
  { immediate: true },
);

onUnmounted(() => {
  document.removeEventListener("keydown", onEscape);
});
</script>

<style scoped>
.rdd-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: color-mix(in srgb, #0f172a 32%, transparent);
}

.rdd-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 51;
  width: min(980px, calc(100vw - 16px));
  max-width: 100%;
  background: var(--surface);
  border-left: 1px solid var(--border);
  box-shadow: -8px 0 28px rgba(15, 23, 42, 0.14);
  display: flex;
  flex-direction: column;
  transform: translateX(100%);
  transition: transform 0.22s ease-out, visibility 0.22s;
  pointer-events: none;
  visibility: hidden;
}

.rdd-drawer--open {
  transform: translateX(0);
  pointer-events: auto;
  visibility: visible;
}

.rdd-drawer-hd {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}

.rdd-drawer-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.01em;
}

.rdd-drawer-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 10px 12px 12px;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;
}
</style>
