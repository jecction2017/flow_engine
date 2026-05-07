<template>
  <span
    class="info-tip"
    :class="{ 'align-end': alignEnd }"
    tabindex="0"
    role="button"
    :aria-label="text"
  >
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
  /** 气泡右对齐到图标，避免靠右时超出滚动容器（如 flex 行内后跟按钮）。 */
  alignEnd?: boolean;
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
  overflow-wrap: anywhere;
  word-break: break-word;
  width: max-content;
  max-width: min(240px, calc(100vw - 24px));
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
  max-width: min(320px, calc(100vw - 24px));
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

/* 显式右对齐（适用于「图标后还有按钮」等场景，避免 :last-child 不生效） */
.info-tip.align-end .bubble {
  left: auto;
  right: -4px;
  transform: translateX(0) translateY(4px);
}

.info-tip.align-end .bubble::after {
  left: auto;
  right: 8px;
  transform: translateX(0);
}

.info-tip.align-end:hover .bubble,
.info-tip.align-end:focus .bubble {
  transform: translateX(0) translateY(0);
}
</style>
