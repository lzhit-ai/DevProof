<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { apiRequest, projectHeaders, selectedProject, selectedProjectId } from '../features/projects/project-context'

interface PublishedRecord { id: string; task_title: string; requirement_key: string; report_sequence_no: number; report_status: string; snapshot_hash: string; record_type: string; record_no: string; record_hash: string; published_by_name: string | null; published_at: string; approval_action: string | null; approval_reason: string | null; approval_by_name: string | null; approval_at: string | null }
const route = useRoute()
const record = ref<PublishedRecord | null>(null)
const message = ref('正式记录一经固化不可编辑；后续变更需要新的输入快照和新的记录。')
const busy = ref(false)

function formatDate(value: string | null) { return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—' }

async function load() {
  const projectId = selectedProjectId.value
  const recordId = String(route.params.deliveryId ?? '')
  if (!projectId || !recordId) { record.value = null; return }
  busy.value = true
  try {
    record.value = await apiRequest<PublishedRecord>(`/projects/${projectId}/published-records/${recordId}`, { headers: projectHeaders() })
  } catch (error) { record.value = null; message.value = error instanceof Error ? error.message : '正式记录加载失败' } finally { busy.value = false }
}

watch([selectedProjectId, () => route.params.deliveryId], () => { void load() }, { immediate: true })
</script>

<template>
  <section class="page page-detail"><RouterLink class="back-link" to="/deliveries">返回正式记录</RouterLink><header class="page-heading detail-heading"><div><h1>正式记录详情</h1><p v-if="record">{{ record.task_title }} · 只读正式版本</p><p v-else>读取当前项目中已固化的交付记录。</p></div><span v-if="record" class="status-mark success">已固化</span></header><p class="page-context-note">{{ message }}</p>
    <section v-if="record && selectedProject" class="surface formal-document"><div class="record-meta"><span>记录号：{{ record.record_no }}</span><span>报告版本：v{{ record.report_sequence_no }}</span><span>需求标识：{{ record.requirement_key }}</span><span>固化时间：{{ formatDate(record.published_at) }}</span></div><div class="document-section"><h2>版本信息</h2><dl class="run-details"><div><dt>记录哈希</dt><dd>{{ record.record_hash }}</dd></div><div><dt>输入快照哈希</dt><dd>{{ record.snapshot_hash }}</dd></div><div><dt>记录类型</dt><dd>{{ record.record_type }}</dd></div><div><dt>固化人</dt><dd>{{ record.published_by_name || '—' }}</dd></div></dl></div><div class="document-section two-column"><div><h2>报告审批</h2><p>{{ record.approval_action || '—' }} · {{ record.approval_by_name || '—' }}</p><p>{{ formatDate(record.approval_at) }}</p></div><div><h2>审批说明</h2><p>{{ record.approval_reason || '无审批说明' }}</p></div></div></section>
  </section>
</template>
