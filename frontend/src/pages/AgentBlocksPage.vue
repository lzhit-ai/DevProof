<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiRequest as request, projectHeaders as authHeaders, selectedProject, selectedProjectId } from '../features/projects/project-context'

type CoreScope = 'REQUIREMENT' | 'DELIVERY' | 'SHARED'

interface Capability {
  id: string
  key: string
  name: string
  description: string
  coreScope: CoreScope
  kind: 'SYSTEM' | 'CUSTOM'
  isLocked: boolean
  isDefaultEnabled: boolean
  isActive: boolean
  latestVersionId: string | null
  latestVersion: number | null
}

interface Tool {
  id: string
  key: string
  name: string
  toolType: string
  endpointUrl: string | null
  secretRef: string | null
  isSystem: boolean
  isActive: boolean
}

interface TemplateNode {
  capabilityVersionId: string
  capabilityKey: string
  capabilityName: string
  coreScope: CoreScope
  displayOrder: number
  enabled: boolean
  locked: boolean
}

interface Template {
  id: string
  name: string
  description: string
  isDefault: boolean
  isSystem: boolean
  version: number
  nodes: TemplateNode[]
}

interface OrchestrationData {
  capabilities: Capability[]
  tools: Tool[]
  templates: Template[]
}

interface CapabilityVersionDetail {
  capabilityId: string
  kind: 'SYSTEM' | 'CUSTOM'
  isLocked: boolean
  isActive: boolean
  versionId: string
  version: number
  promptTemplate: string
  toolIds: string[]
}

interface TaskBinding {
  taskId: string
  taskTitle: string
  requirementKey: string
  templateId: string | null
  templateName: string | null
  templateVersion: number | null
  boundAt: string | null
  isTemplateUsable: boolean
}

const projectId = selectedProjectId
const activeTab = ref<'capabilities' | 'tools' | 'templates'>('capabilities')
const data = ref<OrchestrationData>({ capabilities: [], tools: [], templates: [] })
const taskBindings = ref<TaskBinding[]>([])
const busy = ref(false)
const message = ref('选择项目后加载固定双核、能力块与编排模板。')
const selectedToolIds = ref<string[]>([])
const selectedCapabilityVersionIds = ref<string[]>([])
const agentForm = ref({ key: '', name: '', description: '', coreScope: 'SHARED' as CoreScope, prompt: '' })
const toolForm = ref({ key: '', name: '', toolType: 'HTTP_QUERY', endpointUrl: '', secretRef: '' })
const templateForm = ref({ name: '', description: '' })
const editingCapabilityId = ref<string | null>(null)
const versionForm = ref({ prompt: '', toolIds: [] as string[] })

const capabilitiesByScope = computed(() => ({
  requirement: data.value.capabilities.filter((item) => item.coreScope === 'REQUIREMENT'),
  delivery: data.value.capabilities.filter((item) => item.coreScope === 'DELIVERY'),
  shared: data.value.capabilities.filter((item) => item.coreScope === 'SHARED'),
}))
const selectedTemplateCapabilities = computed(() => selectedCapabilityVersionIds.value.map((versionId) => data.value.capabilities.find((item) => item.latestVersionId === versionId && item.isActive)).filter((item): item is Capability => Boolean(item)))
const bindableTemplates = computed(() => data.value.templates.filter((template) => template.nodes.every((node) => data.value.capabilities.some((capability) => capability.key === node.capabilityKey && capability.isActive))))

async function load() {
  if (!projectId.value) return
  busy.value = true
  try {
    const [orchestration, bindings] = await Promise.all([
      request<OrchestrationData>(`/projects/${projectId.value}/agent-orchestration`, { headers: authHeaders() }),
      request<TaskBinding[]>(`/projects/${projectId.value}/agent-orchestration/task-bindings`, { headers: authHeaders() }),
    ])
    data.value = orchestration
    taskBindings.value = bindings
    selectedCapabilityVersionIds.value = data.value.capabilities.filter((item) => item.isActive && item.latestVersionId).map((item) => item.latestVersionId as string)
    message.value = `已加载固定双核、${data.value.capabilities.length} 个能力块、${data.value.templates.length} 个编排模板与 ${taskBindings.value.length} 个任务绑定。`
  } catch (error) {
    message.value = error instanceof Error ? error.message : '加载失败'
  } finally {
    busy.value = false
  }
}

async function startCapabilityVersion(item: Capability) {
  if (!projectId.value || item.kind !== 'CUSTOM' || !item.isActive) return
  busy.value = true
  try {
    const detail = await request<CapabilityVersionDetail>(`/projects/${projectId.value}/agent-orchestration/capabilities/${item.id}/latest-version`, { headers: authHeaders() })
    editingCapabilityId.value = detail.capabilityId
    versionForm.value = { prompt: detail.promptTemplate, toolIds: detail.toolIds }
    message.value = `正在编辑 ${item.name} v${detail.version} 的新版本。`
  } catch (error) {
    message.value = error instanceof Error ? error.message : '读取能力版本失败'
  } finally {
    busy.value = false
  }
}

function cancelCapabilityVersion() {
  editingCapabilityId.value = null
  versionForm.value = { prompt: '', toolIds: [] }
}

async function createCapabilityVersion() {
  if (!projectId.value || !editingCapabilityId.value) return
  busy.value = true
  try {
    await request(`/projects/${projectId.value}/agent-orchestration/capabilities/${editingCapabilityId.value}/versions`, {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({
        prompt_template: versionForm.value.prompt,
        input_schema: {}, output_schema: {}, parameter_schema: {}, tool_ids: versionForm.value.toolIds,
      }),
    })
    message.value = '新的 Agent 版本已保存；后续模板需显式选择该版本，既有运行保持原样。'
    cancelCapabilityVersion()
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '创建 Agent 版本失败'
  } finally {
    busy.value = false
  }
}

async function deactivateCapability(item: Capability) {
  if (!projectId.value || item.kind !== 'CUSTOM' || !item.isActive) return
  if (!window.confirm(`停用“${item.name}”？停用后将无法用于新模板。`)) return
  busy.value = true
  try {
    await request(`/projects/${projectId.value}/agent-orchestration/capabilities/${item.id}/deactivate`, {
      method: 'POST', headers: authHeaders(true),
    })
    if (editingCapabilityId.value === item.id) cancelCapabilityVersion()
    message.value = `已停用 ${item.name}；既有正式记录和冻结运行未被改写。`
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '停用 Agent 失败'
  } finally {
    busy.value = false
  }
}

async function createAgent() {
  if (!projectId.value) return
  busy.value = true
  try {
    await request(`/projects/${projectId.value}/agent-orchestration/capabilities`, {
      method: 'POST', headers: authHeaders(true), body: JSON.stringify({
        key: agentForm.value.key,
        name: agentForm.value.name,
        description: agentForm.value.description,
        core_scope: agentForm.value.coreScope,
        prompt_template: agentForm.value.prompt,
        input_schema: {}, output_schema: {}, parameter_schema: {}, tool_ids: selectedToolIds.value,
      }),
    })
    agentForm.value = { key: '', name: '', description: '', coreScope: 'SHARED', prompt: '' }
    selectedToolIds.value = []
    message.value = '自定义 Agent 已创建；新的 Prompt 与工具授权将作为版本 v1 保存。'
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '创建失败'
  } finally {
    busy.value = false
  }
}

async function createTool() {
  if (!projectId.value) return
  busy.value = true
  try {
    await request(`/projects/${projectId.value}/agent-orchestration/tools`, {
      method: 'POST', headers: authHeaders(true), body: JSON.stringify({
        key: toolForm.value.key,
        name: toolForm.value.name,
        tool_type: toolForm.value.toolType,
        endpoint_url: toolForm.value.endpointUrl || null,
        secret_ref: toolForm.value.secretRef || null,
        input_schema: {}, output_schema: {},
      }),
    })
    toolForm.value = { key: '', name: '', toolType: 'HTTP_QUERY', endpointUrl: '', secretRef: '' }
    message.value = '只读工具已登记，可授权给新的 Agent 版本。'
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '创建失败'
  } finally {
    busy.value = false
  }
}

async function createTemplate() {
  if (!projectId.value) return
  busy.value = true
  try {
    await request(`/projects/${projectId.value}/agent-orchestration/templates`, {
      method: 'POST', headers: authHeaders(true), body: JSON.stringify({
        name: templateForm.value.name,
        description: templateForm.value.description,
        nodes: selectedCapabilityVersionIds.value.map((capabilityVersionId) => ({ capability_version_id: capabilityVersionId, enabled: true, parameters: {} })),
      }),
    })
    templateForm.value = { name: '', description: '' }
    message.value = '编排模板已创建。双核和 Git Diff 主干会在服务端再次校验。'
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '创建失败'
  } finally {
    busy.value = false
  }
}

async function bindTaskTemplate(taskId: string, templateId: string) {
  if (!templateId) return
  busy.value = true
  try {
    await request(`/verification-tasks/${taskId}/agent-orchestration`, {
      method: 'PUT', headers: authHeaders(true), body: JSON.stringify({ template_id: templateId }),
    })
    message.value = '任务已绑定编排模板。该绑定只决定后续核验使用的能力组合，不代表交付已完成。'
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '绑定任务模板失败'
  } finally {
    busy.value = false
  }
}

function moveSelectedCapability(index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= selectedCapabilityVersionIds.value.length) return
  const reordered = [...selectedCapabilityVersionIds.value]
  ;[reordered[index], reordered[target]] = [reordered[target], reordered[index]]
  selectedCapabilityVersionIds.value = reordered
}

watch(projectId, () => { void load() }, { immediate: true })
</script>

<template>
  <section class="page agent-page">
    <header class="page-heading">
      <div>
        <h1>Agent 功能块</h1>

        <p v-if="!selectedProject">请先选择项目。</p>
      </div>
      <button class="primary-button" type="button" :disabled="busy || !projectId" @click="load">刷新配置</button>
    </header>

    <div class="agent-layout">
      <aside class="surface agent-rail" aria-label="功能块配置区">
        <button :class="{ active: activeTab === 'capabilities' }" type="button" @click="activeTab = 'capabilities'">功能块库</button>
        <button :class="{ active: activeTab === 'tools' }" type="button" @click="activeTab = 'tools'">工具授权</button>
        <button :class="{ active: activeTab === 'templates' }" type="button" @click="activeTab = 'templates'">编排模板</button>
        <p>{{ message }}</p>
      </aside>

      <section v-if="activeTab === 'capabilities'" class="surface agent-content">
        <div class="agent-section-heading"><div><h2>固定双核与能力块</h2></div></div>
        <div class="core-lanes">
          <section><h3>需求 / 验收核心</h3><article v-for="item in capabilitiesByScope.requirement" :key="item.id" class="agent-row"><div><strong>{{ item.name }}</strong><p>{{ item.description }}</p></div><span class="agent-lock">系统必经</span></article></section>
          <section><h3>交付证据核心</h3><article v-for="item in capabilitiesByScope.delivery" :key="item.id" class="agent-row"><div><strong>{{ item.name }}</strong><p>{{ item.description }}</p></div><span :class="item.isLocked ? 'agent-lock' : 'agent-state'">{{ item.isLocked ? '锁定默认' : '默认启用' }}</span></article></section>
        </div>
        <section class="agent-list-section"><h3>共享与自定义能力</h3><article v-for="item in capabilitiesByScope.shared" :key="item.id" class="agent-row"><div><strong>{{ item.name }}</strong><p>{{ item.description || '自定义 Prompt 能力块' }}</p><small>{{ item.kind === 'CUSTOM' ? `自定义 · v${item.latestVersion}` : '系统能力' }}</small></div><div v-if="item.kind === 'CUSTOM'" class="agent-actions"><span :class="item.isActive ? 'agent-state' : 'agent-inactive'">{{ item.isActive ? '可编排' : '已停用' }}</span><button v-if="item.isActive" type="button" :disabled="busy" @click="startCapabilityVersion(item)">新版本</button><button v-if="item.isActive" type="button" class="agent-danger-action" :disabled="busy" @click="deactivateCapability(item)">停用</button></div><span v-else :class="item.isLocked ? 'agent-lock' : 'agent-state'">{{ item.isLocked ? '系统必经' : '系统能力' }}</span></article></section>
        <form v-if="editingCapabilityId" class="agent-form agent-version-form" @submit.prevent="createCapabilityVersion"><h3>创建 Agent 新版本</h3><p class="agent-form-note">保存为新版本。</p><label>自定义 Prompt<textarea v-model="versionForm.prompt" required placeholder="只基于授权证据提出建议；不要输出最终审批结论。"></textarea></label><fieldset><legend>授权工具</legend><label v-for="tool in data.tools.filter((item) => item.isActive)" :key="tool.id" class="check-line"><input v-model="versionForm.toolIds" type="checkbox" :value="tool.id" />{{ tool.name }}<small>{{ tool.toolType }}</small></label></fieldset><div class="agent-form-actions"><button class="primary-button" :disabled="busy || !projectId">保存新版本</button><button type="button" :disabled="busy" @click="cancelCapabilityVersion">取消</button></div></form>
        <form class="agent-form" @submit.prevent="createAgent"><h3>创建外围 Agent</h3><div class="agent-form-grid"><label>标识<input v-model="agentForm.key" required placeholder="例如 payment-risk-check" /></label><label>名称<input v-model="agentForm.name" required placeholder="例如 支付风险复核" /></label></div><label>说明<input v-model="agentForm.description" placeholder="说明它要补充什么证据判断" /></label><label>自定义 Prompt<textarea v-model="agentForm.prompt" required placeholder="只基于授权证据提出关联或风险建议；不要输出最终审批结论。"></textarea></label><fieldset><legend>授权工具</legend><label v-for="tool in data.tools" :key="tool.id" class="check-line"><input v-model="selectedToolIds" type="checkbox" :value="tool.id" />{{ tool.name }}<small>{{ tool.toolType }}</small></label></fieldset><button class="primary-button" :disabled="busy || !projectId">创建外围 Agent</button></form>
      </section>

      <section v-else-if="activeTab === 'tools'" class="surface agent-content">
        <div class="agent-section-heading"><div><h2>只读工具授权</h2><p>凭据填写服务端环境变量名称。</p></div></div>
        <article v-for="tool in data.tools" :key="tool.id" class="agent-row"><div><strong>{{ tool.name }}</strong><p>{{ tool.toolType }}<template v-if="tool.endpointUrl"> · {{ tool.endpointUrl }}</template></p></div><span :class="tool.isSystem ? 'agent-lock' : 'agent-state'">{{ tool.isSystem ? '系统工具' : '项目工具' }}</span></article>
        <form class="agent-form" @submit.prevent="createTool"><h3>登记查询工具</h3><div class="agent-form-grid"><label>标识<input v-model="toolForm.key" required placeholder="例如 release-query" /></label><label>名称<input v-model="toolForm.name" required placeholder="例如 发布记录查询" /></label><label>类型<select v-model="toolForm.toolType"><option value="HTTP_QUERY">HTTP 查询</option><option value="EVIDENCE_QUERY">证据查询</option><option value="CI_EVIDENCE">CI 证据</option></select></label></div><label>登记端点（仅 HTTP 查询）<input v-model="toolForm.endpointUrl" :required="toolForm.toolType === 'HTTP_QUERY'" placeholder="https://example.internal/query" /></label><label>环境变量引用（可选）<input v-model="toolForm.secretRef" placeholder="例如 RELEASE_API_TOKEN" /></label><button class="primary-button" :disabled="busy || !projectId">登记工具</button></form>
      </section>

      <section v-else class="surface agent-content">
        <div class="agent-section-heading"><div><h2>编排模板</h2></div></div>
        <article v-for="template in data.templates" :key="template.id" class="template-row"><div><strong>{{ template.name }}</strong><p>{{ template.description }}</p><ol><li v-for="node in template.nodes" :key="node.capabilityVersionId"><span>{{ node.displayOrder }}</span>{{ node.capabilityName }}<small v-if="node.locked">锁定</small></li></ol></div><span :class="template.isDefault ? 'agent-lock' : 'agent-state'">{{ template.isDefault ? '默认模板' : `v${template.version}` }}</span></article>
        <section class="agent-binding-section"><h3>核验任务绑定</h3><p v-if="!taskBindings.length" class="empty-row">暂无核验任务。</p><article v-for="binding in taskBindings" :key="binding.taskId" class="task-binding-row"><div><strong>{{ binding.taskTitle }}</strong><p>{{ binding.requirementKey }} · 当前：{{ binding.templateName || '未绑定模板' }}<template v-if="binding.templateVersion"> · v{{ binding.templateVersion }}</template></p><small v-if="binding.templateId && !binding.isTemplateUsable" class="risk-text">当前模板包含已停用能力，请重新绑定可用模板。</small></div><select :value="binding.templateId && binding.isTemplateUsable ? binding.templateId : ''" :disabled="busy || !bindableTemplates.length" @change="bindTaskTemplate(binding.taskId, String(($event.target as HTMLSelectElement).value))"><option value="" disabled>选择后续核验模板</option><option v-for="template in bindableTemplates" :key="template.id" :value="template.id">{{ template.name }} · v{{ template.version }}</option></select></article></section>
        <form class="agent-form" @submit.prevent="createTemplate"><h3>创建编排模板</h3><div class="agent-form-grid"><label>名称<input v-model="templateForm.name" required placeholder="例如 支付交付核验" /></label><label>说明<input v-model="templateForm.description" placeholder="说明本模板适用的交付场景" /></label></div><fieldset><legend>纳入能力块</legend><label v-for="item in data.capabilities.filter((capability) => capability.isActive && capability.latestVersionId)" :key="item.id" class="check-line"><input v-model="selectedCapabilityVersionIds" type="checkbox" :value="item.latestVersionId" :disabled="item.isLocked" />{{ item.name }}<small>{{ item.isLocked ? '系统必经' : item.coreScope }}</small></label></fieldset><section class="template-order"><h4>本次编排顺序</h4><p>使用上移、下移调整顺序。</p><div v-for="(item, index) in selectedTemplateCapabilities" :key="item.id" class="template-order-row"><span>{{ index + 1 }}</span><strong>{{ item.name }}</strong><small>{{ item.coreScope }}</small><div><button type="button" :disabled="index === 0" @click="moveSelectedCapability(index, -1)">上移</button><button type="button" :disabled="index === selectedTemplateCapabilities.length - 1" @click="moveSelectedCapability(index, 1)">下移</button></div></div></section><button class="primary-button" :disabled="busy || !projectId">创建模板</button></form>
      </section>
    </div>
  </section>
</template>
