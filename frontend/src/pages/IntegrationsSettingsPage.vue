<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { apiRequest, projectHeaders, selectedProject, selectedProjectId } from '../features/projects/project-context'
import DeleteProjectSection from '../features/projects/DeleteProjectSection.vue'
import UserModelSettings from '../features/settings/UserModelSettings.vue'

interface ExternalConnection { id: string; provider: string; name: string; repository_slug: string; secret_ref_configured: boolean; is_active: boolean; created_at: string }
interface SyncRun { id: string; connection_id: string; status: string; fetched_count: number; changed_count: number; page_count: number; error_code: string | null; error_message: string | null; finished_at: string | null; next_retry_at: string | null }
interface GitRepository { id: string; display_url: string; read_only: boolean }

const connections = ref<ExternalConnection[]>([])
const syncRuns = ref<SyncRun[]>([])
const repositories = ref<GitRepository[]>([])
const busy = ref(false)
const message = ref('')
const connectionForm = ref({ name: '', repositorySlug: '', secretRef: '' })
const repositoryForm = ref({ displayUrl: '', credentialRef: '' })
let pollTimer: ReturnType<typeof setTimeout> | undefined
let disposed = false

function formatDate(value: string | null) { return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '进行中或尚未完成' }
function syncFor(connectionId: string) { return syncRuns.value.find((run) => run.connection_id === connectionId) }
function syncDescription(run: SyncRun) {
  if (run.status === 'RUNNING') {
    const progress = `已同步 ${run.fetched_count} 项`
    if (run.error_code === 'SOURCE_RATE_LIMITED') return `${progress} · GitHub 限流${run.next_retry_at ? `，${formatDate(run.next_retry_at)} 继续` : '，等待恢复'}`
    if (run.error_code) return `${progress} · ${run.next_retry_at ? `${formatDate(run.next_retry_at)} 重试` : '等待重试'}`
    return `${progress} · 正在同步`
  }
  if (run.status === 'SUCCEEDED') return `同步完成 · 读取 ${run.fetched_count} 项 · 更新 ${run.changed_count} 项`
  if (run.status === 'PARTIALLY_SUCCEEDED') return `本批已同步 ${run.fetched_count} 项 · 可继续读取历史记录`
  return `同步失败：${run.error_message ?? run.error_code ?? '请稍后重试'}`
}

async function load(silent = false) {
  clearTimeout(pollTimer)
  const projectId = selectedProjectId.value
  if (!projectId) { connections.value = []; syncRuns.value = []; repositories.value = []; return }
  if (!silent) busy.value = true
  try {
    const [connectionList, runList, repositoryList] = await Promise.all([
      apiRequest<ExternalConnection[]>(`/projects/${projectId}/external-connections`, { headers: projectHeaders() }),
      apiRequest<SyncRun[]>(`/projects/${projectId}/source-sync-runs`, { headers: projectHeaders() }),
      apiRequest<GitRepository[]>(`/projects/${projectId}/git-repositories`, { headers: projectHeaders() }),
    ])
    if (projectId !== selectedProjectId.value) return
    connections.value = connectionList; syncRuns.value = runList; repositories.value = repositoryList
    if (!disposed && connectionList.some(connection => syncFor(connection.id)?.status === 'RUNNING')) {
      pollTimer = setTimeout(() => { void load(true) }, 2000)
    }
  } catch (error) {
    if (projectId === selectedProjectId.value) message.value = error instanceof Error ? error.message : '集成配置加载失败'
  } finally { if (!silent && projectId === selectedProjectId.value) busy.value = false }
}

async function createConnection() {
  const projectId = selectedProjectId.value
  const name = connectionForm.value.name.trim()
  const repositorySlug = connectionForm.value.repositorySlug.trim().replace(/^https:\/\/github\.com\//, '').replace(/\.git$/, '')
  if (!projectId || !name || !repositorySlug) return
  busy.value = true
  try {
    await apiRequest(`/projects/${projectId}/external-connections`, {
      method: 'POST', headers: projectHeaders(true),
      body: JSON.stringify({ provider: 'GITHUB', name, repository_slug: repositorySlug, secret_ref: connectionForm.value.secretRef.trim() || null }),
    })
    connectionForm.value = { name: '', repositorySlug: '', secretRef: '' }
    message.value = 'GitHub 只读连接已保存。公开仓库无需填写凭据引用。'
    await load()
  } catch (error) { message.value = error instanceof Error ? error.message : 'GitHub 连接创建失败' } finally { busy.value = false }
}

async function syncConnection(connection: ExternalConnection) {
  const projectId = selectedProjectId.value
  if (!projectId) return
  busy.value = true
  try {
    const run = await apiRequest<SyncRun>(`/projects/${projectId}/external-connections/${connection.id}/sync`, { method: 'POST', headers: projectHeaders(true) })
    message.value = run.status === 'RUNNING' ? '同步任务已提交，下面会自动更新执行结果。' : syncDescription(run)
    await load()
  } catch (error) { message.value = error instanceof Error ? error.message : 'GitHub 同步失败' } finally { busy.value = false }
}

async function registerRepository() {
  const projectId = selectedProjectId.value
  const displayUrl = repositoryForm.value.displayUrl.trim()
  if (!projectId || !displayUrl) return
  busy.value = true
  try {
    await apiRequest(`/projects/${projectId}/git-repositories`, {
      method: 'POST', headers: projectHeaders(true),
      body: JSON.stringify({ display_url: displayUrl, credential_ref: repositoryForm.value.credentialRef.trim() || null }),
    })
    repositoryForm.value = { displayUrl: '', credentialRef: '' }
    message.value = '只读 Git 仓库已登记。绑定 GitHub Issue 的任务只接受同一来源仓库的 Diff。'
    await load()
  } catch (error) { message.value = error instanceof Error ? error.message : '只读 Git 仓库登记失败' } finally { busy.value = false }
}

watch(selectedProjectId, () => { void load() }, { immediate: true })
onBeforeUnmount(() => { disposed = true; clearTimeout(pollTimer) })
</script>

<template>
  <section class="page page-integrations">
    <header class="page-heading"><div><h1>集成与设置</h1><p v-if="!selectedProject">选择项目后可配置仓库连接。</p></div></header>
    <p v-if="message" class="page-context-note">{{ message }}</p>
    <div class="settings-content">
    <UserModelSettings />
    <template v-if="selectedProject">
      <div class="integration-grid">
        <section class="surface integration-section">
          <div class="surface-heading"><div><h2>GitHub 代码源</h2></div></div>
          <div v-if="connections.length" class="integration-list"><article v-for="connection in connections" :key="connection.id"><div><strong>{{ connection.name }}</strong><p>{{ connection.repository_slug }} · {{ connection.secret_ref_configured ? '已配置私有凭据引用' : '公开连接' }}</p><small v-if="syncFor(connection.id)" aria-live="polite">{{ syncDescription(syncFor(connection.id)!) }}<template v-if="syncFor(connection.id)?.finished_at"> · {{ formatDate(syncFor(connection.id)!.finished_at) }}</template></small></div><button type="button" :disabled="busy || syncFor(connection.id)?.status === 'RUNNING'" @click="syncConnection(connection)">{{ syncFor(connection.id)?.status === 'RUNNING' ? (syncFor(connection.id)?.error_code === 'SOURCE_RATE_LIMITED' ? '等待恢复' : '同步中…') : syncFor(connection.id)?.status === 'PARTIALLY_SUCCEEDED' ? '继续同步' : '同步' }}</button></article></div><p v-else class="empty-row">尚未接入 GitHub 仓库。</p>
          <form class="agent-form" @submit.prevent="createConnection"><h3>接入 GitHub 仓库</h3><label>连接名称<input v-model="connectionForm.name" required placeholder="例如：公开演示仓库" /></label><label>仓库（owner/repository）<input v-model="connectionForm.repositorySlug" required placeholder="例如：octocat/Spoon-Knife" /></label><label>私有仓库凭据引用（可选）<input v-model="connectionForm.secretRef" placeholder="例如：GITHUB_SOURCE_TOKEN" /></label><button class="primary-button" :disabled="busy">保存只读连接</button></form>
        </section>
        <section class="surface integration-section">
          <div class="surface-heading"><div><h2>只读 Git Diff</h2></div></div>
          <div v-if="repositories.length" class="integration-list"><article v-for="repository in repositories" :key="repository.id"><div><strong>{{ repository.display_url }}</strong><p>{{ repository.read_only ? '只读访问已锁定' : '访问策略异常' }}</p></div></article></div><p v-else class="empty-row">尚未登记用于冻结 Diff 的 Git 仓库。</p>
          <form class="agent-form" @submit.prevent="registerRepository"><h3>登记只读 Git 仓库</h3><label>仓库 URL<input v-model="repositoryForm.displayUrl" required placeholder="https://github.com/owner/repository.git" /></label><label>私有仓库凭据引用（可选）<input v-model="repositoryForm.credentialRef" placeholder="例如：GITHUB_SOURCE_TOKEN" /></label><button class="primary-button" :disabled="busy">登记只读仓库</button></form>
        </section>
      </div>
      <DeleteProjectSection />
    </template>
    </div>
  </section>
</template>

<style scoped>
.settings-content { flex: 1; min-height: 0; overflow: auto; padding: 2px; }
.settings-content .integration-section { overflow: visible; }
</style>
