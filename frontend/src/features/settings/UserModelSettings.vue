<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { apiRequest, projectHeaders } from '../projects/project-context'

interface ModelConfiguration { provider: string; model: string; baseUrl: string }
interface CatalogModel extends ModelConfiguration { id: string; label: string; providerLabel: string }
interface Settings { configured: boolean; version: number; configuration: ModelConfiguration; updatedAt: string | null; models: CatalogModel[]; selectedModelId: string | null }

const settings = ref<Settings | null>(null)
const form = ref({ modelId: '', apiKey: '' })
const loading = ref(true)
const saving = ref(false)
const loadFailed = ref(false)
const confirmingClear = ref(false)
const message = ref('')
const failed = ref(false)
const selectedModel = computed(() => settings.value?.models.find(model => model.id === form.value.modelId))
const modelGroups = computed(() => {
  const groups = new Map<string, CatalogModel[]>()
  for (const model of settings.value?.models ?? []) {
    const group = groups.get(model.providerLabel) ?? []
    group.push(model); groups.set(model.providerLabel, group)
  }
  return Array.from(groups, ([label, models]) => ({ label, models }))
})
const retainsKey = computed(() => settings.value?.configured && selectedModel.value?.provider === settings.value.configuration.provider
  && selectedModel.value?.baseUrl === settings.value.configuration.baseUrl)
const keyPlaceholder = computed(() => retainsKey.value ? '已保存，留空保留当前 Key'
  : selectedModel.value ? `输入${selectedModel.value.providerLabel}的 API Key` : '请先选择模型')

watch(() => form.value.modelId, (value, previous) => {
  const models = settings.value?.models ?? []
  if (models.find(model => model.id === value)?.provider !== models.find(model => model.id === previous)?.provider) form.value.apiKey = ''
  message.value = ''; confirmingClear.value = false
}, { flush: 'sync' })

function accept(value: Settings) {
  settings.value = value
  form.value = { modelId: value.selectedModelId ?? '', apiKey: '' }
  confirmingClear.value = false
}

async function load() {
  loading.value = true; loadFailed.value = false; message.value = ''
  try { accept(await apiRequest<Settings>('/me/ai-settings', { headers: projectHeaders() })) }
  catch (error) { loadFailed.value = true; failed.value = true; message.value = error instanceof Error ? error.message : '个人 AI 配置加载失败' }
  finally { loading.value = false }
}

async function save() {
  if (!settings.value || !selectedModel.value || saving.value || loadFailed.value) return
  saving.value = true; message.value = ''; failed.value = false
  try {
    const value = await apiRequest<Settings>('/me/ai-settings', { method: 'PUT', headers: projectHeaders(true), body: JSON.stringify({
      modelId: form.value.modelId,
      apiKey: form.value.apiKey || null, expectedVersion: settings.value.version,
    }) })
    accept(value); message.value = '个人 AI 配置已保存。'
  } catch (error) { failed.value = true; message.value = error instanceof Error ? error.message : '个人 AI 配置保存失败' }
  finally { saving.value = false }
}

async function clear() {
  if (!settings.value || saving.value) return
  saving.value = true; message.value = ''; failed.value = false
  try {
    accept(await apiRequest<Settings>('/me/ai-settings', { method: 'DELETE', headers: projectHeaders(true),
      body: JSON.stringify({ expectedVersion: settings.value.version }) }))
    message.value = '个人 AI 配置已清除。'
  } catch (error) { failed.value = true; message.value = error instanceof Error ? error.message : '个人 AI 配置清除失败' }
  finally { saving.value = false }
}

onMounted(() => { void load() })
onBeforeUnmount(() => { form.value.apiKey = '' })
</script>

<template>
  <section class="surface user-ai-settings" aria-labelledby="personal-ai-title">
    <header class="ai-heading">
      <div><h2 id="personal-ai-title">个人 AI 模型</h2><p>用于你的规划、审查和问答。</p></div>
      <span class="ai-state" :class="{ configured: settings?.configured }">{{ loading ? '正在读取…' : loadFailed ? '读取失败' : settings?.configured ? '已配置' : '未配置' }}</span>
    </header>
    <form @submit.prevent="save">
      <fieldset :disabled="loading || saving || loadFailed">
        <div class="ai-fields">
          <label>模型<select v-model="form.modelId" required>
            <option value="" disabled>{{ settings?.configured ? `当前：${settings.configuration.model}，请选择新模型` : '请选择模型' }}</option>
            <optgroup v-for="group in modelGroups" :key="group.label" :label="group.label"><option v-for="model in group.models" :key="model.id" :value="model.id">{{ model.label }}</option></optgroup>
          </select></label>
          <label>API Key<input v-model="form.apiKey" type="password" :required="!retainsKey" :disabled="!selectedModel" maxlength="8192" autocomplete="off" spellcheck="false" :placeholder="keyPlaceholder" /></label>
        </div>
        <p v-if="!loading && !loadFailed && !settings?.models.length" class="ai-message is-error" role="alert">暂无可选模型，请联系管理员开放模型服务商。</p>
        <div class="ai-actions"><button class="primary-button" type="submit" :disabled="!selectedModel">{{ saving ? '正在保存…' : '保存配置' }}</button><button v-if="settings?.configured" type="button" class="ai-clear" @click="confirmingClear = !confirmingClear">清除配置</button><span v-if="settings?.configured">Key 已加密保存，不显示原文。</span></div>
      </fieldset>
    </form>
    <div v-if="confirmingClear" class="ai-clear-confirm"><span>清除后，新的 AI 任务需要重新配置。</span><button type="button" :disabled="saving" @click="clear">确认清除</button><button type="button" :disabled="saving" @click="confirmingClear = false">取消</button></div>
    <p v-if="message" class="ai-message" :class="{ 'is-error': failed }" :role="failed ? 'alert' : 'status'">{{ message }} <button v-if="loadFailed" type="button" @click="load">重新加载</button></p>
  </section>
</template>

<style scoped>
.user-ai-settings { flex: 0 0 auto; padding: 24px; margin-bottom: 24px; }
.ai-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; margin-bottom: 22px; }
.ai-heading h2 { margin: 0; color: var(--ink); font-size: 18px; font-weight: 600; }
.ai-heading p { margin: 4px 0 0; color: var(--muted); font-size: 14px; }
.ai-state { flex: 0 0 auto; padding: 4px 10px; border-radius: 6px; background: var(--surface-muted); color: var(--muted); font-size: 13px; }
.ai-state.configured { background: var(--brand-soft); color: var(--brand); }
fieldset { min-width: 0; margin: 0; padding: 0; border: 0; }
.ai-fields { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr); gap: 16px 20px; }
.ai-fields label { display: grid; gap: 8px; color: var(--ink); font-size: 14px; }
.ai-fields input, .ai-fields select { width: 100%; min-width: 0; min-height: 44px; padding: 9px 12px; border: 1px solid var(--line); border-radius: 10px; color: var(--ink); background: var(--surface); font: inherit; }
.ai-fields select { text-overflow: ellipsis; }
.ai-fields :is(input, select):disabled { cursor: default; background: var(--surface-muted); }
.ai-fields input::placeholder { color: var(--muted); opacity: 1; }
.ai-fields :is(input, select):focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
.ai-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 20px; }
.ai-actions span { color: var(--muted); font-size: 13px; }
.ai-clear, .ai-clear-confirm button, .ai-message button { min-height: 40px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); color: var(--ink); font: inherit; font-size: 14px; }
.ai-clear-confirm { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 18px; padding-top: 18px; border-top: 1px solid var(--line-soft); font-size: 14px; }
.ai-clear-confirm button:first-of-type { color: var(--danger); }
.ai-message { margin: 16px 0 0; color: var(--brand); font-size: 14px; overflow-wrap: anywhere; }
.ai-message.is-error { color: var(--danger); }
@media (max-width: 680px) { .user-ai-settings { padding: 20px; }.ai-fields { grid-template-columns: minmax(0, 1fr); } }
</style>
