<template>
  <div class="lvl">
    <template v-for="(n, i) in nodes" :key="`${n.type}-${i}-${store.nodeId(n)}`">
      <div class="wrap">
        <div
          class="row"
          :class="{ active: isActive([...pathPrefix, i]) }"
          @click="store.select({ kind: 'node', path: [...pathPrefix, i] })"
        >
          <div class="rail-cell" :class="{ 'rail-on': railRole(i) !== 'none' }">
            <template v-if="railRole(i) !== 'none'">
              <div class="rail-track" :class="railRole(i)" aria-hidden="true" />
              <span
                v-if="railRole(i) === 'first'"
                class="rail-hint"
                title="隐式并行组：相邻节点均为非 sync 策略，且下一节点未设 wait_before 屏障"
              >∥</span>
            </template>
          </div>
          <div class="indent" :style="{ width: 10 + depth * 12 + 'px' }" />
          <span class="glyph">{{ glyph(n) }}</span>
          <div class="meta">
            <div class="name mono">{{ store.nodeId(n) }}</div>
            <div class="sub">
              <span class="chip">{{ n.strategy_ref }}</span>
              <span class="mode">{{ store.modeOf(n.strategy_ref) }}</span>
              <span v-if="n.wait_before" class="pill">wait</span>
            </div>
          </div>
          <div class="mini" @click.stop>
            <button type="button" class="iconbtn" title="同级添加" @click="toggleMenu([...pathPrefix, i], 'sibling')">
              +
            </button>
            <button
              v-if="n.type === 'loop' || n.type === 'subflow'"
              type="button"
              class="iconbtn"
              title="子级添加"
              @click="toggleMenu([...pathPrefix, i], 'child')"
            >
              ⊕
            </button>
          </div>
        </div>

        <div v-if="menuPath && pathKey(menuPath) === pathKey([...pathPrefix, i]) && menuOpen" class="menu">
          <button type="button" @click="doAdd('task')">Task</button>
          <button type="button" @click="doAdd('loop')">Loop</button>
          <button type="button" @click="doAdd('subflow')">Subflow</button>
          <button type="button" class="danger" @click="doDelete">删除</button>
        </div>
      </div>

      <div v-if="n.type === 'loop' || n.type === 'subflow'" class="nest">
        <FlowTreeItem :nodes="n.children" :path-prefix="[...pathPrefix, i]" :depth="depth + 1" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { FlowNode } from "@/types/flow";
import { useFlowStudioStore } from "@/stores/flowStudio";
import FlowTreeItem from "./FlowTreeItem.vue";

const props = defineProps<{
  nodes: FlowNode[];
  pathPrefix: number[];
  depth: number;
}>();

const store = useFlowStudioStore();

type Rail = "none" | "first" | "middle" | "last";

const railRoles = computed(() => {
  const roles: Record<number, Rail> = {};
  for (const r of store.parallelGroupRanges(props.nodes)) {
    if (r.end <= r.start) continue;
    for (let k = r.start; k <= r.end; k++) {
      if (k === r.start) roles[k] = "first";
      else if (k === r.end) roles[k] = "last";
      else roles[k] = "middle";
    }
  }
  return roles;
});

function railRole(i: number): Rail {
  return railRoles.value[i] ?? "none";
}

const menuOpen = ref(false);
const menuPath = ref<number[] | null>(null);
const menuKind = ref<"sibling" | "child" | null>(null);

function pathKey(p: number[]) {
  return p.join("/");
}

function isActive(path: number[]) {
  return store.selection.kind === "node" && pathKey(store.selection.path) === pathKey(path);
}

function glyph(n: FlowNode) {
  if (n.type === "task") return "▫";
  if (n.type === "loop") return "↺";
  return "⎆";
}

function toggleMenu(path: number[], kind: "sibling" | "child") {
  if (
    menuOpen.value &&
    menuPath.value &&
    pathKey(menuPath.value) === pathKey(path) &&
    menuKind.value === kind
  ) {
    menuOpen.value = false;
    menuPath.value = null;
    menuKind.value = null;
    return;
  }
  menuPath.value = path;
  menuKind.value = kind;
  menuOpen.value = true;
}

function doAdd(kind: "task" | "loop" | "subflow") {
  if (!menuPath.value || !menuKind.value) return;
  if (menuKind.value === "child") store.addChild(menuPath.value, kind);
  else store.addSibling(menuPath.value, kind);
  menuOpen.value = false;
  menuPath.value = null;
  menuKind.value = null;
}

function doDelete() {
  if (!menuPath.value) return;
  store.removeNode(menuPath.value);
  menuOpen.value = false;
  menuPath.value = null;
  menuKind.value = null;
}
</script>

<style scoped>
.lvl {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.wrap {
  position: relative;
}

.row {
  display: flex;
  align-items: stretch;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 8px;
  border: 1px solid transparent;
  cursor: pointer;
}

.rail-cell {
  position: relative;
  width: 20px;
  flex-shrink: 0;
  align-self: stretch;
  min-height: 34px;
}

.rail-cell.rail-on {
  width: 22px;
}

.rail-track {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  width: 3px;
  border-radius: 3px;
  background: linear-gradient(180deg, #2563eb, #6366f1);
  box-shadow: 0 0 0 1px color-mix(in srgb, #2563eb 22%, transparent);
  pointer-events: none;
}

.rail-track.first {
  top: 50%;
  bottom: 0;
}

.rail-track.middle {
  top: 0;
  bottom: 0;
}

.rail-track.last {
  top: 0;
  bottom: 50%;
}

.rail-hint {
  position: absolute;
  left: 0;
  top: 6px;
  font-size: 11px;
  font-weight: 800;
  color: #2563eb;
  line-height: 1;
  pointer-events: auto;
  z-index: 1;
}

.row:hover {
  background: color-mix(in srgb, var(--surface) 88%, var(--accent-soft));
  border-color: color-mix(in srgb, var(--border) 70%, transparent);
}

.row.active {
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 28%, transparent);
}

.indent {
  flex: 0 0 auto;
  align-self: center;
}

.row > .glyph {
  align-self: center;
}

.glyph {
  width: 18px;
  text-align: center;
  color: var(--muted);
  flex: 0 0 auto;
}

.meta {
  min-width: 0;
  flex: 1;
  align-self: center;
}

.name {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sub {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}

.chip {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--muted);
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mode {
  font-size: 10px;
  color: var(--muted);
}

.pill {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--warn) 35%, transparent);
  color: var(--warn);
  background: color-mix(in srgb, var(--warn) 10%, transparent);
}

.mini {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.12s ease;
  align-self: center;
}

.row:hover .mini {
  opacity: 1;
}

.iconbtn {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  cursor: pointer;
  line-height: 1;
  font-size: 14px;
}

.nest {
  margin-left: 10px;
  padding-left: 8px;
  border-left: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
}

.menu {
  position: absolute;
  right: 6px;
  top: 34px;
  z-index: 6;
  display: grid;
  gap: 4px;
  padding: 8px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.12);
}

.menu button {
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
  text-align: left;
}

.menu button.danger {
  border-color: color-mix(in srgb, #ef4444 35%, transparent);
  color: #b91c1c;
}
</style>
