<template>
  <div class="secret-panel">
    <div v-if="confirmOpen" class="confirm-mask" @click.self="closeConfirmDialog">
      <div class="confirm-dialog" role="dialog" aria-modal="true" :aria-label="confirmTitle">
        <div class="confirm-title">{{ confirmTitle }}</div>
        <p class="confirm-text">{{ confirmText }}</p>
        <div class="confirm-actions">
          <button type="button" class="btn ghost" @click="closeConfirmDialog">取消</button>
          <button type="button" class="btn ghost danger" :disabled="deletingSecret" @click="confirmDialogAction">
            {{ deletingSecret ? "删除中…" : "确认删除" }}
          </button>
        </div>
      </div>
    </div>

    <div class="secret-layout">
      <aside class="secret-left">
        <div class="section-title">
          <span>环境「{{ profile }}」</span>
          <button type="button" class="link" @click="startNew">新增</button>
        </div>
        <div
          v-for="s in secrets"
          :key="s.secret_name"
          class="secret-item"
          :class="{ active: selectedName === s.secret_name && !isNew }"
          @click="selectSecret(s.secret_name)"
        >
          <span class="mono secret-name">{{ s.secret_name }}</span>
          <div class="secret-item-tail">
            <span class="type-tag">{{ s.secret_type }}</span>
            <button
              type="button"
              class="delete-module-btn"
              :class="{ 'is-revealed': deletingSecretName === s.secret_name }"
              :disabled="!!deletingSecretName"
              aria-label="删除密钥"
              @click.stop="requestRemoveSecret(s.secret_name)"
            >
              {{ deletingSecretName === s.secret_name ? "…" : "删除" }}
            </button>
          </div>
        </div>
        <p v-if="!secrets.length" class="empty">当前环境暂无密钥。可用下方加密工具生成密文后保存。</p>
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
          <span class="lbl">加密方式</span>
          <select v-model="editorType" class="inp-mini">
            <option v-for="t in secretTypes" :key="t" :value="t">{{ t }}</option>
          </select>
          <button type="button" class="btn primary" :disabled="saving || !editorName.trim()" @click="onSave">
            {{ saving ? "保存中…" : "保存" }}
          </button>
        </div>

        <div class="lbl block">密文数据（JSON）</div>
        <CodeEditor v-model="editorDataJson" language="json" :height="200" />

        <div class="crypto-box">
          <div class="lbl">加密工具</div>
          <p class="muted small">
            输入明文并加密后，将生成的 JSON 填入上方「密文数据」并保存。在本环境的数据字典中引用：
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
const pendingDeleteName = ref<string | null>(null);
const deletingSecret = ref(false);
const deletingSecretName = ref<string | null>(null);

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
    emit("error", "密文数据 JSON 格式无效");
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

function requestRemoveSecret(name: string) {
  pendingDeleteName.value = name;
  confirmTitle.value = "删除密钥";
  confirmText.value = `确定删除环境「${props.profile}」下的密钥「${name}」？此操作不可恢复。`;
  confirmOpen.value = true;
}

function closeConfirmDialog() {
  if (deletingSecret.value) return;
  confirmOpen.value = false;
  pendingDeleteName.value = null;
}

async function confirmDialogAction() {
  const name = pendingDeleteName.value;
  if (!name) return;
  deletingSecret.value = true;
  deletingSecretName.value = name;
  confirmOpen.value = false;
  pendingDeleteName.value = null;
  try {
    await apiDeleteSecret(props.profile, name);
    if (selectedName.value === name) {
      startNew();
    }
    await reload();
  } catch (e) {
    emit("error", e instanceof Error ? e.message : String(e));
  } finally {
    deletingSecret.value = false;
    deletingSecretName.value = null;
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

.secret-item {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 8px 10px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  font-size: 12px;
}

.secret-item:hover {
  background: color-mix(in srgb, var(--accent-soft) 50%, transparent);
}

.secret-item.active {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: var(--accent-soft);
}

.secret-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.secret-item-tail {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  margin-left: auto;
}

.type-tag {
  font-size: 10px;
  color: var(--muted);
}

.delete-module-btn {
  flex-shrink: 0;
  white-space: nowrap;
  margin: 0;
  font: inherit;
  font-size: 10px;
  line-height: 1.2;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, #fecaca 55%, var(--border));
  background: color-mix(in srgb, #fef2f2 75%, #fbfdff);
  color: var(--muted);
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transition:
    opacity 0.14s ease,
    border-color 0.14s ease,
    color 0.14s ease,
    background 0.14s ease;
}

.secret-item:hover .delete-module-btn,
.secret-item:focus-within .delete-module-btn,
.delete-module-btn.is-revealed {
  opacity: 1;
  pointer-events: auto;
}

.delete-module-btn:hover:not(:disabled) {
  border-color: color-mix(in srgb, #dc2626 45%, var(--border));
  color: #b91c1c;
  background: #fef2f2;
}

.delete-module-btn:disabled {
  cursor: not-allowed;
}

.delete-module-btn.is-revealed:disabled {
  opacity: 1;
  pointer-events: none;
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
