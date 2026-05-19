<template>
  <div class="hooks-editor">
    <div v-if="!enabled" class="empty-hint">
      未配置钩子。<button type="button" class="mini" @click="enable">添加钩子</button>
    </div>
    <div v-else class="slot-list">
      <div v-for="slot in slots" :key="slot.key" class="hook-row">
        <div class="hook-head">
          <span class="hook-key mono">{{ slot.key }}</span>
          <span v-if="slot.tip" class="hook-tip">
            <InfoTip wide :text="slot.tip" />
          </span>
          <div class="hook-actions">
            <button
              v-if="hasSlotValue(slot.key)"
              type="button"
              class="mini ghost"
              @click="clearSlot(slot.key)"
            >
              清空
            </button>
          </div>
        </div>
        <div class="editor-wrap">
          <CodeEditor
            :model-value="slotValue(slot.key)"
            :height="editorHeight(slot.key)"
            :registry="registry"
            :path-suggestions="pathSuggestions"
            placeholder="# Starlark，通常仅用 resolve() 读路径"
            @update:model-value="(v) => onSlotUpdate(slot.key, v)"
          />
        </div>
      </div>
      <div class="list-foot">
        <button type="button" class="mini ghost danger" @click="disableAll">移除全部钩子</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { normalizeHooks } from "@/types/flow";
import CodeEditor from "./CodeEditor.vue";
import InfoTip from "./InfoTip.vue";
import type { RegistryPythonFn } from "@/api/starlark";

export type HookSlotDef = {
  key: string;
  label: string;
  tip?: string;
};

const props = defineProps<{
  modelValue: Record<string, string | null | undefined> | null | undefined;
  slots: HookSlotDef[];
  registry?: RegistryPythonFn[] | null;
  pathSuggestions?: ((prefix: string) => string[]) | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: Record<string, string | null | undefined> | null): void;
}>();

const enabled = ref(false);

const slotKeys = computed(() => props.slots.map((s) => s.key));

watch(
  () => props.modelValue,
  (v) => {
    if (v && slotKeys.value.some((k) => typeof v[k] === "string" && (v[k] as string).trim())) {
      enabled.value = true;
    }
  },
  { immediate: true, deep: true },
);

function slotValue(key: string): string {
  const v = props.modelValue?.[key];
  return typeof v === "string" ? v : "";
}

function hasSlotValue(key: string): boolean {
  return slotValue(key).trim().length > 0;
}

function editorHeight(key: string): number {
  const lines = Math.max(1, slotValue(key).split("\n").length);
  return Math.min(160, Math.max(56, lines * 20 + 16));
}

function emitNormalized(next: Record<string, string | null | undefined> | null) {
  const keys = slotKeys.value;
  const normalized = normalizeHooks(next, keys as (keyof typeof next)[]);
  emit("update:modelValue", normalized);
}

function onSlotUpdate(key: string, value: string) {
  const base = { ...(props.modelValue ?? {}) };
  if (value.trim()) {
    base[key] = value;
  } else {
    delete base[key];
  }
  emitNormalized(base);
}

function clearSlot(key: string) {
  const base = { ...(props.modelValue ?? {}) };
  delete base[key];
  emitNormalized(base);
}

function enable() {
  enabled.value = true;
  if (!props.modelValue) {
    emit("update:modelValue", {});
  }
}

function disableAll() {
  enabled.value = false;
  emit("update:modelValue", null);
}
</script>

<style scoped>
.hooks-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.empty-hint {
  font-size: 11.5px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.slot-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hook-row {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px 10px;
  background: #fbfdff;
}

.hook-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  min-width: 0;
}

.hook-key {
  font-size: 11px;
  font-weight: 600;
  color: var(--text);
  padding: 2px 6px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--accent-soft, #eff6ff) 65%, #fff);
  border: 1px solid color-mix(in srgb, var(--border) 80%, var(--accent, #3b82f6) 20%);
}

.hook-tip {
  display: inline-flex;
  align-items: center;
}

.hook-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
}

.editor-wrap {
  border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
}

.editor-wrap :deep(.wrap) {
  border: none;
  border-radius: 0;
}

.list-foot {
  display: flex;
  justify-content: flex-start;
  padding-top: 2px;
}

.mini {
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 11px;
  cursor: pointer;
  color: var(--muted);
  font-weight: 500;
  transition: all 0.15s ease;
}

.mini:hover:not(:disabled) {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
}

.mini.ghost {
  background: transparent;
}

.mini.danger:hover:not(:disabled) {
  color: #b91c1c;
  border-color: #fca5a5;
}
</style>
