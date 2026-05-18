<template>
  <Teleport to="body">
    <div
      v-show="open"
      class="debug-drawer-backdrop"
      @click.self="close"
    />
    <aside
      class="debug-drawer"
      :class="{ 'debug-drawer--open': open }"
      role="dialog"
      aria-modal="true"
      :aria-label="ariaLabel || title"
      @click.stop
    >
      <div class="debug-drawer-hd">
        <span class="debug-drawer-title">{{ title }}</span>
        <div class="debug-drawer-hd-actions">
          <button
            v-if="showRun"
            type="button"
            class="btn primary sm"
            :disabled="pending"
            @click="emit('run')"
          >
            {{ pending ? "请求中…" : "▶ 调试" }}
          </button>
          <button type="button" class="btn ghost sm" @click="close">关闭</button>
        </div>
      </div>
      <div class="debug-drawer-body">
        <slot />
      </div>
    </aside>
  </Teleport>
</template>

<script setup lang="ts">
import { onUnmounted, watch } from "vue";

const open = defineModel<boolean>("open", { default: false });

withDefaults(
  defineProps<{
    title: string;
    ariaLabel?: string;
    pending?: boolean;
    showRun?: boolean;
  }>(),
  { pending: false, showRun: true },
);

const emit = defineEmits<{
  run: [];
}>();

function close() {
  open.value = false;
}

function onEscape(ev: KeyboardEvent) {
  if (ev.key !== "Escape" || !open.value) return;
  close();
}

watch(
  open,
  (isOpen) => {
    if (isOpen) document.addEventListener("keydown", onEscape);
    else document.removeEventListener("keydown", onEscape);
  },
  { immediate: true },
);

onUnmounted(() => {
  document.removeEventListener("keydown", onEscape);
});
</script>

<style scoped>
.debug-drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: color-mix(in srgb, #0f172a 32%, transparent);
}

.debug-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 51;
  width: min(480px, calc(100vw - 12px));
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

.debug-drawer--open {
  transform: translateX(0);
  pointer-events: auto;
  visibility: visible;
}

.debug-drawer-hd {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}

.debug-drawer-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.01em;
}

.debug-drawer-hd-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.debug-drawer-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 12px 14px 16px;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;
}

.btn {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 7px;
  padding: 5px 10px;
  font-size: 11.5px;
  cursor: pointer;
}

.btn.sm {
  padding: 4px 9px;
  font-size: 11px;
}

.btn.ghost {
  background: #fff;
  box-shadow: none;
}

.btn.ghost:hover {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  color: var(--accent);
}

.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
}

.btn.primary:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 88%, #000);
}

.btn.primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
</style>
