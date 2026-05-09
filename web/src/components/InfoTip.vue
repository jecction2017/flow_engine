<template>
  <span
    ref="anchorEl"
    class="info-tip"
    tabindex="0"
    role="button"
    :aria-label="text"
    @mouseenter="open"
    @mouseleave="close"
    @focus="open"
    @blur="close"
  >
    <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
      <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.4" />
      <circle cx="8" cy="4.6" r="0.95" fill="currentColor" />
      <path d="M8 7v5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
    </svg>
  </span>

  <Teleport to="body">
    <div
      v-if="shown"
      class="fe-tooltip"
      :class="{ wide, 'align-end': alignEnd }"
      :style="bubbleStyles"
      :data-placement="placement"
      role="tooltip"
      aria-live="polite"
    >
      {{ text }}
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps<{
  text: string;
  wide?: boolean;
  /** 气泡右对齐到图标，避免靠右时超出滚动容器（如 flex 行内后跟按钮）。 */
  alignEnd?: boolean;
}>();

const anchorEl = ref<HTMLElement | null>(null);
const shown = ref(false);
const lastOpenAt = ref(0);
const bubbleStyles = ref<Record<string, string>>({});
const placement = ref<"top" | "bottom">("bottom");

const maxWidthCss = computed(() => (props.wide ? "min(320px, calc(100vw - 24px))" : "min(240px, calc(100vw - 24px))"));

const VIEWPORT_MARGIN = 8;

function computeBubbleStyles(anchor: HTMLElement): Record<string, string> {
  const rect = anchor.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  const preferUp = rect.top > vh / 2;
  const gap = 8;
  placement.value = preferUp ? "top" : "bottom";

  const styles: Record<string, string> = {
    position: "fixed",
    zIndex: "2000",
    maxWidth: maxWidthCss.value,
    maxHeight: "min(320px, calc(100vh - 24px))",
    width: "max-content",
    left: "0px",
  };

  // Horizontal placement: center by default; optionally align end (right edge).
  const bubbleMaxWidthPx = props.wide ? 320 : 240;
  const estWidth = Math.min(bubbleMaxWidthPx, vw - 24);

  let left: number;
  if (props.alignEnd) {
    left = rect.right - estWidth;
  } else {
    left = rect.left + rect.width / 2 - estWidth / 2;
  }
  left = Math.max(VIEWPORT_MARGIN, Math.min(left, vw - VIEWPORT_MARGIN - estWidth));
  styles.left = `${Math.round(left)}px`;

  if (preferUp) {
    // IMPORTANT: don't set both top and bottom, or the element will stretch vertically.
    styles.bottom = `${Math.round(vh - rect.top + gap)}px`;
  } else {
    styles.top = `${Math.round(rect.bottom + gap)}px`;
  }

  return styles;
}

function updatePosition() {
  if (!shown.value || !anchorEl.value) return;
  if (!document.body.contains(anchorEl.value)) {
    shown.value = false;
    return;
  }
  bubbleStyles.value = computeBubbleStyles(anchorEl.value);
}

function open() {
  if (!anchorEl.value) return;
  shown.value = true;
  lastOpenAt.value = Date.now();
  updatePosition();
}

function close() {
  // Avoid flicker when focus and mouseleave race.
  if (Date.now() - lastOpenAt.value < 30) return;
  shown.value = false;
}

watch(shown, (v) => {
  if (v) updatePosition();
});

onMounted(() => {
  window.addEventListener("resize", updatePosition);
  window.addEventListener("scroll", updatePosition, true);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", updatePosition);
  window.removeEventListener("scroll", updatePosition, true);
});
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
</style>

<style>
/* Teleported tooltip must be unscoped. */
.fe-tooltip {
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
  text-align: left;
  pointer-events: none;
  overflow: hidden;
  box-shadow: 0 10px 20px -4px rgba(15, 23, 42, 0.25);
  letter-spacing: 0;
  animation: fe-tooltip-in 120ms ease-out;
}

.fe-tooltip::after {
  content: "";
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
}

.fe-tooltip[data-placement="top"]::after {
  bottom: -10px;
  border-top: none;
  border-bottom-color: #0f172a;
}

.fe-tooltip[data-placement="bottom"]::after {
  top: -10px;
  border-bottom: none;
  border-top-color: #0f172a;
}

.fe-tooltip.align-end::after {
  left: auto;
  right: 8px;
  transform: translateX(0);
}

@keyframes fe-tooltip-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
