<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { apiRequest, projectHeaders, selectedProject, selectedProjectId } from '../features/projects/project-context'

interface DeliveryItem { id: string; external_key: string; title: string; planning_status: string; verification_status: string; source_updated_at: string | null }
interface VerificationTask { id: string; delivery_item_id: string | null; title: string; cycle_status: string; published_record_id: string | null }
interface ProjectReport { id: string; task_title: string; status: string; submitted_at: string | null; latest_approval_action: string | null }
interface PublishedRecord { id: string; task_title: string; record_no: string; published_at: string; approval_by_name: string | null }

type WorkAction = { title: string; description: string; to: string; label: string }

const deliveryItems = ref<DeliveryItem[]>([])
const tasks = ref<VerificationTask[]>([])
const reports = ref<ProjectReport[]>([])
const records = ref<PublishedRecord[]>([])
const busy = ref(false)
const message = ref('选择项目后，将显示当前工作和已留档的交付。')
const openProjectCreate = inject<() => void>('openProjectCreate', () => undefined)
const welcomeFeatures = [
  { title: '代码问题审查', description: '围绕 Pull Request 的实际变更分析潜在问题，结合相关代码理解影响，并查看问题所在的文件与位置。', icon: 'm8 5-7 7 7 7m8-14 7 7-7 7M14 3l-4 18' },
  { title: '交付内容核验', description: '从 PR 描述中提取本次交付内容，确认后逐项核对实现依据，区分代码支持、证据不足和存在冲突的结论。', icon: 'M9 3h6v4H9zM9 5H5v16h14V5h-4m-7 9 3 3 5-6' },
  { title: '知识库与证据定位', description: '关联需求、接口说明等项目资料，在审查时对照引用原文和代码 Diff，理解每条结论的依据。', icon: 'M12 5v16M3 3h5a4 4 0 0 1 4 2 4 4 0 0 1 4-2h5v16h-5a4 4 0 0 0-4 2 4 4 0 0 0-4-2H3Z' },
  { title: '人工审批与交付留档', description: '对审查结果作出人工判断，提交报告并由其他成员审批，形成可以回看结论与证据的交付记录。', icon: 'M5 3h10l4 4v14H5ZM14 3v5h5M8 12h8m-8 4h6' },
]

const taskByItemId = computed(() => new Map(tasks.value.filter((task) => task.delivery_item_id).map((task) => [task.delivery_item_id as string, task])))
const unreviewedItems = computed(() => deliveryItems.value.filter((item) => !taskByItemId.value.has(item.id)))

const primaryAction = computed<WorkAction>(() => {
  if (!deliveryItems.value.length) return { title: '接入代码交付', description: '先同步 GitHub Pull Request，再开始审查一次实际代码变更。', to: '/settings', label: '接入 GitHub 仓库' }
  if (unreviewedItems.value.length) return { title: '开始代码审查', description: `有 ${unreviewedItems.value.length} 个 Pull Request 尚未建立审查。`, to: '/tasks', label: '查看待审 PR' }
  if (reports.value.length) return { title: '处理人工确认', description: `有 ${reports.value.length} 份报告已提交，等待不同成员确认。`, to: '/approvals', label: '前往确认' }
  return { title: '继续代码审查', description: '已建立审查任务；选择一项 PR，继续审查并处理结果。', to: '/tasks', label: '查看代码交付' }
})

const recentWork = computed(() => deliveryItems.value.slice(0, 4))
const progressStages = computed(() => [
  { label: '代码交付已接入', value: deliveryItems.value.length, detail: deliveryItems.value.length ? `已同步 ${deliveryItems.value.length} 个 PR` : '尚未接入 PR' },
  { label: '已建立审查', value: tasks.value.length, detail: tasks.value.length ? `已建立 ${tasks.value.length} 个审查任务` : '尚未建立审查任务' },
  { label: '等待人工确认', value: reports.value.length, detail: reports.value.length ? `${reports.value.length} 份报告待确认` : '当前没有待确认报告' },
  { label: '交付已留档', value: records.value.length, detail: records.value.length ? `已保留 ${records.value.length} 条记录` : '尚未形成留档记录' },
])

function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
}

function planningLabel(value: string) {
  return ({ OPEN: '未开始', IN_PROGRESS: '进行中', DECLARED_DONE: '已声明完成', CANCELLED: '已取消' } as Record<string, string>)[value] ?? value
}

function verificationLabel(value: string) {
  return ({ NOT_ASSESSED: '尚未审查', PARTIALLY_SUPPORTED: '部分有依据', CONFIRMED: '已确认', CONFLICT: '需要核对', INSUFFICIENT_EVIDENCE: '依据不足' } as Record<string, string>)[value] ?? value
}

async function loadDashboard() {
  const projectId = selectedProjectId.value
  if (!projectId) {
    deliveryItems.value = []; tasks.value = []; reports.value = []; records.value = []
    return
  }
  busy.value = true
  message.value = '正在读取当前项目的事项、审查和留档记录。'
  try {
    const [items, taskList, reportList, recordList] = await Promise.all([
      apiRequest<DeliveryItem[]>(`/projects/${projectId}/delivery-items`, { headers: projectHeaders() }),
      apiRequest<VerificationTask[]>(`/projects/${projectId}/verification-tasks`, { headers: projectHeaders() }),
      apiRequest<ProjectReport[]>(`/projects/${projectId}/report-versions?status_filter=SUBMITTED`, { headers: projectHeaders() }),
      apiRequest<PublishedRecord[]>(`/projects/${projectId}/published-records`, { headers: projectHeaders() }),
    ])
    if (projectId !== selectedProjectId.value) return
    deliveryItems.value = items; tasks.value = taskList; reports.value = reportList; records.value = recordList
    message.value = ''
  } catch (error) {
    if (projectId !== selectedProjectId.value) return
    message.value = error instanceof Error ? error.message : '项目工作台加载失败'
  } finally {
    if (projectId === selectedProjectId.value) busy.value = false
  }
}

watch(selectedProjectId, () => { void loadDashboard() }, { immediate: true })
</script>

<template>
  <section class="page page-home">
    <header v-if="selectedProject" class="home-project-heading">
      <div><h2>{{ selectedProject?.name || '工作台' }}</h2><p>{{ selectedProject?.description || (selectedProject ? '查看当前待办，继续最近的审查。' : '从一次代码交付，开始有依据的审查。') }}</p></div>
      <RouterLink v-if="selectedProject" class="home-project-settings" to="/settings">项目设置 <span aria-hidden="true">→</span></RouterLink>
    </header>
    <section v-if="!selectedProject" class="home-welcome" aria-labelledby="welcome-title">
      <div class="welcome-overview">
        <header class="welcome-heading">
          <h2 id="welcome-title">看清每次交付，<br />找到结论依据。</h2>
          <p>从 Pull Request 开始审查，查看证据与交付结论。</p>
        </header>
        <section class="welcome-capabilities" aria-labelledby="welcome-capabilities-title">
          <h3 id="welcome-capabilities-title">你可以在这里做什么</h3>
          <dl class="welcome-feature-list">
            <div v-for="feature in welcomeFeatures" :key="feature.title" class="welcome-feature-row">
              <dt><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="feature.icon" /></svg><span>{{ feature.title }}</span></dt>
              <dd>{{ feature.description }}</dd>
            </div>
          </dl>
        </section>
      </div>
      <aside class="welcome-start" aria-labelledby="welcome-start-title">
        <div class="welcome-start-symbol" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1ZM12 10v7m-3-3h6" /></svg></div>
        <h3 id="welcome-start-title">开启第一轮审查</h3>
        <p>接入仓库，开始审查。</p>
        <ol class="welcome-steps">
          <li><strong>创建并接入项目</strong><p>填写项目名称与仓库地址，系统会同步 Pull Request。</p></li>
          <li><strong>选择一次代码交付</strong><p>打开待审查的 PR，提取并确认本次交付内容。</p></li>
          <li><strong>开始审查，核对结果</strong><p>自动保存本轮输入，结合证据查看结论并完成人工确认。</p></li>
        </ol>
        <button class="primary-button" type="button" @click="openProjectCreate">创建并接入项目 <span aria-hidden="true">→</span></button>
        <p class="welcome-start-note">只读接入 GitHub · 知识库资料可选</p>
      </aside>
    </section>
    <template v-else>
      <p v-if="message" class="home-data-note" :class="{ loading: busy }" role="status">{{ message }}</p>
      <section class="home-next-action" :aria-busy="busy">
        <div><h2 class="home-action-heading">{{ primaryAction.title }}</h2><p>{{ primaryAction.description }}</p></div>
        <RouterLink class="primary-button" :to="primaryAction.to">{{ primaryAction.label }} <span aria-hidden="true">→</span></RouterLink>
      </section>
      <div class="home-progress-summary" aria-label="项目工作概况">
        <div v-for="stage in progressStages" :key="stage.label"><span>{{ stage.label }}</span><strong>{{ stage.value }}</strong></div>
      </div>
      <section class="home-work-section">
        <div class="home-section-heading"><h2>最近审查</h2><RouterLink to="/tasks">全部代码交付 <span aria-hidden="true">→</span></RouterLink></div>
        <div v-if="recentWork.length" class="home-work-list">
          <RouterLink v-for="item in recentWork" :key="item.id" class="home-work-row" :to="taskByItemId.get(item.id) ? `/tasks/${taskByItemId.get(item.id)?.id}/notebook` : '/tasks'">
            <span class="home-pr-symbol" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="7" cy="5" r="2"/><circle cx="7" cy="19" r="2"/><circle cx="17" cy="19" r="2"/><path d="M7 7v10M17 17V9a4 4 0 0 0-4-4h-1m2-2-2 2 2 2"/></svg></span>
            <div><strong>{{ item.title }}</strong><small>{{ item.external_key }}</small></div><span class="status-mark">{{ verificationLabel(item.verification_status) }}</span><span class="home-row-arrow" aria-hidden="true">→</span>
          </RouterLink>
        </div>
        <p v-else class="home-empty-copy">暂无审查记录。接入 Pull Request 后，在这里继续你的工作。</p>
      </section>
      <section class="home-work-section">
        <div class="home-section-heading"><h2>近期交付记录</h2><RouterLink to="/deliveries">全部记录 <span aria-hidden="true">→</span></RouterLink></div>
        <div v-if="records.length" class="data-table delivery-table home-record-table">
          <div class="table-row table-header"><span>记录编号</span><span>关联工作</span><span>确认人</span><span>留档时间</span></div>
          <RouterLink v-for="record in records.slice(0, 4)" :key="record.id" class="table-row table-button" :to="`/deliveries/${record.id}`"><strong>{{ record.record_no }}</strong><span>{{ record.task_title }}</span><span>{{ record.approval_by_name || '—' }}</span><time>{{ formatDate(record.published_at) }}</time></RouterLink>
        </div>
        <p v-else class="home-empty-copy">完成审查与人工确认后，交付记录会保留在这里。</p>
      </section>
    </template>
  </section>
</template>
