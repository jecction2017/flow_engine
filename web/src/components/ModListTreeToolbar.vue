<template>
  <div class="mod-list-toolbar" role="toolbar" :aria-label="ariaLabel">
    <p class="mod-list-stats">
      <span>{{ moduleCount }} 个模块</span>
      <span class="mod-list-stats-sep" aria-hidden="true">·</span>
      <span>{{ itemCount }} 个{{ itemLabel }}</span>
    </p>
    <div class="mod-list-toolbar-actions">
      <button
        type="button"
        class="mod-tree-icon-btn"
        title="全部展开"
        aria-label="全部展开"
        :disabled="disabled"
        @click="emit('expandAll')"
      >
        <svg class="mod-tree-ico" viewBox="0 0 16 16" aria-hidden="true">
          <path
            d="M3 5.5 8 9.5 13 5.5M3 9.5 8 13.5 13 9.5"
            fill="none"
            stroke="currentColor"
            stroke-width="1.25"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
      <button
        type="button"
        class="mod-tree-icon-btn"
        title="全部折叠"
        aria-label="全部折叠"
        :disabled="disabled"
        @click="emit('collapseAll')"
      >
        <svg class="mod-tree-ico" viewBox="0 0 16 16" aria-hidden="true">
          <path
            d="M3 10.5 8 6.5 13 10.5M3 6.5 8 2.5 13 6.5"
            fill="none"
            stroke="currentColor"
            stroke-width="1.25"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    ariaLabel?: string;
    disabled?: boolean;
    moduleCount?: number;
    itemCount?: number;
    itemLabel?: string;
  }>(),
  {
    ariaLabel: "列表展开与折叠",
    disabled: false,
    moduleCount: 0,
    itemCount: 0,
    itemLabel: "项",
  },
);

const emit = defineEmits<{
  expandAll: [];
  collapseAll: [];
}>();
</script>

<style scoped>
.mod-list-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin: 0 0 6px;
  padding: 0 2px;
  min-height: 22px;
}

.mod-list-stats {
  margin: 0;
  flex: 1;
  min-width: 0;
  font-size: 10px;
  line-height: 1.25;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mod-list-stats-sep {
  margin: 0 3px;
  opacity: 0.65;
}

.mod-list-toolbar-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.mod-tree-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  transition:
    background 0.12s ease,
    color 0.12s ease,
    border-color 0.12s ease,
    box-shadow 0.12s ease;
}

.mod-tree-icon-btn:hover:not(:disabled) {
  color: var(--text);
  background: color-mix(in srgb, var(--accent-soft) 60%, transparent);
  border-color: color-mix(in srgb, var(--border) 70%, transparent);
}

.mod-tree-icon-btn:focus-visible {
  outline: none;
  color: var(--text);
  background: color-mix(in srgb, var(--accent-soft) 60%, transparent);
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 28%, transparent);
}

.mod-tree-icon-btn:active:not(:disabled) {
  background: color-mix(in srgb, var(--accent-soft) 85%, var(--surface));
  box-shadow: inset 0 1px 2px color-mix(in srgb, var(--text) 8%, transparent);
}

.mod-tree-icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.mod-tree-ico {
  width: 13px;
  height: 13px;
  display: block;
}
</style>
