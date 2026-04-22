<template>
  <div class="lvl">
    <template v-for="(n, i) in nodes" :key="`${n.type}-${i}-${store.nodeId(n)}`">
      <div
        class="wrap"
        :class="railRole(i) !== 'none' ? `rail-${railRole(i)}` : ''"
        :style="railRole(i) !== 'none' ? { '--rail-left': `${34 + depth * 12}px` } : undefined"
        :title="railRole(i) === 'first' ? '隐式并行组：相邻节点均为非 sync 策略，且下一节点未设 wait_before 屏障' : undefined"
        v-show="!store.searchQuery || isNodeMatched([...pathPrefix, i]) || isChildMatched([...pathPrefix, i]) || isParentMatched([...pathPrefix, i])"
      >
        <div
          class="row"
          :class="{ 
            active: isActive([...pathPrefix, i]),
            'search-match': store.searchQuery && isNodeMatched([...pathPrefix, i])
          }"
          @click="store.select({ kind: 'node', path: [...pathPrefix, i] })"
        >
          <div class="indent" :style="{ width: 10 + depth * 12 + 'px' }" />
          <span 
            v-if="n.type === 'loop' || n.type === 'subflow'" 
            class="fold-arrow"
            @click.stop="toggleFold([...pathPrefix, i])"
          >
            {{ isFolded([...pathPrefix, i]) ? '▶' : '▼' }}
          </span>
          <span v-else class="fold-arrow placeholder"></span>
          <div class="meta">
            <div class="name" :title="store.nodeId(n)">
              {{ store.displayName(n) }}
              <span v-if="store.isNodeDirty([...pathPrefix, i])" class="dirty-dot" title="该节点有未保存修改">●</span>
            </div>
            <div class="sub">
              <span class="type-badge">{{ n.type }}</span>
              <span class="mode-badge" :class="store.modeOf(n.strategy_ref)">{{ store.modeOf(n.strategy_ref) }}</span>
              <span v-if="n.wait_before" class="pill">wait</span>
            </div>
          </div>
          <div class="mini" @click.stop>
            <button type="button" class="iconbtn" title="更多操作" @click="toggleMenu([...pathPrefix, i], 'more', $event)">
              ···
            </button>
          </div>
        </div>

        <template v-if="menuPath && pathKey(menuPath) === pathKey([...pathPrefix, i]) && menuOpen">
          <Teleport to="body">
            <div class="flow-tree-item-menu-overlay" @click.stop="closeMenu" @contextmenu.prevent="closeMenu"></div>
            <div class="flow-tree-item-menu" :style="menuStyles" @click.stop>
              <button type="button" @click="doAdd('task')">添加平级 Task</button>
              <button type="button" @click="doAdd('loop')">添加平级 Loop</button>
              <button type="button" @click="doAdd('subflow')">添加平级 Subflow</button>

              <template v-if="n.type === 'loop' || n.type === 'subflow'">
                <div class="divider"></div>
                <button type="button" @click="doAddChild('task')">添加子级 Task</button>
                <button type="button" @click="doAddChild('loop')">添加子级 Loop</button>
                <button type="button" @click="doAddChild('subflow')">添加子级 Subflow</button>
              </template>

              <div class="divider"></div>
              <button type="button" @click="doCopy">复制</button>
              <button type="button" @click="doMoveUp">上移</button>
              <button type="button" @click="doMoveDown">下移</button>
              <button type="button" class="danger" @click="doDelete">删除</button>
            </div>
          </Teleport>
        </template>
      </div>

      <div v-show="!isFolded([...pathPrefix, i]) || (store.searchQuery && isChildMatched([...pathPrefix, i]))" v-if="n.type === 'loop' || n.type === 'subflow'" class="nest">
        <FlowTreeItem :nodes="n.children" :path-prefix="[...pathPrefix, i]" :depth="depth + 1" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onBeforeUnmount, onMounted } from "vue";
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
const menuKind = ref<"more" | null>(null);
const menuStyles = ref<Record<string, string>>({});
const menuAnchorEl = ref<HTMLElement | null>(null);

const MENU_WIDTH = 160;
const MENU_MAX_HEIGHT = 300;
const VIEWPORT_MARGIN = 8;

function computeMenuStyles(anchor: HTMLElement) {
  const rect = anchor.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  const spaceBelow = vh - rect.bottom;
  const spaceAbove = rect.top;
  const preferUp = spaceBelow < 220 && spaceAbove > spaceBelow;

  const styles: Record<string, string> = {
    position: 'fixed',
    zIndex: '1000',
    width: `${MENU_WIDTH}px`,
  };

  let left = rect.right - MENU_WIDTH;
  if (left < VIEWPORT_MARGIN) left = VIEWPORT_MARGIN;
  if (left + MENU_WIDTH > vw - VIEWPORT_MARGIN) left = vw - MENU_WIDTH - VIEWPORT_MARGIN;
  styles.left = `${left}px`;

  if (preferUp) {
    const available = Math.max(80, spaceAbove - VIEWPORT_MARGIN);
    const maxH = Math.min(MENU_MAX_HEIGHT, available);
    styles.bottom = `${vh - rect.top + 4}px`;
    styles.maxHeight = `${maxH}px`;
  } else {
    const available = Math.max(80, spaceBelow - VIEWPORT_MARGIN);
    const maxH = Math.min(MENU_MAX_HEIGHT, available);
    styles.top = `${rect.bottom + 4}px`;
    styles.maxHeight = `${maxH}px`;
  }
  styles.overflowY = 'auto';

  return styles;
}

function updateMenuPosition() {
  if (!menuOpen.value || !menuAnchorEl.value) return;
  if (!document.body.contains(menuAnchorEl.value)) {
    closeMenu();
    return;
  }
  menuStyles.value = computeMenuStyles(menuAnchorEl.value);
}

onMounted(() => {
  window.addEventListener('resize', updateMenuPosition);
  window.addEventListener('scroll', updateMenuPosition, true);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateMenuPosition);
  window.removeEventListener('scroll', updateMenuPosition, true);
});

// 树的折叠状态：存储已折叠的节点 pathKey
const foldedPaths = ref<Set<string>>(new Set());

function isFolded(path: number[]) {
  return foldedPaths.value.has(pathKey(path));
}

function toggleFold(path: number[]) {
  const key = pathKey(path);
  if (foldedPaths.value.has(key)) {
    foldedPaths.value.delete(key);
  } else {
    foldedPaths.value.add(key);
  }
}

function isNodeMatched(path: number[]) {
  const q = store.searchQuery.toLowerCase();
  if (!q) return false;
  
  const node = store.getNode(path);
  if (!node) return false;
  
  const id = store.nodeId(node) || "";
  const name = store.displayName(node) || "";
  
  return id.toLowerCase().includes(q) || name.toLowerCase().includes(q);
}

function isChildMatched(path: number[]) {
  const q = store.searchQuery.toLowerCase();
  if (!q) return false;
  
  const node = store.getNode(path);
  if (!node || (node.type !== "loop" && node.type !== "subflow")) return false;
  
  const checkChildren = (n: FlowNode): boolean => {
    if (n.type !== "loop" && n.type !== "subflow") return false;
    
    for (const child of n.children) {
      const id = store.nodeId(child) || "";
      const name = store.displayName(child) || "";
      if (id.toLowerCase().includes(q) || name.toLowerCase().includes(q)) return true;
      
      if (checkChildren(child)) return true;
    }
    return false;
  };
  
  return checkChildren(node);
}

function isParentMatched(path: number[]) {
  const q = store.searchQuery.toLowerCase();
  if (!q || path.length <= 1) return false;
  
  // Check if any ancestor matches the query
  for (let i = 1; i < path.length; i++) {
    const parentPath = path.slice(0, i);
    if (isNodeMatched(parentPath)) return true;
  }
  
  return false;
}

function pathKey(p: number[]) {
  return p.join("/");
}

function isActive(path: number[]) {
  return store.selection.kind === "node" && pathKey(store.selection.path) === pathKey(path);
}

function toggleMenu(path: number[], kind: "more", event: MouseEvent) {
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
  
  const target = event.currentTarget as HTMLElement;
  menuAnchorEl.value = target;
  menuStyles.value = computeMenuStyles(target);
  menuPath.value = path;
  menuKind.value = kind;
  menuOpen.value = true;
}

function doAdd(kind: "task" | "loop" | "subflow") {
  if (!menuPath.value || !menuKind.value) return;
  store.addSibling(menuPath.value, kind);
  closeMenu();
}

function doAddChild(kind: "task" | "loop" | "subflow") {
  if (!menuPath.value || !menuKind.value) return;
  store.addChild(menuPath.value, kind);
  closeMenu();
}

function doCopy() {
  if (!menuPath.value) return;
  store.copyNode(menuPath.value);
  closeMenu();
}

function doMoveUp() {
  if (!menuPath.value) return;
  store.moveNodeUp(menuPath.value);
  closeMenu();
}

function doMoveDown() {
  if (!menuPath.value) return;
  store.moveNodeDown(menuPath.value);
  closeMenu();
}

function doDelete() {
  if (!menuPath.value) return;
  store.removeNode(menuPath.value);
  closeMenu();
}

function closeMenu() {
  menuOpen.value = false;
  menuPath.value = null;
  menuKind.value = null;
  menuAnchorEl.value = null;
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

/* Parallel-group rail: a continuous 2px bar placed just before the node name,
 * aligned with the current indent depth via the --rail-left CSS variable.
 * First/last segments have rounded caps; middle/first/... extend into the
 * inter-row gap (bottom: -2px) so there are no visual breaks. */
.wrap.rail-first::before,
.wrap.rail-middle::before,
.wrap.rail-last::before {
  content: "";
  position: absolute;
  left: var(--rail-left, 12px);
  width: 2px;
  background: linear-gradient(180deg, #3b82f6, #6366f1);
  pointer-events: none;
  z-index: 1;
}

.wrap.rail-first::before {
  top: 10px;
  bottom: -2px;
  border-top-left-radius: 2px;
  border-top-right-radius: 2px;
}

.wrap.rail-middle::before {
  top: 0;
  bottom: -2px;
}

.wrap.rail-last::before {
  top: 0;
  bottom: 10px;
  border-bottom-left-radius: 2px;
  border-bottom-right-radius: 2px;
}

.row {
  display: flex;
  align-items: stretch;
  gap: 4px;
  padding: 2px 6px;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
}

.row:hover {
  background: color-mix(in srgb, var(--surface) 88%, var(--accent-soft));
  border-color: color-mix(in srgb, var(--border) 70%, transparent);
}

.row.active {
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 28%, transparent);
}

.row.search-match {
  background: color-mix(in srgb, #fef08a 30%, transparent); /* Tailwind yellow-200 */
}

.row.search-match.active {
  background: color-mix(in srgb, #fde047 40%, var(--accent-soft)); /* Tailwind yellow-300 + accent */
  border-color: color-mix(in srgb, #eab308 40%, transparent); /* Tailwind yellow-500 */
}

.indent {
  flex: 0 0 auto;
  align-self: center;
}

.row > .meta {
  align-self: center;
}

.meta {
  min-width: 0;
  flex: 1;
  align-self: center;
  line-height: 1.2;
}

.name {
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dirty-dot {
  margin-left: 4px;
  color: #f59e0b;
  font-size: 8px;
  vertical-align: middle;
}

.sub {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 3px;
  align-items: center;
}

.type-badge {
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--border) 40%, transparent);
  color: var(--muted);
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.mode-badge {
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 4px;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.mode-badge.sync {
  background: color-mix(in srgb, var(--success) 12%, transparent);
  color: color-mix(in srgb, var(--success) 80%, var(--text));
  border: 1px solid color-mix(in srgb, var(--success) 30%, transparent);
}

.mode-badge.async {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  color: color-mix(in srgb, var(--accent) 80%, var(--text));
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
}

.mode-badge.process {
  background: color-mix(in srgb, #8b5cf6 12%, transparent); /* purple */
  color: color-mix(in srgb, #8b5cf6 80%, var(--text));
  border: 1px solid color-mix(in srgb, #8b5cf6 30%, transparent);
}

.mode-badge.thread {
  background: color-mix(in srgb, #f59e0b 12%, transparent); /* amber */
  color: color-mix(in srgb, #f59e0b 80%, var(--text));
  border: 1px solid color-mix(in srgb, #f59e0b 30%, transparent);
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
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  line-height: 1;
  font-size: 14px;
  font-weight: bold;
  color: var(--muted);
  display: flex;
  align-items: center;
  justify-content: center;
}

.iconbtn:hover {
  background: var(--surface);
  border-color: var(--border);
  color: var(--text);
}

.nest {
  margin-left: 10px;
  padding-left: 8px;
}

.fold-arrow {
  display: inline-block;
  width: 14px;
  text-align: center;
  font-size: 9px;
  color: var(--muted);
  cursor: pointer;
  user-select: none;
  flex: 0 0 auto;
}

.fold-arrow:hover {
  color: var(--text);
}

.fold-arrow.placeholder {
  cursor: default;
}
</style>

<style>
/* Menu is teleported to <body>, so these styles must be unscoped */
.flow-tree-item-menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 999;
  background: transparent;
  cursor: default;
}

.flow-tree-item-menu {
  display: grid;
  gap: 2px;
  padding: 6px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.18);
  min-width: 140px;
  box-sizing: border-box;
}

.flow-tree-item-menu button {
  border: none;
  background: transparent;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 11px;
  cursor: pointer;
  text-align: left;
  color: var(--text);
}

.flow-tree-item-menu button:hover {
  background: var(--accent-soft);
  color: var(--accent);
}

.flow-tree-item-menu button.danger {
  color: #ef4444;
}

.flow-tree-item-menu button.danger:hover {
  background: color-mix(in srgb, #ef4444 10%, transparent);
  color: #ef4444;
}

.flow-tree-item-menu .divider {
  height: 1px;
  background: var(--border);
  margin: 4px 0;
}
</style>
