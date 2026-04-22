<template>
  <span class="info-tip" tabindex="0" role="button" :aria-label="text">
    <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
      <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.4" />
      <circle cx="8" cy="4.6" r="0.95" fill="currentColor" />
      <path d="M8 7v5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
    </svg>
    <span class="bubble" :class="{ wide }">{{ text }}</span>
  </span>
</template>

<script setup lang="ts">
defineProps<{
  text: string;
  wide?: boolean;
}>();
</script>

<style scoped>
.info-tip {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: 4px;
  color: var(--muted);
  cursor: help;
  outline: none;
  vertical-align: middle;
  flex-shrink: 0;
}

.info-tip:hover,
.info-tip:focus {
  color: var(--accent);
}

.bubble {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%) translateY(4px);
  background: #0f172a;
  color: #f8fafc;
  padding: 7px 10px;
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.55;
  font-weight: 400;
  white-space: normal;
  width: max-content;
  max-width: 240px;
  text-align: left;
  z-index: 1000;
  pointer-events: none;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.12s ease, transform 0.12s ease, visibility 0.12s;
  box-shadow: 0 10px 20px -4px rgba(15, 23, 42, 0.25);
  letter-spacing: 0;
}

.bubble.wide {
  max-width: 320px;
}

.bubble::after {
  content: "";
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: #0f172a;
}

.info-tip:hover .bubble,
.info-tip:focus .bubble {
  opacity: 1;
  visibility: visible;
  transform: translateX(-50%) translateY(0);
}

/* keep bubble inside viewport on rightmost fields */
.info-tip:last-child .bubble {
  left: auto;
  right: -4px;
  transform: translateX(0) translateY(4px);
}

.info-tip:last-child .bubble::after {
  left: auto;
  right: 8px;
  transform: translateX(0);
}

.info-tip:last-child:hover .bubble,
.info-tip:last-child:focus .bubble {
  transform: translateX(0) translateY(0);
}
</style>
