<template>
  <div class="secret-panel">
    <div v-if="confirmOpen" class="confirm-mask" @click.self="closeConfirmDialog">
      <div class="confirm-dialog" role="dialog" aria-modal="true" :aria-label="confirmTitle">
        <div class="confirm-title">{{ confirmTitle }}</div>
        <p class="confirm-text">{{ confirmText }}</p>
        <div class="confirm-actions">
          <button type="button" class="btn ghost" @click="closeConfirmDialog">取消</button>
          <button type="button" class="btn ghost danger" @click="confirmDialogAction">确认删除</button>
        </div>
      </div>
    </div>

    <div class="secret-layout">
      <aside class="secret-left">
        <div class="section-title">
          <span>密钥列表 · {{ profile }}</span>
          <button type="button" class="link" @click="startNew">新增</button>
        </div>
        <button
          v-for="s in secrets"
          :key="s.secret_name"
          type="button"
          class="module-btn"
          :class="{ active: selectedName === s.secret_name && !isNew }"
          @click="selectSecret(s.secret_name)"
        >
          <span class="mono">{{ s.secret_name }}</span>
          <span class="type-tag">{{ s.secret_type }}</span>
        </button>
        <p v-if="!secrets.length" class="empty">当前 profile 暂无密钥，请先加密明文并保存。</p>
      </aside>

      <div class="secret-right">
        <div class="meta">
          <span class="lbl">密钥名</span>
          <input
            v-model="editorName"
            class="inp-mini mono module-input"
            placeholder="es_password"
            :disabled="!isNew && !!selectedName"
          />
          <span class="lbl">类型</span>
          <select v-model="editorType" class="inp-mini">
            <option v-for="t in secretTypes" :key="t" :value="t">{{ t }}</option>
          </select>
          <button type="button" class="btn primary" :disabled="saving || !editorName.trim()" @click="onSave">
            {{ saving ? "保存中…" : "保存" }}
          </button>
          <button type="button" class="btn ghost danger" :disabled="!selectedName || isNew" @click="requestRemove">
            删除
          </button>
        </div>

        <div class="lbl block">密钥数据 JSON（密文）</div>
        <CodeEditor v-model="editorDataJson" language="json" :height="200" />

        <div class="crypto-box">
          <div class="lbl">加密工具</div>
          <p class="muted small">
            输入明文 → 加密 → 将下方 JSON 粘贴到「密钥数据」并保存。本 profile 数据字典引用：
            <code class="mono">secret://{{ editorName || "密钥名" }}</code>
          </p>
          <textarea v-model="plaintextInput" class="plaintext-inp mono" rows="2" placeholder="待加密的明文" />
          <div class="crypto-actions">
            <button type="button" class="btn ghost" :disabled="encrypting" @click="runEncrypt">
              {{ encrypting ? "加密中…" : "加密明文" }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import CodeEditor from "@/components/CodeEditor.vue";
import {
  deleteSecret as apiDeleteSecret,
  encryptPlaintext,
  fetchSecret,
  fetchSecrets,
  fetchSecretTypes,
  saveSecret as apiSaveSecret,
  type SecretRecord,
} from "@/api/secrets";

const props = defineProps<{
  profile: string;
}>();

const emit = defineEmits<{ (e: "error", msg: string): void }>();

const secrets = ref<SecretRecord[]>([]);
const secretTypes = ref<string[]>(["local_fernet"]);
const selectedName = ref<string | null>(null);
const isNew = ref(false);
const editorName = ref("");
const editorType = ref("local_fernet");
const editorDataJson = ref("{\n}\n");
const plaintextInput = ref("");
const saving = ref(false);
const encrypting = ref(false);

const confirmOpen = ref(false);
const confirmTitle = ref("确认删除");
const confirmText = ref("");

async function reload() {
  try {
    const [list, types] = await Promise.all([
      fetchSecrets(props.profile),
      fetchSecretTypes(),
    ]);
    secrets.value = list.secrets;
    secretTypes.value = types.length ? types : ["local_fernet"];
    if (!secretTypes.value.includes(editorType.value)) {
      editorType.value = secretTypes.value[0] ?? "local_fernet";
    }
  } catch (e) {
    emit("error", e instanceof Error ? e.message : String(e));
  }
}

function startNew() {
  isNew.value = true;
  selectedName.value = null;
  editorName.value = "";
  editorType.value = secretTypes.value[0] ?? "local_fernet";
  editorDataJson.value = "{\n}\n";
  plaintextInput.value = "";
}

async function selectSecret(name: string) {
  isNew.value = false;
  selectedName.value = name;
  try {
    const rec = await fetchSecret(props.profile, name);
    editorName.value = rec.secret_name;
    editorType.value = rec.secret_type;
    editorDataJson.value = JSON.stringify(rec.secret_data, null, 2) + "\n";
  } catch (e) {
    emit("error", e instanceof Error ? e.message : String(e));
  }
}

async function onSave() {
  const name = editorName.value.trim().toLowerCase();
  if (!name) return;
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(editorDataJson.value) as Record<string, unknown>;
  } catch {
    emit("error", "密钥数据 JSON 格式无效");
    return;
  }
  saving.value = true;
  try {
    await apiSaveSecret(props.profile, name, editorType.value, data);
    selectedName.value = name;
    isNew.value = false;
    await reload();
  } catch (e) {
    emit("error", e instanceof Error ? e.message : String(e));
  } finally {
    saving.value = false;
  }
}

function requestRemove() {
  if (!selectedName.value) return;
  confirmTitle.value = "删除密钥";
  confirmText.value = `确定删除 profile「${props.profile}」下的密钥「${selectedName.value}」？此操作不可恢复。`;
  confirmOpen.value = true;
}

function closeConfirmDialog() {
  confirmOpen.value = false;
}

async function confirmDialogAction() {
  const name = selectedName.value;
  confirmOpen.value = false;
  if (!name) return;
  try {
    await apiDeleteSecret(props.profile, name);
    startNew();
    await reload();
  } catch (e) {
    emit("error", e instanceof Error ? e.message : String(e));
  }
}

async function runEncrypt() {
  encrypting.value = true;
  try {
    const res = await encryptPlaintext(editorType.value, plaintextInput.value);
    editorDataJson.value = JSON.stringify(res.secret_data, null, 2) + "\n";
  } catch (e) {
    emit("error", e instanceof Error ? e.message : String(e));
  } finally {
    encrypting.value = false;
  }
}

watch(
  () => props.profile,
  () => {
    startNew();
    void reload();
  },
);

onMounted(() => {
  void reload();
});

defineExpose({ reload });
</script>

<style scoped>
.secret-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.confirm-mask {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, #0f172a 32%, transparent);
  z-index: 40;
  display: grid;
  place-items: center;
  padding: 16px;
}

.confirm-dialog {
  width: min(460px, calc(100vw - 32px));
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow);
  padding: 16px;
}

.confirm-title {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 8px;
}

.confirm-text {
  margin: 0;
  font-size: 13px;
  color: var(--text);
}

.confirm-actions {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.secret-layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 12px;
  flex: 1;
  min-height: 0;
  padding: 12px 16px;
}

.secret-left {
  overflow: auto;
  border-right: 1px solid var(--border);
  padding-right: 8px;
}

.secret-right {
  overflow: auto;
  min-width: 0;
}

.section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.module-btn {
  display: flex;
  width: 100%;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 12px;
  cursor: pointer;
  margin-bottom: 4px;
}

.module-btn:hover {
  background: color-mix(in srgb, var(--accent-soft) 40%, transparent);
}

.module-btn.active {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  background: var(--accent-soft);
}

.type-tag {
  font-size: 10px;
  color: var(--muted);
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.lbl {
  font-size: 11px;
  color: var(--muted);
}

.lbl.block {
  display: block;
  margin-bottom: 6px;
}

.inp-mini,
.module-input {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  padding: 6px 8px;
  font-size: 12px;
}

.module-input {
  min-width: 140px;
}

.btn {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 12px;
  cursor: pointer;
}

.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
}

.btn.danger {
  color: #b91c1c;
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.link {
  border: none;
  background: none;
  color: var(--accent);
  font-size: 11px;
  cursor: pointer;
  padding: 0;
}

.crypto-box {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: color-mix(in srgb, var(--surface) 92%, transparent);
}

.plaintext-inp {
  width: 100%;
  margin: 8px 0;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 12px;
  resize: vertical;
}

.crypto-actions {
  display: flex;
  gap: 8px;
}

.muted.small {
  font-size: 11px;
  color: var(--muted);
  margin: 4px 0 8px;
}

.empty {
  font-size: 11px;
  color: var(--muted);
}
</style>
