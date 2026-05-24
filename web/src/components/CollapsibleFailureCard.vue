<template>
  <details class="failure-card" :class="tone">
    <summary class="failure-card-toggle">
      <div class="failure-card-summary">
        <div class="failure-card-title">{{ title }}</div>
        <p v-if="preview" class="failure-card-preview">{{ preview }}</p>
      </div>
      <span class="failure-card-chevron" aria-hidden="true" />
    </summary>
    <div class="failure-card-body">
      <slot />
      <div v-if="$slots.footer" class="failure-card-footer">
        <slot name="footer" />
      </div>
    </div>
  </details>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string;
    preview?: string;
    tone?: "bad" | "warn";
  }>(),
  { tone: "bad", preview: "" },
);
</script>

<style scoped>
.failure-card {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid color-mix(in srgb, #ef4444 35%, var(--border));
  border-radius: 10px;
  background: color-mix(in srgb, #fef2f2 60%, var(--surface));
}

.failure-card.warn {
  border-color: color-mix(in srgb, #d97706 35%, var(--border));
  background: color-mix(in srgb, #fffbeb 65%, var(--surface));
}

.failure-card-toggle {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  min-height: 40px;
  padding: 8px 12px;
  list-style: none;
  cursor: pointer;
  user-select: none;
  box-sizing: border-box;
}

.failure-card-toggle::-webkit-details-marker {
  display: none;
}

.failure-card[open] > .failure-card-toggle {
  padding-bottom: 4px;
}

.failure-card-summary {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.failure-card-title {
  font-size: 12px;
  font-weight: 700;
  color: #b91c1c;
  line-height: 1.25;
}

.failure-card.warn .failure-card-title {
  color: #92400e;
}

.failure-card:not([open]) .failure-card-title,
.failure-card:not([open]) .failure-card-preview {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.failure-card[open] .failure-card-preview {
  display: none;
}

.failure-card-preview {
  margin: 0;
  font-size: 11px;
  line-height: 1.35;
  color: #991b1b;
  font-weight: 400;
}

.failure-card.warn .failure-card-preview {
  color: #92400e;
}

.failure-card-chevron {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--border) 35%, transparent);
  position: relative;
}

.failure-card-chevron::after {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  width: 6px;
  height: 6px;
  border-right: 2px solid var(--muted);
  border-bottom: 2px solid var(--muted);
  transform: translate(-65%, -75%) rotate(45deg);
  transition: transform 0.15s ease;
}

.failure-card[open] .failure-card-chevron::after {
  transform: translate(-65%, -35%) rotate(-135deg);
}

.failure-card-body {
  padding: 0 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.failure-card-body :deep(.failure-card-meta) {
  margin: 0;
}

.failure-card-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 2px;
}

.failure-card-footer :deep(.failure-card-link) {
  border: none;
  background: none;
  padding: 0;
  font: inherit;
  font-size: 12px;
  color: var(--accent);
  cursor: pointer;
  text-decoration: none;
}

.failure-card-footer :deep(.failure-card-link:hover) {
  text-decoration: underline;
}

.muted {
  color: var(--muted);
}

.small {
  font-size: 11px;
}
</style>
