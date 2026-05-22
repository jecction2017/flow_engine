<template>
  <!-- 主栏：消费者 + 并发上限 -->
  <div v-if="pane === 'consumer'" class="sub-consumer">
    <label class="form-field full form-field--narrow form-field--narrow-kafka">
      <FormFieldLabel
        label="消费者"
        tech="consumer_id"
        tech-placement="tooltip"
        required
        wide-tip
        tip="数据字典中的完整 ID（集群.主题.消费者名）。选定后将拉取该消费者的字典配置并填入下方参数，可按需修改。"
      />
      <DictKafkaIdInput
        v-model="form.consumer_id"
        kind="consumer"
        :profile-code="envProfileCode"
        placeholder="cluster.topic.consumer"
      />
      <p v-if="dictLoadError" class="err small">{{ dictLoadError }}</p>
    </label>

    <label class="form-field full">
      <FormFieldLabel
        label="同时消费数量上限（单节点）"
        tech="max_in_flight"
        tech-placement="tooltip"
        wide-tip
        tip="最多有多少条消息正在跑流程；满了会暂停拉取（背压）。部署后最常调整的参数之一。"
      />
      <input
        v-model.number="form.max_in_flight"
        type="number"
        min="1"
        max="500"
        class="form-inp mono sub-inp-narrow"
      />
    </label>
  </div>

  <!-- 侧栏：消费参数、映射（默认折叠）等 -->
  <div v-else-if="pane === 'side'" class="sub-side">
    <details class="advanced">
      <summary>消费参数</summary>
      <p class="sub-side-note muted small">
        选择消费者后自动填入字典中的 strategy、分区等；可按需覆盖。未选消费者前起点为空。
      </p>
      <div class="form-grid consume-config-grid">
        <label class="form-field form-field--narrow form-field--narrow-pos">
          <FormFieldLabel
            label="从哪条消息开始读"
            tech="start_position"
            tech-placement="tooltip"
            wide-tip
            tip="「默认」对应 strategy.mode=default：优先消费组已提交位点，无位点时按字典 consumer.params 的 auto_offset_reset。选定消费者后由字典填充，可再改。"
          />
          <select v-model="form.start_position_mode" class="form-inp">
            <option value="">请选择</option>
            <option value="default">默认（消费组位点，否则 auto_offset_reset）</option>
            <option value="latest">仅新消息</option>
            <option value="earliest">从最早可读位置</option>
            <option value="offset">指定分区 offset</option>
            <option value="timestamp">从指定时间</option>
          </select>
        </label>
        <label v-if="form.start_position_mode === 'offset'" class="form-field form-field--narrow form-field--narrow-offset">
          <FormFieldLabel
            label="分区与 offset"
            tech="offsets"
            tech-placement="tooltip"
            required
            tip="格式：分区:offset，多个用逗号分隔，如 0:100, 1:200"
          />
          <input v-model="form.offsetsText" class="form-inp mono" placeholder="0:100, 1:200" />
        </label>
        <div v-if="form.start_position_mode === 'timestamp'" class="sub-ts-row">
          <label class="form-field form-field--narrow form-field--narrow-ts">
            <FormFieldLabel
              label="起始时间"
              tech="timestamp_ms"
              tech-placement="tooltip"
              required
              tip="Unix 毫秒时间戳"
            />
            <input v-model.number="form.timestamp_ms" type="number" min="1" class="form-inp mono" />
          </label>
          <label class="form-field form-field--narrow form-field--narrow-dt">
            <FormFieldLabel label="或选择日期时间" tip="自动填入毫秒时间戳" />
            <input v-model="timestampLocal" type="datetime-local" class="form-inp" @change="onTimestampLocalChange" />
          </label>
        </div>
        <label
          class="form-field form-field--narrow form-field--narrow-part"
          :class="{ 'field-disabled': partitionsDisabled }"
        >
          <FormFieldLabel
            label="只监听部分分区"
            tech="partitions"
            tech-placement="tooltip"
            :tip="
              partitionsDisabled
                ? '与「指定分区 offset」冲突：位点已在「分区与 offset」中指定，此项不可用'
                : '留空=监听该主题全部分区（字典默认）；填写如 0,1,2'
            "
          />
          <input
            v-model="form.partitionsText"
            class="form-inp mono"
            placeholder="1,2,3"
            :disabled="partitionsDisabled"
          />
        </label>
        <label class="form-field">
          <FormFieldLabel
            label="单次最多拉取条数"
            tech="batch_max_records"
            tech-placement="tooltip"
            tip="一次向 Kafka 拉取的上限；每条仍单独触发流程。"
          />
          <input v-model.number="form.batch_max_records" type="number" min="1" max="10000" class="form-inp mono sub-inp-narrow" />
        </label>
        <label class="form-field">
          <FormFieldLabel label="拉取等待上限（毫秒）" tech="poll_timeout_ms" tech-placement="tooltip" />
          <input v-model.number="form.poll_timeout_ms" type="number" min="100" max="60000" class="form-inp mono sub-inp-narrow" />
        </label>
      </div>
    </details>

    <details class="advanced">
      <summary class="summary-with-tip">
        上下文映射（消息体默认注入 <span class="mono">payload</span> 上下文变量）
        <InfoTip
          text="将 Kafka 消息体按下方规则映射为流程入参；未配置映射时，整段消息体默认以 payload 写入上下文。平台还会自动注入 event_meta（主题、分区、offset 等元数据）。与测试中心「方案级上下文映射」使用同一套语义。"
          wide
        />
      </summary>
      <div class="mapping-block">
        <ContextMappingEditor v-model="mapping" surface="ingress" />
      </div>
    </details>

    <details class="advanced">
      <summary>吞吐、失败与容错</summary>
      <div class="form-grid fault-tolerance-grid">
        <label class="form-field full form-field--narrow form-field--narrow-kafka">
          <FormFieldLabel
            label="失败队列（可选）"
            tech="consumption.dlq.producer_id"
            tech-placement="tooltip"
            wide-tip
            tip="处理失败时转发到字典生产者；留空则仅在运行中心记录。"
          />
          <DictKafkaIdInput
            v-model="form.dlq_producer_id"
            kind="producer"
            :profile-code="envProfileCode"
            placeholder="memory.alerts.dlq"
          />
        </label>
        <div class="idempotency-block">
          <label class="form-field full check-row">
            <span class="check">
              <input v-model="form.idempotencyEnabled" type="checkbox" />
              <span>幂等（按 topic + 分区 + offset 去重）</span>
            </span>
          </label>
          <label v-if="form.idempotencyEnabled" class="form-field idempotency-window">
            <FormFieldLabel label="去重窗口（秒）" tech="idempotency.window_s" tech-placement="tooltip" />
            <input v-model.number="form.idempotency_window_s" type="number" min="1" class="form-inp mono sub-inp-narrow" />
          </label>
        </div>
        <label class="form-field">
          <FormFieldLabel label="Ingress 最多重启" tech="ingress_policy.max_restarts" tech-placement="tooltip" />
          <input v-model.number="form.ingress_max_restarts" type="number" min="0" class="form-inp mono sub-inp-narrow" />
        </label>
        <label class="form-field">
          <FormFieldLabel label="重启等待基数（秒）" tech="ingress_policy.restart_backoff_s" tech-placement="tooltip" />
          <input v-model.number="form.ingress_restart_backoff_s" type="number" min="1" class="form-inp mono sub-inp-narrow" />
        </label>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { fetchDictResolved } from "@/api/dict";
import ContextMappingEditor from "@/components/ContextMappingEditor.vue";
import DictKafkaIdInput from "@/components/DictKafkaIdInput.vue";
import FormFieldLabel from "@/components/FormFieldLabel.vue";
import InfoTip from "@/components/InfoTip.vue";
import type { ContextMappingState } from "@/operations/contextMappingConfig";
import {
  applyDictConsumerToForm,
  clearConsumerDerivedFormFields,
  getKafkaConsumerFromDict,
} from "@/operations/kafkaConsumerDict";
import type { SubscriptionFormState } from "@/operations/subscriptionScheduleConfig";

const props = defineProps<{
  pane: "consumer" | "side";
  /** Resolved env profile for dictionary lookup; empty = default profile. */
  envProfileCode?: string;
}>();

const form = defineModel<SubscriptionFormState>("form", { required: true });
const mapping = defineModel<ContextMappingState>("mapping", { required: true });

const timestampLocal = ref("");
const dictLoadError = ref("");
let lastDictLoadKey = "";

const partitionsDisabled = computed(() => form.value.start_position_mode === "offset");

watch(
  () => form.value.start_position_mode,
  (mode) => {
    if (mode === "offset") form.value.partitionsText = "";
  },
);

async function loadConsumerParamsFromDict(consumerId: string) {
  const cid = consumerId.trim();
  if (!cid) {
    lastDictLoadKey = "";
    clearConsumerDerivedFormFields(form.value);
    dictLoadError.value = "";
    return;
  }
  const loadKey = `${props.envProfileCode ?? ""}:${cid}`;
  if (loadKey === lastDictLoadKey) return;
  lastDictLoadKey = loadKey;
  dictLoadError.value = "";
  try {
    const res = await fetchDictResolved(props.envProfileCode?.trim() || undefined);
    const spec = getKafkaConsumerFromDict(res.resolved_dictionary ?? {}, cid);
    if (!spec) {
      dictLoadError.value = `字典中未找到消费者 ${cid}`;
      clearConsumerDerivedFormFields(form.value);
      return;
    }
    applyDictConsumerToForm(form.value, spec);
  } catch (e) {
    dictLoadError.value = e instanceof Error ? e.message : String(e);
    clearConsumerDerivedFormFields(form.value);
  }
}

watch(
  () => [props.envProfileCode, form.value.consumer_id] as const,
  ([, consumerId]) => {
    void loadConsumerParamsFromDict(consumerId);
  },
);

function onTimestampLocalChange() {
  if (!timestampLocal.value) return;
  const ms = new Date(timestampLocal.value).getTime();
  if (Number.isFinite(ms)) form.value.timestamp_ms = ms;
}

watch(
  () => form.value.timestamp_ms,
  (ms) => {
    if (!ms || ms <= 0) {
      timestampLocal.value = "";
      return;
    }
    const d = new Date(ms);
    if (!Number.isFinite(d.getTime())) return;
    const pad = (n: number) => String(n).padStart(2, "0");
    timestampLocal.value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  },
  { immediate: true },
);
</script>

<style scoped>
.sub-consumer {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sub-consumer .sub-inp-narrow {
  width: 120px;
  max-width: 100%;
}

.sub-side {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sub-side-note {
  margin: -4px 0 0;
  line-height: 1.45;
  font-size: 11.5px;
}

.sub-inp-narrow {
  width: 88px;
  max-width: 100%;
}

.consume-config-grid,
.fault-tolerance-grid {
  margin-top: 10px;
  grid-template-columns: 1fr;
}

.sub-ts-row {
  display: grid;
  grid-template-columns: minmax(0, 10.5rem) minmax(0, 14.5rem);
  gap: 10px 12px;
  align-items: end;
}

.field-disabled {
  opacity: 0.55;
}

.field-disabled .form-inp:disabled {
  background: #f1f5f9;
  cursor: not-allowed;
}

@media (max-width: 520px) {
  .sub-ts-row {
    grid-template-columns: 1fr;
  }
}

.idempotency-block {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.idempotency-window {
  max-width: 200px;
}

.mapping-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--border));
  border-radius: 10px;
  background: color-mix(in srgb, var(--accent-soft) 18%, #fff);
}

.check-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text);
}
</style>
