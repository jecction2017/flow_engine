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
      :style="{ width: drawerWidth }"
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
      <div class="debug-drawer-body" :class="{ 'debug-drawer-body--split': hasScriptPane }">
        <div v-if="hasScriptPane" class="debug-drawer-split">
          <aside class="debug-drawer-script" aria-label="脚本编辑">
            <slot name="script" />
          </aside>
          <div class="debug-drawer-main">
            <slot />
          </div>
        </div>
        <slot v-else />
      </div>
    </aside>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onUnmounted, useSlots, watch } from "vue";

const slots = useSlots();
const hasScriptPane = computed(() => !!slots.script);

const open = defineModel<boolean>("open", { default: false });

withDefaults(
  defineProps<{
    title: string;
    ariaLabel?: string;
    pending?: boolean;
    showRun?: boolean;
    /** 抽屉宽度，默认与历史节点调试一致；流程节点调试可传入更宽值。 */
    drawerWidth?: string;
  }>(),
  {
    pending: false,
    showRun: true,
    drawerWidth: "min(480px, calc(100vw - 12px))",
  },
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

.debug-drawer-body--split {
  overflow: hidden;
  padding: 0;
}

.debug-drawer-split {
  display: grid;
  grid-template-columns: minmax(300px, 1fr) minmax(340px, 1fr);
  height: 100%;
  min-height: 0;
}

.debug-drawer-script {
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  border-right: 1px solid color-mix(in srgb, #1e293b 40%, var(--border));
  background: #0f172a;
}

.debug-drawer-main {
  min-height: 0;
  min-width: 0;
  overflow: auto;
  padding: 12px 14px 16px;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;
}

.debug-drawer-script :deep(.debug-script-pane) {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.debug-drawer-script :deep(.debug-script-hd) {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px 8px;
  border-bottom: 1px solid color-mix(in srgb, #334155 65%, transparent);
}

.debug-drawer-script :deep(.debug-script-hd-title) {
  font-size: 12px;
  font-weight: 600;
  color: #e2e8f0;
  letter-spacing: 0.01em;
}

.debug-drawer-script :deep(.debug-script-hd .info-tip) {
  color: #94a3b8;
}

.debug-drawer-script :deep(.debug-script-body) {
  flex: 1 1 auto;
  min-height: 0;
  padding: 6px 8px 10px;
}

@media (max-width: 900px) {
  .debug-drawer-split {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(200px, 38vh) 1fr;
  }

  .debug-drawer-script {
    border-right: none;
    border-bottom: 1px solid color-mix(in srgb, #1e293b 40%, var(--border));
  }
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
