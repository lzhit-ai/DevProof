<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { apiRequest, projectHeaders, selectedProject, selectedProjectId } from '../features/projects/project-context'

type PullRequest = { number: string; baseRef: string; baseSha: string; headRef: string; headSha: string; mergedAt: string | null; draft: boolean; changedFiles: number | null }
type DeliveryItem = { id: string; external_key: string; title: string; planning_status: string; verification_status: string; web_url: string; source_updated_at: string | null; pull_request: PullRequest | null }
type VerificationTask = { id: string; delivery_item_id: string; cycle_status: string; published_record_id: string | null }
type CreatedTask = { id: string }
type SyncRun = { id: string; connection_id: string; status: string; fetched_count: number; error_code: string | null; error_message: string | null; finished_at: string | null; next_retry_at: string | null }
type Filter = 'ALL' | 'READY' | 'REVIEWING' | 'FORMALIZED'

const router = useRouter()
const items = ref<DeliveryItem[]>([])
const tasks = ref<VerificationTask[]>([])
const syncs = ref<SyncRun[]>([])
const busyItemId = ref<string | null>(null)
const syncRetrying = ref(false)
const message = ref('')
const activeFilter = ref<Filter>('ALL')
const query = ref('')
const loadError = ref('')
let pollTimer: ReturnType<typeof setTimeout> | undefined
let disposed = false

const taskByItem = computed(() => new Map(tasks.value.map((task) => [task.delivery_item_id, task])))
const latestSync = computed(() => syncs.value[0] ?? null)
const syncInProgress = computed(() => latestSync.value?.status === 'RUNNING')
const syncFailed = computed(() => latestSync.value ? latestSync.value.status === 'FAILED' : false)
const canContinueSync = computed(() => latestSync.value?.status === 'PARTIALLY_SUCCEEDED' || syncFailed.value)
const syncProgress = computed(() => {
  const sync = latestSync.value
  if (!sync) return ''
  if (sync.status === 'RUNNING') {
    const progress = `已同步 ${sync.fetched_count} 项`
    if (sync.error_code === 'SOURCE_RATE_LIMITED') return `${progress} · GitHub 限流${sync.next_retry_at ? `，${formatDate(sync.next_retry_at)} 继续` : '，等待恢复'}`
    if (sync.error_code) return `${progress} · 等待重试`
    return `${progress} · 正在同步`
  }
  if (sync.status === 'PARTIALLY_SUCCEEDED') return `本批已同步 ${sync.fetched_count} 项 · 还有历史记录可继续读取`
  if (sync.status === 'FAILED') return `同步中断：${sync.error_message ?? sync.error_code ?? '请稍后重试'}`
  return ''
})
const visibleItems = computed(() => items.value.filter((item) => {
  const task = taskByItem.value.get(item.id)
  const text = `${item.title} ${item.pull_request?.number ?? ''} ${item.pull_request?.headRef ?? ''}`.toLowerCase()
  if (query.value.trim() && !text.includes(query.value.trim().toLowerCase())) return false
  if (activeFilter.value === 'READY') return !task
  if (activeFilter.value === 'REVIEWING') return Boolean(task && !task.published_record_id)
  if (activeFilter.value === 'FORMALIZED') return Boolean(task?.published_record_id)
  return true
}))

function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
}

function pullRequestState(item: DeliveryItem) {
  if (item.pull_request?.mergedAt) return '已合并'
  if (item.pull_request?.draft) return '草稿'
  return '待合并'
}

function reviewState(task: VerificationTask | undefined) {
  if (!task) return '尚未审查'
  return ({ DRAFT: '待准备', ANALYZING: '审查中', DRAFT_READY: '待提交', NEEDS_EVIDENCE: '待补证', NEEDS_CONFIRMATION: '待确认', PENDING_REVIEW: '待审批', APPROVED: '已批准', PUBLISHED: '已固化' } as Record<string, string>)[task.cycle_status] ?? task.cycle_status
}

async function load() {
  clearTimeout(pollTimer)
  loadError.value = ''
  const projectId = selectedProjectId.value
  if (!projectId) { items.value = []; tasks.value = []; syncs.value = []; return }
  try {
    const [deliveryItems, taskList, syncList] = await Promise.all([
      apiRequest<DeliveryItem[]>(`/projects/${projectId}/delivery-items`, { headers: projectHeaders() }),
      apiRequest<VerificationTask[]>(`/projects/${projectId}/verification-tasks`, { headers: projectHeaders() }),
      apiRequest<SyncRun[]>(`/projects/${projectId}/source-sync-runs`, { headers: projectHeaders() }),
    ])
    if (projectId !== selectedProjectId.value) return
    items.value = deliveryItems.filter((item) => Boolean(item.pull_request))
    tasks.value = taskList
    syncs.value = syncList
    message.value = syncProgress.value
    if (!disposed && syncs.value.some(sync => sync.status === 'RUNNING')) {
      pollTimer = setTimeout(() => { void load() }, 2000)
    }
  } catch (error) {
    if (projectId === selectedProjectId.value) {
      loadError.value = error instanceof Error ? error.message : '代码交付加载失败'
      message.value = loadError.value
    }
  }
}

async function retrySync() {
  const projectId = selectedProjectId.value
  const sync = latestSync.value
  if (!projectId || !sync || syncRetrying.value) return
  syncRetrying.value = true
  try {
    await apiRequest(`/projects/${projectId}/external-connections/${sync.connection_id}/sync`, {
      method: 'POST',
      headers: projectHeaders(true),
    })
    message.value = '已重新提交同步，正在后台处理，请稍后刷新。'
    await load()
  } catch (error) {
    message.value = error instanceof Error ? `重试同步失败：${error.message}` : '重试同步失败，请稍后重试。'
  } finally {
    syncRetrying.value = false
  }
}

async function createReview(item: DeliveryItem) {
  const projectId = selectedProjectId.value
  if (!projectId || taskByItem.value.has(item.id)) return
  busyItemId.value = item.id
  try {
    const task = await apiRequest<CreatedTask>(`/projects/${projectId}/verification-tasks`, {
      method: 'POST',
      headers: projectHeaders(true),
      body: JSON.stringify({
        title: item.title,
        requirement_key: `pr:${item.id}`,
        delivery_item_id: item.id,
      }),
    })
    await router.push(`/tasks/${task.id}/notebook`)
  } catch (error) {
    message.value = error instanceof Error ? `创建审查失败：${error.message}` : '创建审查失败，请稍后重试。'
  } finally {
    busyItemId.value = null
  }
}

watch(selectedProjectId, () => { void load() }, { immediate: true })
onBeforeUnmount(() => { disposed = true; clearTimeout(pollTimer) })
</script>

<template>
  <section class="page page-tasks">
    <header class="page-heading">
      <div>
        <h1>代码交付</h1>

        <p v-if="!selectedProject">请先选择项目。</p>
      </div>
    </header>
    <p v-if="items.length && message" class="page-context-note" aria-live="polite">{{ message }} <button v-if="canContinueSync" type="button" :disabled="syncRetrying" @click="retrySync">{{ syncRetrying ? '正在提交…' : syncFailed ? '重试同步' : '继续同步' }}</button></p>

    <template v-if="selectedProject">
      <div class="filter-row task-filters">
        <div class="filter-tabs">
          <button :class="{ active: activeFilter === 'ALL' }" type="button" @click="activeFilter = 'ALL'">全部 PR</button>
          <button :class="{ active: activeFilter === 'READY' }" type="button" @click="activeFilter = 'READY'">待审查</button>
          <button :class="{ active: activeFilter === 'REVIEWING' }" type="button" @click="activeFilter = 'REVIEWING'">审查中</button>
          <button :class="{ active: activeFilter === 'FORMALIZED' }" type="button" @click="activeFilter = 'FORMALIZED'">已固化</button>
        </div>
        <input v-model="query" placeholder="搜索 PR 标题、编号或分支" aria-label="搜索代码交付" />
      </div>

      <section class="surface code-delivery-list">
        <div v-if="visibleItems.length" class="data-table task-table">
          <div class="table-row table-header"><span>代码交付</span><span>分支范围</span><span>合并状态</span><span>审查状态</span><span>同步时间</span><span>操作</span></div>
          <div v-for="item in visibleItems" :key="item.id" class="table-row">
            <strong>
              <a v-if="item.web_url" :href="item.web_url" target="_blank" rel="noreferrer">PR #{{ item.pull_request?.number }} · {{ item.title }}</a>
              <template v-else>PR #{{ item.pull_request?.number }} · {{ item.title }}</template>
              <small>{{ item.pull_request?.changedFiles == null ? '变更文件数将在审查时确认' : `${item.pull_request?.changedFiles} 个变更文件` }}</small>
            </strong>
            <span class="pr-branch-range">{{ item.pull_request?.headRef || '未知来源分支' }} → {{ item.pull_request?.baseRef || '未知目标分支' }}</span>
            <span>{{ pullRequestState(item) }}</span>
            <span><span class="status-mark" :data-status="taskByItem.get(item.id)?.cycle_status">{{ reviewState(taskByItem.get(item.id)) }}</span></span>
            <time>{{ formatDate(item.source_updated_at) }}</time>
            <div class="task-row-actions">
              <RouterLink v-if="taskByItem.get(item.id)" :to="`/tasks/${taskByItem.get(item.id)?.id}/notebook`">继续审查</RouterLink>
              <button v-else type="button" :disabled="busyItemId !== null" @click="createReview(item)">{{ busyItemId === item.id ? '正在打开…' : '进入审查' }}</button>
            </div>
          </div>
        </div>
        <div v-else class="delivery-empty-state">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="5" r="2.5" /><circle cx="6" cy="19" r="2.5" /><circle cx="18" cy="19" r="2.5" /><path d="M6 7.5v9M18 16.5v-6a5 5 0 0 0-5-5h-1m2.5-2.5L12 5.5 14.5 8" /></svg>
          <template v-if="loadError"><h2>暂时无法读取代码交付</h2><p>{{ loadError }}</p><button type="button" class="secondary" @click="load">重新加载</button></template>
          <template v-else-if="syncFailed">
            <h2>{{ latestSync?.error_code === 'SOURCE_RATE_LIMITED' ? 'GitHub 读取额度暂时用完了' : '这次同步还没有完成' }}</h2>
            <p>{{ latestSync?.error_code === 'SOURCE_RATE_LIMITED' ? '仓库连接已保存，请在 GitHub 读取额度恢复后重试。' : latestSync?.error_message ?? '请检查仓库连接，或稍后重新同步。' }}</p>
            <button type="button" class="primary-button" :disabled="syncRetrying" @click="retrySync">{{ syncRetrying ? '正在提交…' : '重试同步' }}</button>
          </template>
          <template v-else-if="syncInProgress">
            <h2>{{ latestSync?.error_code === 'SOURCE_RATE_LIMITED' ? '等待 GitHub 额度恢复' : '正在读取 GitHub 代码交付' }}</h2><p aria-live="polite">{{ syncProgress }}</p>
          </template>
          <template v-else-if="latestSync?.status === 'PARTIALLY_SUCCEEDED'"><h2>本批同步完成</h2><p>{{ syncProgress }}</p><button type="button" class="primary-button" :disabled="syncRetrying" @click="retrySync">{{ syncRetrying ? '正在提交…' : '继续同步' }}</button></template>
          <template v-else-if="items.length"><h2>没有找到匹配的 Pull Request</h2><p>试试其他关键词，或切换到“全部 PR”。</p><button type="button" class="secondary" @click="query = ''; activeFilter = 'ALL'">查看全部 PR</button></template>
          <template v-else><h2>等待第一份代码交付</h2><p>接入仓库并同步 Pull Request。</p><RouterLink class="primary-button" to="/settings">查看仓库连接</RouterLink></template>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.delivery-empty-state { display: flex; flex: 1; min-height: 300px; flex-direction: column; align-items: center; justify-content: center; gap: 16px; padding: 48px 28px; text-align: center; }
.delivery-empty-state > svg { box-sizing: content-box; width: 28px; height: 28px; padding: 16px; margin-bottom: 4px; border-radius: 18px; background: var(--brand-soft); color: var(--brand); }
.delivery-empty-state h2 { margin: 0; color: var(--ink); font-size: 21px; line-height: 1.5; font-weight: 600; }
.delivery-empty-state p { max-width: 52ch; margin: 0 0 6px; color: var(--muted); font-size: 15px; line-height: 1.85; text-wrap: pretty; }
</style>
