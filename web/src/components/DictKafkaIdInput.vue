<template>
  <div class="dict-id-wrap">
    <input
      ref="inputEl"
      v-model="model"
      type="text"
      class="form-inp mono dict-id-inp"
      :placeholder="placeholder"
      autocomplete="off"
      :aria-expanded="open"
      aria-autocomplete="list"
      :aria-controls="open ? listId : undefined"
      @focus="onFocus"
      @blur="onBlur"
      @input="onInput"
      @keydown="onKeyDown"
    />
    <ul
      v-if="open"
      :id="listId"
      class="dict-id-suggest"
      role="listbox"
      @mousedown.prevent
    >
      <li v-if="loading" class="dict-id-cap muted small">加载数据字典…</li>
      <li v-else-if="loadError" class="dict-id-cap err small">{{ loadError }}</li>
      <li v-else-if="allIds.length === 0" class="dict-id-cap muted small">
        当前环境字典中无{{ kindLabel }}
      </li>
      <li v-else-if="filtered.length === 0" class="dict-id-cap muted small">无匹配项，可继续手动输入</li>
      <li v-else-if="!model?.trim() && allIds.length > maxItems" class="dict-id-cap muted small">
        共 {{ allIds.length }} 条，显示前 {{ maxItems }} 条；输入关键字可过滤
      </li>
      <li
        v-for="(id, i) in filtered"
        :key="id"
        role="option"
        :aria-selected="i === highlightIndex"
      >
        <button
          type="button"
          class="dict-id-item"
          :class="{ active: i === highlightIndex }"
          @mousedown.prevent="select(id)"
        >
          {{ id }}
        </button>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useKafkaDictIds } from "@/composables/useKafkaDictIds";
import { filterKafkaIds } from "@/operations/kafkaDictIds";

const props = withDefaults(
  defineProps<{
    kind: "consumer" | "producer";
    profileCode?: string;
    placeholder?: string;
    maxItems?: number;
  }>(),
  {
    profileCode: "",
    placeholder: "",
    maxItems: 80,
  },
);

const model = defineModel<string>({ required: true });

const inputEl = ref<HTMLInputElement | null>(null);
const open = ref(false);
const highlightIndex = ref(0);
const listId = `dict-kafka-${props.kind}-${Math.random().toString(36).slice(2, 9)}`;

const profileRef = computed(() => props.profileCode ?? "");
const { consumers, producers, loading, error: loadError } = useKafkaDictIds(profileRef);

const kindLabel = computed(() => (props.kind === "consumer" ? "消费者" : "生产者"));

const allIds = computed(() => (props.kind === "consumer" ? consumers.value : producers.value));

const filtered = computed(() =>
  filterKafkaIds(allIds.value, model.value ?? "", props.maxItems),
);

watch(filtered, () => {
  highlightIndex.value = 0;
});

function onFocus() {
  open.value = true;
}

function onBlur() {
  window.setTimeout(() => {
    open.value = false;
  }, 120);
}

function onInput() {
  open.value = true;
}

function select(id: string) {
  model.value = id;
  open.value = false;
  inputEl.value?.blur();
}

function onKeyDown(ev: KeyboardEvent) {
  if (ev.key === "ArrowDown" && !open.value && allIds.value.length > 0) {
    open.value = true;
    ev.preventDefault();
    return;
  }
  if (!open.value || filtered.value.length === 0) return;
  if (ev.key === "ArrowDown") {
    ev.preventDefault();
    highlightIndex.value = (highlightIndex.value + 1) % filtered.value.length;
  } else if (ev.key === "ArrowUp") {
    ev.preventDefault();
    highlightIndex.value =
      (highlightIndex.value - 1 + filtered.value.length) % filtered.value.length;
  } else if (ev.key === "Enter" || ev.key === "Tab") {
    const pick = filtered.value[highlightIndex.value];
    if (pick) {
      ev.preventDefault();
      select(pick);
    }
  } else if (ev.key === "Escape") {
    open.value = false;
  }
}
</script>

<style scoped>
.dict-id-wrap {
  position: relative;
}

.dict-id-inp {
  width: 100%;
}

.dict-id-suggest {
  position: absolute;
  z-index: 40;
  left: 0;
  right: 0;
  top: calc(100% + 4px);
  margin: 0;
  padding: 4px 0;
  list-style: none;
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: 0 8px 24px rgb(15 23 42 / 12%);
}

.dict-id-cap {
  padding: 6px 10px;
  font-size: 11px;
}

.dict-id-item {
  display: block;
  width: 100%;
  border: none;
  background: transparent;
  text-align: left;
  padding: 6px 10px;
  font-size: 12px;
  font-family: inherit;
  color: var(--text);
  cursor: pointer;
}

.dict-id-item:hover,
.dict-id-item.active {
  background: var(--accent-soft);
  color: var(--text);
}

.dict-id-item:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
</style>
