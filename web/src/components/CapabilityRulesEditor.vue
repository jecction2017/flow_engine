<template>
  <div class="cap-rules">
    <div v-if="!rules.length" class="empty-hint">
      <slot name="empty">
        无规则。<button type="button" class="mini" @click="addRule">添加规则</button>
      </slot>
    </div>
    <div v-else class="rule-list">
      <div v-for="(rule, idx) in rules" :key="idx" class="rule-row">
        <div class="rule-grid">
          <label class="field">
            <span class="lbl">类目</span>
            <select
              :value="rule.builtin_category ?? ''"
              class="inp"
              @change="updateField(idx, 'builtin_category', ($event.target as HTMLSelectElement).value || null)"
            >
              <option value="">（任意）</option>
              <option v-for="c in categoryOptions" :key="c" :value="c">{{ c }}</option>
            </select>
          </label>
          <label class="field">
            <span class="lbl">名称</span>
            <select
              :value="rule.builtin_name ?? ''"
              class="inp mono"
              @change="updateField(idx, 'builtin_name', ($event.target as HTMLSelectElement).value || null)"
            >
              <option value="">（按类目匹配）</option>
              <option v-for="n in nameOptionsFor(rule.builtin_category)" :key="n" :value="n">
                {{ n }}
              </option>
            </select>
          </label>
          <label class="field">
            <span class="lbl">动作</span>
            <select
              :value="rule.action"
              class="inp"
              @change="updateField(idx, 'action', ($event.target as HTMLSelectElement).value)"
            >
              <option value="allow">allow（放行）</option>
              <option value="suppress">suppress（抑制）</option>
              <option value="redirect">redirect（改写）</option>
            </select>
          </label>
          <button type="button" class="mini ghost danger" @click="removeRule(idx)">删除</button>
        </div>
        <div v-if="rule.action === 'redirect'" class="redirect-row">
          <span class="lbl">redirect_params (JSON)</span>
          <textarea
            :value="redirectText(rule)"
            class="area mono"
            rows="2"
            spellcheck="false"
            placeholder='{"url": "https://sandbox.example.com/api"}'
            :class="{ invalid: redirectErrors[idx] }"
            @input="onRedirectInput(idx, ($event.target as HTMLTextAreaElement).value)"
          />
          <span v-if="redirectErrors[idx]" class="err">{{ redirectErrors[idx] }}</span>
        </div>
      </div>
      <button type="button" class="mini" @click="addRule">添加规则</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { CapabilityRule } from "@/types/flow";
import { fetchStarlarkRegistry, type RegistryPythonFn } from "@/api/starlark";

const props = defineProps<{
  modelValue: CapabilityRule[] | null | undefined;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: CapabilityRule[]): void;
}>();

const rules = computed<CapabilityRule[]>(() => props.modelValue ?? []);
const redirectErrors = ref<Record<number, string>>({});

// ---------------------------------------------------------------------------
// Builtin metadata loaded once on mount; ``builtin_category`` 与 ``builtin_name``
// 的下拉选项均派生自此，避免用户拼错类目导致规则永不命中。
// ---------------------------------------------------------------------------

const fns = ref<RegistryPythonFn[]>([]);

async function loadRegistry() {
  try {
    const reg = await fetchStarlarkRegistry();
    fns.value = reg.python_functions || [];
  } catch (e) {
    console.warn("Failed to load Starlark registry:", e);
  }
}
void loadRegistry();

const categoryOptions = computed(() => {
  const set = new Set<string>();
  for (const f of fns.value) {
    if (f.category) set.add(f.category);
  }
  return Array.from(set).sort();
});

function nameOptionsFor(category: string | null | undefined): string[] {
  if (!category) return fns.value.map((f) => f.starlark_name).sort();
  return fns.value
    .filter((f) => f.category === category)
    .map((f) => f.starlark_name)
    .sort();
}

// ---------------------------------------------------------------------------
// Edit helpers — 始终通过 emit 而非直接 mutate 父级数组，以便父组件控制持久化。
// ---------------------------------------------------------------------------

function emitRules(next: CapabilityRule[]) {
  emit("update:modelValue", next);
}

function updateField(idx: number, key: keyof CapabilityRule, value: unknown) {
  const next = rules.value.map((r, i) => (i === idx ? { ...r, [key]: value } : r));
  emitRules(next);
}

function addRule() {
  const next: CapabilityRule[] = [
    ...rules.value,
    { builtin_category: null, builtin_name: null, action: "suppress", redirect_params: {} },
  ];
  emitRules(next);
}

function removeRule(idx: number) {
  const next = rules.value.filter((_, i) => i !== idx);
  delete redirectErrors.value[idx];
  emitRules(next);
}

function redirectText(rule: CapabilityRule): string {
  const params = rule.redirect_params || {};
  if (Object.keys(params).length === 0) return "";
  return JSON.stringify(params, null, 2);
}

function onRedirectInput(idx: number, raw: string) {
  if (!raw.trim()) {
    delete redirectErrors.value[idx];
    updateField(idx, "redirect_params", {});
    return;
  }
  try {
    const obj = JSON.parse(raw) as unknown;
    if (typeof obj !== "object" || obj === null || Array.isArray(obj)) {
      redirectErrors.value[idx] = "必须是 JSON 对象";
      return;
    }
    delete redirectErrors.value[idx];
    updateField(idx, "redirect_params", obj as Record<string, unknown>);
  } catch (e) {
    redirectErrors.value[idx] = `JSON 解析失败：${(e as Error).message}`;
  }
}

watch(
  () => rules.value.length,
  () => {
    // 列表长度变化时清掉无对应行的错误，避免误显示。
    const valid: Record<number, string> = {};
    for (const k of Object.keys(redirectErrors.value)) {
      const i = Number(k);
      if (i < rules.value.length) valid[i] = redirectErrors.value[i];
    }
    redirectErrors.value = valid;
  },
);
</script>

<style scoped>
.cap-rules {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.empty-hint {
  font-size: 11.5px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 8px;
}

.rule-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rule-row {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  background: #fbfdff;
}

.rule-grid {
  display: grid;
  grid-template-columns: 1.4fr 1.6fr 1.2fr auto;
  gap: 8px;
  align-items: end;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  font-size: 11.5px;
  color: var(--muted);
}

.lbl {
  font-weight: 500;
  color: #475569;
}

.inp {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 8px;
  font-size: 12px;
  outline: none;
  background: #fff;
  color: var(--text);
  min-width: 0;
}

.inp.mono {
  font-family: var(--mono);
}

.area {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 8px;
  font-size: 11.5px;
  font-family: var(--mono);
  resize: vertical;
  outline: none;
  background: #fff;
  color: var(--text);
}

.area.invalid {
  border-color: #fca5a5;
  background: #fff7f7;
}

.err {
  font-size: 11px;
  color: #b91c1c;
}

.redirect-row {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11px;
  color: var(--muted);
}

.mini {
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 11px;
  cursor: pointer;
  color: var(--muted);
  font-weight: 500;
  transition: all 0.15s ease;
}

.mini:hover:not(:disabled) {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
}

.mini.danger:hover:not(:disabled) {
  color: #b91c1c;
  border-color: #fca5a5;
}

.mini.ghost {
  background: transparent;
}
</style>
