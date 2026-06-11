<template>
  <div
    class="json-editor"
    :class="{ 'is-invalid': invalid }"
    :style="fill ? undefined : { height: `${currentHeight}px` }"
    @focusin="onFocusIn"
    @focusout="onFocusOut"
  >
    <CodeEditor
      :model-value="modelValue"
      language="json"
      :height="currentHeight"
      :fill="fill"
      :read-only="readOnly"
      :placeholder="placeholder"
      @update:model-value="onUpdate"
    />
    <button
      v-if="showResizeHandle"
      type="button"
      class="pane-resize-corner"
      aria-label="拖动调整 JSON 区域高度"
      :class="{ 'pane-resize-corner--active': resizeActive }"
      @mousedown="startResize($event)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import CodeEditor from "@/components/CodeEditor.vue";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    height?: number;
    fill?: boolean;
    readOnly?: boolean;
    placeholder?: string | null;
    invalid?: boolean;
    resizable?: boolean;
    minHeight?: number;
  }>(),
  {
    height: 200,
    fill: false,
    readOnly: false,
    placeholder: null,
    invalid: false,
    resizable: true,
    minHeight: 96,
  },
);

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
  (e: "focus"): void;
  (e: "blur"): void;
}>();
const currentHeight = ref(props.height);
const resizeActive = ref(false);
let resizeStartY = 0;
let resizeStartHeight = 0;

const showResizeHandle = computed(() => props.resizable && !props.fill);

watch(
  () => props.height,
  (v) => {
    currentHeight.value = v;
  },
);

function onUpdate(value: string): void {
  emit("update:modelValue", value);
}

function onFocusIn(): void {
  emit("focus");
}

function onFocusOut(ev: FocusEvent): void {
  const root = ev.currentTarget as HTMLElement | null;
  const next = ev.relatedTarget;
  if (root && next instanceof Node && root.contains(next)) return;
  emit("blur");
}

function onResizeMove(ev: MouseEvent) {
  const dy = ev.clientY - resizeStartY;
  currentHeight.value = Math.max(props.minHeight, resizeStartHeight + dy);
}

function stopResize() {
  resizeActive.value = false;
  document.removeEventListener("mousemove", onResizeMove);
  document.removeEventListener("mouseup", stopResize);
  document.body.style.removeProperty("user-select");
  document.body.style.removeProperty("cursor");
}

function startResize(ev: MouseEvent) {
  ev.preventDefault();
  resizeActive.value = true;
  resizeStartY = ev.clientY;
  resizeStartHeight = currentHeight.value;
  document.body.style.userSelect = "none";
  document.body.style.cursor = "nwse-resize";
  document.addEventListener("mousemove", onResizeMove);
  document.addEventListener("mouseup", stopResize);
}

onUnmounted(() => {
  stopResize();
});
</script>

<style scoped>
.json-editor {
  min-width: 0;
  position: relative;
  box-sizing: border-box;
}

.json-editor.is-invalid :deep(.wrap) {
  border-color: color-mix(in srgb, #ef4444 55%, var(--border));
  box-shadow: 0 0 0 2px color-mix(in srgb, #ef4444 14%, transparent);
}

.pane-resize-corner {
  position: absolute;
  right: 2px;
  bottom: 2px;
  z-index: 2;
  width: 14px;
  height: 14px;
  padding: 0;
  border: none;
  border-radius: 0 0 6px 0;
  background: transparent;
  cursor: nwse-resize;
  touch-action: none;
}

.pane-resize-corner::after {
  content: "";
  position: absolute;
  right: 2px;
  bottom: 2px;
  width: 8px;
  height: 8px;
  border-right: 2px solid #94a3b8;
  border-bottom: 2px solid #94a3b8;
  border-radius: 0 0 2px 0;
  opacity: 0.75;
  pointer-events: none;
}

.pane-resize-corner:hover::after,
.pane-resize-corner--active::after {
  border-color: var(--accent);
  opacity: 1;
}
</style>
