<template>
  <span
    ref="anchorEl"
    class="info-tip"
    tabindex="0"
    role="button"
    :aria-label="text"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
    @focus="onFocus"
    @blur="onBlur"
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
const bubbleStyles = ref<Record<string, string>>({});
const placement = ref<"top" | "bottom">("bottom");

// 显示状态由"哪些输入源处于激活"派生而来。hover 与 keyboard-focus 是
// 两条独立通道：任一激活则显示，全部失活则隐藏。这样不会出现 open/close
// 互相竞争的 race，因此也不需要时间窗护栏。
type Source = "hover" | "focus";
const sources = new Set<Source>();

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
    // anchor 已经被父组件卸载/隐藏：强制清空所有通道，避免悬空 tooltip。
    reset();
    return;
  }
  bubbleStyles.value = computeBubbleStyles(anchorEl.value);
}

function sync() {
  const next = sources.size > 0;
  if (next === shown.value) return;
  shown.value = next;
  if (next) updatePosition();
}

function activate(source: Source) {
  if (sources.has(source)) return;
  sources.add(source);
  sync();
}

function deactivate(source: Source) {
  if (!sources.has(source)) return;
  sources.delete(source);
  sync();
}

function reset() {
  if (sources.size === 0 && !shown.value) return;
  sources.clear();
  sync();
}

function onMouseEnter() {
  activate("hover");
}

function onMouseLeave() {
  deactivate("hover");
}

function onFocus(event: FocusEvent) {
  // 仅把"键盘聚焦"算作打开来源：鼠标点击带来的隐式 focus 不会命中
  // :focus-visible，所以点击图标后再移开鼠标，浮窗会随 mouseleave 立刻消失，
  // 不会因为图标仍处于 focus 状态而被"钉住"。
  const target = event.target as HTMLElement | null;
  let keyboard = true;
  try {
    if (target && typeof target.matches === "function") {
      keyboard = target.matches(":focus-visible");
    }
  } catch {
    keyboard = true;
  }
  if (keyboard) activate("focus");
}

function onBlur() {
  deactivate("focus");
}

function onWindowBlur() {
  // 窗口/标签失焦或被隐藏时，浏览器不一定派发 mouseleave，主动清空避免卡住。
  reset();
}

function onVisibilityChange() {
  if (document.visibilityState !== "visible") reset();
}

watch(shown, (v) => {
  if (v) updatePosition();
});

onMounted(() => {
  window.addEventListener("resize", updatePosition);
  window.addEventListener("scroll", updatePosition, true);
  window.addEventListener("blur", onWindowBlur);
  document.addEventListener("visibilitychange", onVisibilityChange);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", updatePosition);
  window.removeEventListener("scroll", updatePosition, true);
  window.removeEventListener("blur", onWindowBlur);
  document.removeEventListener("visibilitychange", onVisibilityChange);
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
