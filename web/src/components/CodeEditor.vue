<template>
  <div class="wrap" :data-readonly="readOnly ? 'true' : 'false'" :style="{ height: heightPx }">
    <CodeMirror
      class="cm-fill"
      :model-value="modelValue"
      :extensions="extensions"
      :style="{ height: '100%', minHeight: 0 }"
      :placeholder="placeholderText"
      basic
      @update:model-value="onCmUpdate"
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
import type { RegistryDoc } from "@/api/starlark";
import { flowRegistryAutocompletion } from "@/codemirror/flowRegistryAutocomplete";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    height?: number;
    readOnly?: boolean;
    language?: "python" | "yaml" | "json";
    /** When set (python only), adds demo_add / dict_get / internal exports to completions. */
    registry?: RegistryDoc | null;
  }>(),
  { height: 280, readOnly: false, language: "python", registry: null },
);

const emit = defineEmits<{ (e: "update:modelValue", v: string): void }>();

function onCmUpdate(v: string) {
  if (props.readOnly) return;
  emit("update:modelValue", v);
}

const heightPx = computed(() => `${props.height}px`);

const theme = EditorView.theme(
  {
    "&": {
      fontSize: "12px",
      fontFamily: "var(--mono), ui-monospace, monospace",
      backgroundColor: "#ffffff",
      height: "100%",
      display: "flex",
      flexDirection: "column",
      minHeight: 0,
    },
    ".cm-scroller": {
      fontFamily: "inherit",
      overflow: "auto",
      flex: "1 1 auto",
      minHeight: 0,
    },
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

const extensions = computed(() => {
  const lang =
    props.language === "yaml" ? yaml() : props.language === "json" ? json() : python();
  const reg =
    props.language === "python" && props.registry ? flowRegistryAutocompletion(props.registry) : [];
  return [
    lang,
    ...reg,
    EditorState.readOnly.of(props.readOnly),
    EditorView.editable.of(!props.readOnly),
    theme,
  ];
});
</script>

<style scoped>
.wrap {
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
  display: flex;
  flex-direction: column;
  min-height: 0;
  box-sizing: border-box;
}

.wrap[data-readonly="true"] {
  cursor: default;
}

.cm-fill {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.wrap :deep(.cm-editor) {
  border-radius: 10px;
  height: 100% !important;
  min-height: 0;
  display: flex !important;
  flex-direction: column;
}

.wrap :deep(.cm-gutters) {
  flex-shrink: 0;
}
</style>
