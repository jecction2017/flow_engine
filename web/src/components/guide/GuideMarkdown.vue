<template>
  <article ref="rootEl" class="guide-md card" v-html="html" />
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import MarkdownIt from "markdown-it";
import DOMPurify from "dompurify";
import { guidePathFromHref } from "@/composables/useGuideDocPath";

const props = defineProps<{
  content: string;
  currentPath: string;
}>();

const emit = defineEmits<{
  (e: "navigate", path: string): void;
}>();

const rootEl = ref<HTMLElement | null>(null);

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
});

const html = computed(() => {
  const raw = md.render(props.content);
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ["target", "rel"],
  });
});

function attachCodeCopyButtons(): void {
  const root = rootEl.value;
  if (!root) return;
  root.querySelectorAll(".guide-code-wrap").forEach((el) => el.remove());

  root.querySelectorAll("pre").forEach((pre) => {
    if (pre.querySelector("code") == null) return;
    const wrap = document.createElement("div");
    wrap.className = "guide-code-wrap";
    const parent = pre.parentNode;
    if (!parent) return;
    parent.insertBefore(wrap, pre);
    wrap.appendChild(pre);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "guide-copy-btn";
    btn.textContent = "复制";
    btn.addEventListener("click", () => {
      const text = pre.textContent ?? "";
      void navigator.clipboard.writeText(text).catch(() => undefined);
    });
    wrap.appendChild(btn);
  });
}

function onClick(ev: MouseEvent): void {
  const target = ev.target as HTMLElement | null;
  const anchor = target?.closest("a");
  if (!anchor) return;
  const href = anchor.getAttribute("href");
  if (!href) return;
  const guidePath = guidePathFromHref(href, props.currentPath);
  if (guidePath == null) return;
  ev.preventDefault();
  emit("navigate", guidePath);
}

watch(
  () => props.content,
  async () => {
    await nextTick();
    attachCodeCopyButtons();
  },
);

onMounted(async () => {
  await nextTick();
  attachCodeCopyButtons();
  rootEl.value?.addEventListener("click", onClick);
});

onBeforeUnmount(() => {
  rootEl.value?.removeEventListener("click", onClick);
});

watch(rootEl, (el, prev) => {
  prev?.removeEventListener("click", onClick);
  el?.addEventListener("click", onClick);
});
</script>

<style scoped>
.guide-md {
  padding: 18px 22px;
  max-width: 900px;
}

.guide-md :deep(h1) {
  margin: 0 0 12px;
  font-size: 22px;
}

.guide-md :deep(h2) {
  margin: 20px 0 8px;
  font-size: 17px;
}

.guide-md :deep(h3) {
  margin: 14px 0 6px;
  font-size: 14px;
}

.guide-md :deep(p),
.guide-md :deep(li) {
  font-size: 13px;
  line-height: 1.55;
}

.guide-md :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin: 10px 0;
}

.guide-md :deep(th),
.guide-md :deep(td) {
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
}

.guide-md :deep(th) {
  background: color-mix(in srgb, var(--bg) 70%, var(--surface));
}

.guide-md :deep(code) {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  background: color-mix(in srgb, var(--bg) 80%, var(--surface));
  padding: 1px 4px;
  border-radius: 4px;
}

.guide-md :deep(pre) {
  margin: 10px 0;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #0f172a;
  color: #e2e8f0;
  overflow: auto;
  font-size: 12px;
}

.guide-md :deep(pre code) {
  background: transparent;
  padding: 0;
  color: inherit;
}

.guide-md :deep(a) {
  color: var(--accent);
}

.guide-md :deep(blockquote) {
  margin: 10px 0;
  padding: 8px 12px;
  border-left: 3px solid var(--accent);
  color: var(--muted);
}

.guide-md :deep(.guide-code-wrap) {
  position: relative;
}

.guide-md :deep(.guide-copy-btn) {
  position: absolute;
  top: 8px;
  right: 8px;
  border: 1px solid #64748b;
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
}

.guide-md :deep(.guide-copy-btn:hover) {
  border-color: #94a3b8;
}
</style>
