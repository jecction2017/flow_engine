<template>
  <!-- 主栏：消费者 + 并发上限 -->
  <div v-if="pane === 'consumer'" class="sub-consumer">
    <label class="form-field full">
      <FormFieldLabel
        label="消费者"
        tech="consumer_id"
        tech-placement="tooltip"
        required
        wide-tip
        tip="数据字典中的完整 ID（集群.主题.消费者名）。消费起点、分区范围等默认沿用字典中该消费者的配置。"
      />
      <input v-model="form.consumer_id" class="form-inp mono" placeholder="memory.alerts.default" />
    </label>

    <label class="form-field full sub-max-in-flight">
      <FormFieldLabel
        label="同时处理条数上限"
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
        默认沿用数据字典；仅特殊上线场景需要覆盖起点、分区或拉取参数。
      </p>
      <div class="form-grid consume-config-grid">
        <label class="form-field full">
          <FormFieldLabel
            label="从哪条消息开始读"
            tech="start_position"
            tech-placement="tooltip"
            wide-tip
            tip="默认=消费组已保存进度。仅新消息 / 最早 / offset / 时间点见下方联动项。"
          />
          <select v-model="form.start_position_mode" class="form-inp">
            <option value="default">默认（消费组进度 / 字典）</option>
            <option value="latest">仅新消息</option>
            <option value="earliest">从最早可读位置</option>
            <option value="offset">指定分区 offset</option>
            <option value="timestamp">从指定时间</option>
          </select>
        </label>
        <label v-if="form.start_position_mode === 'offset'" class="form-field full">
          <FormFieldLabel
            label="分区与 offset"
            tech="offsets"
            tech-placement="tooltip"
            required
            tip="格式：分区:offset，多个用逗号分隔，如 0:100, 1:200"
          />
          <input v-model="form.offsetsText" class="form-inp mono" placeholder="0:100, 1:200" />
        </label>
        <label v-if="form.start_position_mode === 'timestamp'" class="form-field">
          <FormFieldLabel
            label="起始时间"
            tech="timestamp_ms"
            tech-placement="tooltip"
            required
            tip="Unix 毫秒时间戳"
          />
          <input v-model.number="form.timestamp_ms" type="number" min="1" class="form-inp mono" />
        </label>
        <label v-if="form.start_position_mode === 'timestamp'" class="form-field">
          <FormFieldLabel label="或选择日期时间" tip="自动填入毫秒时间戳" />
          <input v-model="timestampLocal" type="datetime-local" class="form-inp" @change="onTimestampLocalChange" />
        </label>
        <label class="form-field full">
          <FormFieldLabel
            label="只监听部分分区"
            tech="partitions"
            tech-placement="tooltip"
            tip="留空=监听该主题全部分区（字典默认）；填写如 0,1,2"
          />
          <input v-model="form.partitionsText" class="form-inp mono" placeholder="留空=全部" />
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

    <details class="advanced sub-mapping-details">
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
        <label class="form-field full">
          <FormFieldLabel
            label="失败队列（可选）"
            tech="consumption.dlq.producer_id"
            tech-placement="tooltip"
            wide-tip
            tip="处理失败时转发到字典生产者；留空则仅在运行中心记录。"
          />
          <input v-model="form.dlq_producer_id" class="form-inp mono" placeholder="memory.alerts.dlq" />
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
import { ref, watch } from "vue";
import ContextMappingEditor from "@/components/ContextMappingEditor.vue";
import FormFieldLabel from "@/components/FormFieldLabel.vue";
import InfoTip from "@/components/InfoTip.vue";
import type { ContextMappingState } from "@/operations/contextMappingConfig";
import type { SubscriptionFormState } from "@/operations/subscriptionScheduleConfig";

defineProps<{
  pane: "consumer" | "side";
}>();

const form = defineModel<SubscriptionFormState>("form", { required: true });
const mapping = defineModel<ContextMappingState>("mapping", { required: true });

const timestampLocal = ref("");

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

.consume-config-grid {
  margin-top: 10px;
}

.fault-tolerance-grid {
  margin-top: 10px;
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
