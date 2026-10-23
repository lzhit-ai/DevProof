<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { apiRequest, projectHeaders, selectedProject, selectedProjectId } from '../features/projects/project-context'

interface ProjectReport { id: string; task_title: string; sequence_no: number; submitted_by_name: string | null; editorial_note: string; submitted_at: string | null; snapshot_hash: string; latest_approval_reason: string | null }

const reports = ref<ProjectReport[]>([])
const query = ref('')
const busy = ref(false)
const message = ref('')
const visibleReports = computed(() => { const q = query.value.trim().toLowerCase(); return q ? reports.value.filter((report) => `${report.task_title} ${report.submitted_by_name ?? ''}`.toLowerCase().includes(q)) : reports.value })

function formatDate(value: string | null) { return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—' }

async function load() {
  const projectId = selectedProjectId.value
  if (!projectId) { reports.value = []; return }
  busy.value = true
  try {
    const list = await apiRequest<ProjectReport[]>(`/projects/${projectId}/report-versions?status_filter=SUBMITTED`, { headers: projectHeaders() })
    if (projectId !== selectedProjectId.value) return
    reports.value = list
    message.value = list.length ? '' : ''
  } catch (error) { if (projectId === selectedProjectId.value) message.value = error instanceof Error ? error.message : '待审批队列加载失败' } finally { if (projectId === selectedProjectId.value) busy.value = false }
}

watch(selectedProjectId, () => { void load() }, { immediate: true })
</script>

<template>
  <section class="page page-approvals"><header class="page-heading"><div><h1>待审批队列</h1><p v-if="!selectedProject">请先选择项目。</p></div></header><p class="page-context-note">{{ message }}</p>
    <template v-if="selectedProject"><div class="filter-row"><input v-model="query" placeholder="搜索核验任务或提交人" /></div><section class="surface"><div v-if="visibleReports.length" class="data-table approval-table"><div class="table-row table-header"><span>核验任务</span><span>报告版本</span><span>提交人</span><span>输入快照</span><span>待确认原因</span><span>提交时间</span></div><RouterLink v-for="report in visibleReports" :key="report.id" class="table-row table-button" :to="`/approvals/${report.id}`"><strong>{{ report.task_title }}</strong><span>v{{ report.sequence_no }}</span><span>{{ report.submitted_by_name || '—' }}</span><span>{{ report.snapshot_hash.slice(0, 12) }}…</span><span>{{ report.latest_approval_reason || report.editorial_note || '等待审批人基于引用证据作出决定' }}</span><time>{{ formatDate(report.submitted_at) }}</time></RouterLink></div><p v-else class="empty-row">没有符合当前筛选条件的待审批报告。</p></section></template>
  </section>
</template>
