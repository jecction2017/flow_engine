<template>
  <span class="ffl">
    <span class="ffl-primary">{{ label }}</span>
    <InfoTip v-if="resolvedTip" :text="resolvedTip" :wide="wideTip" />
    <span v-if="showTechInline" class="ffl-tech mono">{{ tech }}</span>
    <em v-if="required" class="req">*</em>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import InfoTip from "@/components/InfoTip.vue";

const props = withDefaults(
  defineProps<{
    label: string;
    tip?: string;
    tech?: string;
    required?: boolean;
    wideTip?: boolean;
    showTech?: boolean;
    techPlacement?: "inline" | "tooltip";
  }>(),
  {
    showTech: false,
    techPlacement: "inline",
  },
);

const showTechInline = computed(() => props.showTech && props.techPlacement === "inline" && !!props.tech);

const resolvedTip = computed(() => {
  if (!props.tip && !(props.showTech && props.techPlacement === "tooltip" && props.tech)) return undefined;
  if (props.showTech && props.techPlacement === "tooltip" && props.tech) {
    return props.tip ? `${props.tip}\n字段：${props.tech}` : `字段：${props.tech}`;
  }
  return props.tip;
});
</script>

<style scoped>
.ffl {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px 4px;
  font-size: 12px;
  font-weight: 500;
  color: #475569;
}

.ffl-tech {
  font-size: 10px;
  font-weight: 500;
  color: var(--muted);
}

.req {
  color: #e11d48;
  font-style: normal;
}
</style>
