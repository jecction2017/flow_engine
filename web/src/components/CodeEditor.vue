<template>
  <div class="wrap">
    <CodeMirror
      :model-value="modelValue"
      :extensions="extensions"
      :style="{ height: heightPx }"
      :placeholder="placeholderText"
      basic
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import CodeMirror from "vue-codemirror6";
import { json } from "@codemirror/lang-json";
import { python } from "@codemirror/lang-python";
import { yaml } from "@codemirror/lang-yaml";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    height?: number;
    readOnly?: boolean;
    language?: "python" | "yaml" | "json";
  }>(),
  { height: 280, readOnly: false, language: "python" },
);

const emit = defineEmits<{ (e: "update:modelValue", v: string): void }>();

const heightPx = computed(() => `${props.height}px`);

const theme = EditorView.theme(
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
);

const placeholderText = computed(() => {
  if (props.language === "yaml") return "YAML";
  if (props.language === "json") return "JSON";
  return "Starlark / Python 风格脚本";
});

const extensions = computed(() => [
  props.language === "yaml" ? yaml() : props.language === "json" ? json() : python(),
  EditorState.readOnly.of(props.readOnly),
  theme,
]);
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
