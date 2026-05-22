<template>
  <div class="ctx-map" :class="`ctx-map--${surface}`">
    <label class="ctx-map-field" :class="{ 'ctx-map-field--mode': surface === 'ingress' }">
      <FormFieldLabel
        v-if="surface === 'ingress'"
        label="映射方式"
        tech="parse.transform / mapping.mode"
        tech-placement="tooltip"
        wide-tip
        tip="展开、打包、按字段映射、自定义 Starlark 脚本四选一；与测试中心上下文映射一致。"
      />
      <span v-else class="ctx-map-lbl">映射方式</span>
      <select v-model="mappingMode" class="ctx-map-inp">
        <option v-for="opt in modeOptions" :key="opt.value" :value="opt.value">
          {{ opt.tech }} · {{ opt.label }}
        </option>
      </select>
    </label>

    <p class="ctx-map-hint muted small">{{ modeHint }}</p>

    <div v-if="mapping.mode === 'wrap'" class="ctx-map-wrap-grid">
      <label class="ctx-map-field">
        <FormFieldLabel
          v-if="surface === 'ingress'"
          label="流程变量名"
          tech="wrap_key"
          tech-placement="tooltip"
          required
          :tip="`写入流程的变量名，如 ${effectiveWrapKey}.id`"
        />
        <span v-else class="ctx-map-lbl">变量名 <em class="req">*</em></span>
        <input v-model="wrapKey" class="ctx-map-inp mono" :placeholder="wrapKeyPlaceholder" />
      </label>
      <label class="ctx-map-check">
        <span class="check">
          <input v-model="wrapAsList" type="checkbox" />
          <span>作为数组写入（{key: [row]}）</span>
        </span>
      </label>
    </div>

    <div v-if="mapping.mode === 'rules'" class="ctx-map-rules">
      <div class="ctx-map-rules-head">
        <span class="muted small">{{ rulesCaption }}</span>
        <button type="button" class="ctx-map-btn sm ghost" @click="addRule">+ 添加</button>
      </div>
      <div v-for="(r, i) in rules" :key="i" class="ctx-map-rules-row">
        <input v-model="r.source" class="ctx-map-inp mono" placeholder="alert_id" />
        <span class="ctx-map-arrow">→</span>
        <input v-model="r.target" class="ctx-map-inp mono" placeholder="case.id" />
        <button type="button" class="ctx-map-btn sm ghost" title="删除" @click="removeRule(i)">×</button>
      </div>
    </div>

    <label v-if="mapping.mode === 'script'" class="ctx-map-field full">
      <FormFieldLabel
        v-if="surface === 'ingress'"
        label="Starlark 脚本"
        tech="parse.script"
        tech-placement="tooltip"
        show-tech
        required
        wide-tip
        tip="须返回 dict；全局变量 payload 为解码后的消息 JSON。"
      />
      <span v-else class="ctx-map-lbl">Starlark 脚本 <em class="req">*</em></span>
      <span v-if="surface === 'test'" class="ctx-map-lbl-sub muted small">全局变量 payload = lookup 行 / 样例 JSON</span>
      <textarea v-model="scriptText" class="ctx-map-area mono" rows="6" spellcheck="false" />
    </label>

    <template v-if="showSamplePreview && mapping.mode !== 'script'">
      <label class="ctx-map-field full">
        <span class="ctx-map-lbl">{{ sampleCaption }}</span>
        <textarea v-model="sampleText" class="ctx-map-area mono" rows="4" spellcheck="false" />
      </label>
      <label class="ctx-map-field full">
        <span class="ctx-map-lbl">{{ previewCaption }}</span>
        <textarea :value="previewText" class="ctx-map-area mono ctx-map-preview" rows="5" readonly spellcheck="false" />
      </label>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import FormFieldLabel from "@/components/FormFieldLabel.vue";
import { previewContextMapping } from "@/testCenter/mappingPreview";
import {
  MAPPING_MODE_OPTIONS,
  MAPPING_SAMPLE_JSON,
  createMappingForMode,
  defaultWrapKey,
  mappingModeHint,
  type ContextMappingMode,
  type ContextMappingState,
  type MappingSurface,
} from "@/operations/contextMappingConfig";

const props = withDefaults(
  defineProps<{
    /** test = 测试中心；ingress = 消息订阅部署 */
    surface: MappingSurface;
    showSamplePreview?: boolean;
  }>(),
  { showSamplePreview: true },
);

const mapping = defineModel<ContextMappingState>({ required: true });

const sampleText = ref(MAPPING_SAMPLE_JSON);

const modeOptions = MAPPING_MODE_OPTIONS;

const mappingMode = computed({
  get: (): ContextMappingMode => mapping.value.mode,
  set: (mode: ContextMappingMode) => {
    mapping.value = createMappingForMode(mode, props.surface, mapping.value);
    if (mode !== "script") sampleText.value = MAPPING_SAMPLE_JSON;
  },
});

const wrapKeyPlaceholder = computed(() => defaultWrapKey(props.surface));

const effectiveWrapKey = computed(() =>
  mapping.value.mode === "wrap"
    ? mapping.value.wrap_key.trim() || wrapKeyPlaceholder.value
    : wrapKeyPlaceholder.value,
);

const modeHint = computed(() => mappingModeHint(mapping.value.mode, effectiveWrapKey.value, props.surface));

const rulesCaption = computed(() =>
  props.surface === "ingress" ? "消息字段 → 流程变量" : "来源字段 → 流程变量",
);

const sampleCaption = computed(() =>
  props.surface === "ingress" ? "样例消息 JSON" : "样例输入 JSON（lookup 行或消息体）",
);

const previewCaption = computed(() =>
  props.surface === "ingress" ? "预览：映射后流程变量" : "预览：映射后 context",
);

const wrapKey = computed({
  get: () => (mapping.value.mode === "wrap" ? mapping.value.wrap_key : ""),
  set: (v: string) => {
    if (mapping.value.mode === "wrap") mapping.value.wrap_key = v;
  },
});

const wrapAsList = computed({
  get: () => mapping.value.mode === "wrap" && !!mapping.value.wrap_as_list,
  set: (v: boolean) => {
    if (mapping.value.mode === "wrap") mapping.value.wrap_as_list = v;
  },
});

const rules = computed({
  get: () => (mapping.value.mode === "rules" ? mapping.value.rules : []),
  set: (r: Array<{ source: string; target: string }>) => {
    if (mapping.value.mode === "rules") mapping.value.rules = r;
  },
});

const scriptText = computed({
  get: () => (mapping.value.mode === "script" ? mapping.value.script : ""),
  set: (v: string) => {
    if (mapping.value.mode === "script") mapping.value.script = v;
  },
});

function addRule() {
  if (mapping.value.mode !== "rules") return;
  mapping.value.rules.push({ source: "", target: "" });
}

function removeRule(i: number) {
  if (mapping.value.mode !== "rules") return;
  mapping.value.rules.splice(i, 1);
}

const previewText = computed(() => {
  if (mapping.value.mode === "script") {
    return "自定义映射（Starlark）无静态预览；运行/批次执行时由脚本基于 payload 生成流程变量。";
  }
  try {
    const row = JSON.parse(sampleText.value || "{}") as Record<string, unknown>;
    const mapped = previewContextMapping(row, mapping.value);
    if (props.surface === "ingress") {
      return JSON.stringify(
        {
          ...mapped,
          event_meta: {
            topic: "(示例)",
            partition: 0,
            offset: 0,
            message_id: "topic:0:0",
            correlation_id: "(运行后生成)",
          },
        },
        null,
        2,
      );
    }
    return JSON.stringify(mapped, null, 2);
  } catch (e) {
    return `预览失败：${e instanceof Error ? e.message : String(e)}`;
  }
});
</script>

<style scoped>
.ctx-map {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ctx-map-field {
  display: grid;
  gap: 4px;
  font-size: 11px;
  color: var(--muted);
}

.ctx-map-field.full {
  width: 100%;
}

.ctx-map-lbl {
  font-size: 11px;
  color: var(--muted);
}

.ctx-map-lbl .req {
  color: #dc2626;
  font-style: normal;
}

.ctx-map-lbl-sub {
  grid-column: 1 / -1;
  margin-top: -2px;
}

.ctx-map-inp {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  background: var(--surface);
  color: var(--text);
}

.ctx-map-area {
  width: 100%;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  background: var(--surface);
  color: var(--text);
  resize: vertical;
}

.ctx-map-preview {
  background: color-mix(in srgb, var(--accent-soft) 35%, white);
}

.ctx-map-hint {
  margin: -4px 0 0;
  line-height: 1.45;
}

.ctx-map-wrap-grid {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px 12px;
  align-items: end;
}

.ctx-map-check {
  display: flex;
  align-items: center;
  padding-bottom: 6px;
}

.check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text);
}

.ctx-map-rules {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ctx-map-rules-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.ctx-map-rules-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr auto;
  gap: 6px;
  align-items: center;
}

.ctx-map-arrow {
  color: var(--muted);
  font-size: 12px;
}

.ctx-map-btn {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
}

.ctx-map-btn.ghost:hover {
  background: #f1f5f9;
}

.ctx-map--ingress .ctx-map-inp,
.ctx-map--ingress .ctx-map-area {
  /* 与 form-page 一致时可由父级覆盖 */
}

.ctx-map--test .ctx-map-inp,
.ctx-map--test .ctx-map-area {
  /* 嵌入测试中心 details 时沿用局部样式 */
}
</style>
