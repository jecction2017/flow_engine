<template>
  <div class="json-editor" :class="{ 'is-invalid': invalid }">
    <CodeEditor
      :model-value="modelValue"
      language="json"
      :height="height"
      :fill="fill"
      :read-only="readOnly"
      :placeholder="placeholder"
      @update:model-value="onUpdate"
    />
  </div>
</template>

<script setup lang="ts">
import CodeEditor from "@/components/CodeEditor.vue";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    height?: number;
    fill?: boolean;
    readOnly?: boolean;
    placeholder?: string | null;
    invalid?: boolean;
  }>(),
  {
    height: 200,
    fill: false,
    readOnly: false,
    placeholder: null,
    invalid: false,
  },
);

const emit = defineEmits<{ (e: "update:modelValue", value: string): void }>();

function onUpdate(value: string): void {
  emit("update:modelValue", value);
}
</script>

<style scoped>
.json-editor {
  min-width: 0;
}

.json-editor.is-invalid :deep(.wrap) {
  border-color: color-mix(in srgb, #ef4444 55%, var(--border));
  box-shadow: 0 0 0 2px color-mix(in srgb, #ef4444 14%, transparent);
}
</style>
