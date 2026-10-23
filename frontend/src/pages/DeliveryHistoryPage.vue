<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { apiRequest, projectHeaders, selectedProject, selectedProjectId } from '../features/projects/project-context'

interface PublishedRecord { id: string; task_title: string; requirement_key: string; report_sequence_no: number; snapshot_hash: string; record_no: string; approval_action: string | null; approval_by_name: string | null; published_at: string }

const records = ref<PublishedRecord[]>([])
const query = ref('')
const message = ref('')
const busy = ref(false)
const visibleRecords = computed(() => { const q = query.value.trim().toLowerCase(); return q ? records.value.filter((record) => `${record.record_no} ${record.task_title} ${record.requirement_key}`.toLowerCase().includes(q)) : records.value })

function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) }

async function load() {
  const projectId = selectedProjectId.value
  if (!projectId) { records.value = []; return }
  busy.value = true
  try {
    const list = await apiRequest<PublishedRecord[]>(`/projects/${projectId}/published-records`, { headers: projectHeaders() })
    if (projectId !== selectedProjectId.value) return
    records.value = list
    message.value = list.length ? '' : ''
  } catch (error) { if (projectId === selectedProjectId.value) message.value = error instanceof Error ? error.message : '正式记录加载失败' } finally { if (projectId === selectedProjectId.value) busy.value = false }
}

watch(selectedProjectId, () => { void load() }, { immediate: true })
</script>

<template>
  <section class="page page-history"><header class="page-heading"><div><h1>正式记录</h1><p v-if="!selectedProject">请先选择项目。</p></div></header><p class="page-context-note">{{ message }}</p>
    <template v-if="selectedProject"><div class="filter-row"><input v-model="query" placeholder="搜索记录号、核验任务或需求标识" /></div><section class="surface history-list"><div v-if="visibleRecords.length" class="data-table history-table"><div class="table-row table-header"><span>正式记录</span><span>报告版本</span><span>关联任务</span><span>输入快照</span><span>审批结果</span><span>审批人</span><span>固化时间</span></div><RouterLink v-for="record in visibleRecords" :key="record.id" class="table-row table-button" :to="`/deliveries/${record.id}`"><strong>{{ record.record_no }}</strong><span>v{{ record.report_sequence_no }}</span><span>{{ record.task_title }}</span><span>{{ record.snapshot_hash.slice(0, 12) }}…</span><span>{{ record.approval_action || '—' }}</span><span>{{ record.approval_by_name || '—' }}</span><time>{{ formatDate(record.published_at) }}</time></RouterLink></div><p v-else class="empty-row">没有符合当前筛选条件的正式记录。</p></section></template>
  </section>
</template>
