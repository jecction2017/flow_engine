<template>
  <div
    class="wrap"
    :class="{ 'is-fill': fill, 'is-code-dark': appearance === 'code-dark' }"
    :data-readonly="readOnly ? 'true' : 'false'"
    :style="fill ? undefined : { height: heightPx }"
  >
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
import { EditorState, type Extension, type Text } from "@codemirror/state";
import { EditorView, tooltips } from "@codemirror/view";
import { oneDark } from "@codemirror/theme-one-dark";
import type { RegistryDoc } from "@/api/starlark";
import { flowRegistryAutocompletion } from "@/codemirror/flowRegistryAutocomplete";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    height?: number;
    /** When true, editor stretches to fill its flex parent instead of using `height`. */
    fill?: boolean;
    readOnly?: boolean;
    language?: "python" | "yaml" | "json";
    /** When set (python only), adds demo_add / dict_get / internal exports to completions. */
    registry?: RegistryDoc | null;
    /** 当为 python 时，为 ``$.`` 上下文路径提供补全（每次打开菜单时重新拉取路径列表）。 */
    pathSuggestions?: (() => readonly string[]) | null;
    /** 将换行符剥掉，适合单行表达式 / 路径输入。 */
    stripNewlines?: boolean;
    /** 覆盖默认占位提示（如单行路径、条件表达式）。 */
    placeholder?: string | null;
    /** 暗色编辑区（如任务节点主脚本），与浅色表单区分。 */
    appearance?: "default" | "code-dark";
  }>(),
  {
    height: 280,
    fill: false,
    readOnly: false,
    language: "python",
    registry: null,
    pathSuggestions: null,
    stripNewlines: false,
    placeholder: null,
    appearance: "default",
  },
);

const emit = defineEmits<{ (e: "update:modelValue", v: string): void }>();

function onCmUpdate(v?: string | Text) {
  if (props.readOnly) return;
  let s = typeof v === "string" ? v : (v?.toString() ?? "");
  if (props.stripNewlines) s = s.replace(/\r?\n/g, "");
  emit("update:modelValue", s);
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
  const custom = (props.placeholder ?? "").trim();
  if (custom) return custom;
  if (props.language === "yaml") return "YAML";
  if (props.language === "json") return "JSON";
  return "Starlark / Python 风格脚本";
});

const tooltipParent =
  typeof document !== "undefined" ? (document.body as HTMLElement) : undefined;

const extensions = computed<Extension[]>(() => {
  const lang =
    props.language === "yaml" ? yaml() : props.language === "json" ? json() : python();
  const mergedCm =
    props.language === "python" && (props.registry || props.pathSuggestions)
      ? flowRegistryAutocompletion(props.registry ?? null, props.pathSuggestions ?? null)
      : null;
  const chrome: Extension =
    props.appearance === "code-dark" ? oneDark : theme;
  return [
    ...(tooltipParent ? [tooltips({ parent: tooltipParent })] : []),
    lang,
    ...(mergedCm ? [mergedCm] : []),
    EditorState.readOnly.of(props.readOnly),
    EditorView.editable.of(!props.readOnly),
    chrome,
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

.wrap.is-fill {
  flex: 1 1 auto;
  height: 100%;
  min-height: 0;
}

.wrap.is-code-dark {
  border-color: #3e4451;
  background: #282c34;
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

<!-- CodeMirror 将补全说明挂到 body 时，不受 scoped 主题影响，需单独保证层级与版式 -->
<style>
.cm-tooltip {
  z-index: 5000;
  max-width: min(420px, calc(100vw - 24px));
}
.cm-tooltip.cm-completionInfo {
  padding: 8px 10px;
  line-height: 1.45;
  font-size: 12px;
}
</style>
