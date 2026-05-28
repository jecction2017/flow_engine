<template>
  <JsonEditor
    :model-value="modelValue"
    :height="defaultHeight"
    :min-height="minHeight"
    :resizable="resizable"
    read-only
  />
</template>

<script setup lang="ts">
import JsonEditor from "@/components/JsonEditor.vue";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    defaultHeight?: number;
    minHeight?: number;
    resizable?: boolean;
  }>(),
  {
    defaultHeight: 220,
    minHeight: 100,
    resizable: true,
  },
);
</script>
