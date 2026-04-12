<template>
  <div class="wrap">
    <CodeMirror
      :model-value="modelValue"
      :extensions="extensions"
      :style="{ height: heightPx }"
      placeholder="Starlark / Python 风格脚本"
      basic
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import CodeMirror from "vue-codemirror6";
import { python } from "@codemirror/lang-python";
import { EditorView } from "@codemirror/view";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    height?: number;
  }>(),
  { height: 280 },
);

const emit = defineEmits<{ (e: "update:modelValue", v: string): void }>();

const heightPx = computed(() => `${props.height}px`);

const extensions = [
  python(),
  EditorView.theme(
    {
      "&": {
        fontSize: "12px",
        fontFamily: "var(--mono), ui-monospace, monospace",
        backgroundColor: "#ffffff",
      },
      ".cm-scroller": { fontFamily: "inherit" },
      ".cm-gutters": {
        backgroundColor: "#f8fafc",
        color: "#94a3b8",
        border: "none",
      },
      ".cm-activeLineGutter": { backgroundColor: "#e8f0fe" },
    },
    { dark: false },
  ),
];
</script>

<style scoped>
.wrap {
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}

.wrap :deep(.cm-editor) {
  border-radius: 10px;
}
</style>
