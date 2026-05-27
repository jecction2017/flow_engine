<template>
  <div class="on-error-editor">
    <div v-if="!enabled" class="empty-hint">
      未配置异常处理。<button type="button" class="mini" @click="enable">添加 on_error</button>
    </div>
    <div v-else class="panel">
      <div class="form-grid">
        <label class="field field-span2">
          <span class="lbl-row">
            处理动作 (action)<span class="req">*</span>
            <InfoTip
              wide
              text="retry：按策略 retry_count 重试；jump：跳转目标节点；continue/break：循环内控制流；ignore：吞掉错误并继续；custom：执行脚本后仍按失败传播。"
            />
          </span>
          <select v-model="action" class="inp inp-sel" @change="onActionChange">
            <option value="retry">retry — 重试</option>
            <option value="jump">jump — 跳转</option>
            <option value="continue">continue — 继续迭代</option>
            <option value="break">break — 终止循环</option>
            <option value="ignore">ignore — 忽略错误</option>
            <option value="custom">custom — 自定义脚本</option>
          </select>
        </label>

        <label v-if="action === 'jump'" class="field field-span2">
          <span class="lbl-row">
            跳转目标 (target)<span class="req">*</span>
            <InfoTip
              wide
              text="按节点名称选择目标，保存时写入逻辑 ID；仍受编译期 scope barrier（同层兄弟或祖先）约束。"
            />
          </span>
          <select
            v-model="target"
            class="inp inp-sel"
            :class="{ invalid: !!jumpWarn && !target }"
            @change="emitConfig"
          >
            <option value="">（选择目标节点）</option>
            <option v-for="t in jumpTargets" :key="t.id" :value="t.id">
              {{ t.label }} · {{ t.id }}
            </option>
          </select>
          <span v-if="jumpWarn" class="hint-warn">{{ jumpWarn }}</span>
        </label>

        <div v-if="action === 'custom'" class="field field-span2 nested-block">
          <span class="lbl-row">
            自定义脚本 (script)<span class="req">*</span>
            <InfoTip text="Starlark 脚本；可访问 extra.error（字符串）。执行后仍按失败传播。" />
          </span>
          <div class="editor-wrap">
            <CodeEditor
              v-model="script"
              :height="80"
              :registry="registry"
              :jump-target-suggestions="jumpSuggestionsGetter"
              placeholder='log_info("err", error)'
              @update:model-value="emitConfig"
            />
          </div>
        </div>

        <p v-if="action === 'retry' && retryWarn" class="hint-warn field-span2">{{ retryWarn }}</p>
      </div>
      <div class="panel-foot">
        <button type="button" class="mini ghost danger" @click="disable">移除异常处理</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { ExecutionStrategy, OnErrorAction, OnErrorConfig } from "@/types/flow";
import type { JumpTargetOption } from "@/utils/jumpTargets";
import CodeEditor from "./CodeEditor.vue";
import InfoTip from "./InfoTip.vue";
import type { RegistryPythonFn } from "@/api/starlark";

const props = defineProps<{
  modelValue: OnErrorConfig | null | undefined;
  strategyRef: string;
  strategies: Record<string, ExecutionStrategy>;
  jumpTargets: JumpTargetOption[];
  registry?: RegistryPythonFn[] | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: OnErrorConfig | null): void;
}>();

const enabled = ref(false);
const action = ref<OnErrorAction>("ignore");
const target = ref("");
const script = ref("");

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      enabled.value = true;
      action.value = v.action;
      target.value = v.target ?? "";
      script.value = v.script ?? "";
    }
  },
  { immediate: true, deep: true },
);

const retryWarn = computed(() => {
  if (action.value !== "retry") return "";
  const st = props.strategies[props.strategyRef];
  const rc = st?.retry_count ?? 0;
  if (rc <= 0) {
    return `策略「${props.strategyRef}」的 retry_count 为 0，保存时编译将失败。`;
  }
  return "";
});

const jumpWarn = computed(() => {
  if (action.value !== "jump") return "";
  if (!target.value.trim()) return "jump 必须指定 target。";
  if (!props.jumpTargets.some((t) => t.id === target.value)) {
    return "当前 target 不在允许跳转范围内。";
  }
  return "";
});

function jumpSuggestionsGetter(): readonly JumpTargetOption[] {
  return props.jumpTargets;
}

function emitConfig() {
  if (!enabled.value) {
    emit("update:modelValue", null);
    return;
  }
  const cfg: OnErrorConfig = { action: action.value };
  if (action.value === "jump") {
    cfg.target = target.value.trim() || null;
  } else if (action.value === "custom") {
    cfg.script = script.value.trim() || null;
  }
  emit("update:modelValue", cfg);
}

function onActionChange() {
  if (action.value !== "jump") target.value = "";
  if (action.value !== "custom") script.value = "";
  emitConfig();
}

function enable() {
  enabled.value = true;
  if (!props.modelValue) {
    action.value = "ignore";
    emitConfig();
  }
}

function disable() {
  enabled.value = false;
  emit("update:modelValue", null);
}
</script>

<style scoped>
.on-error-editor {
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
  flex-wrap: wrap;
}

.panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 10px 8px;
  background: #fbfdff;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 12px;
  align-items: start;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  font-size: 12px;
  color: var(--muted);
}

.field-span2 {
  grid-column: 1 / -1;
}

.lbl-row {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  font-weight: 500;
  color: #475569;
  font-size: 12px;
}

.req {
  color: #dc2626;
}

.inp {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 10px;
  outline: none;
  font-size: 12.5px;
  background: #fff;
  color: var(--text);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  min-width: 0;
}

.inp:focus {
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.inp.invalid {
  border-color: #fca5a5;
  background: #fff7f7;
}

.inp-sel {
  width: 100%;
  max-width: 100%;
}

.inp.mono {
  font-family: var(--mono);
}

.nested-block {
  margin-top: 2px;
}

.editor-wrap {
  border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
}

.editor-wrap :deep(.wrap) {
  border: none;
  border-radius: 0;
}

.hint-warn {
  font-size: 11px;
  color: #b45309;
  line-height: 1.45;
  margin-top: 2px;
}

.panel-foot {
  display: flex;
  justify-content: flex-start;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed color-mix(in srgb, var(--border) 75%, transparent);
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

.mini.ghost {
  background: transparent;
}

.mini.danger:hover:not(:disabled) {
  color: #b91c1c;
  border-color: #fca5a5;
}
</style>
