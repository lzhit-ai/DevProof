<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiRequest, projectHeaders, selectedProject, selectedProjectId } from '../features/projects/project-context'

interface HealthSnapshot { id: string; as_of: string; snapshot_hash: string; scope: Record<string, unknown>; summary: Record<string, unknown>; coverage: { dataGaps?: string[] } }
interface SummaryDraft { id: string; period_type: string; title: string; draft_status: string; updated_at: string }
interface SummaryRecord { id: string; record_no: string; confirmation_type: string; published_at: string }
interface PeripheralProfileRun { id: string; assessment_profile: string; run_status: string; input_hash: string; output: Record<string, unknown>; coverage: Record<string, unknown>; limitations: string[]; created_at: string }

const snapshots = ref<HealthSnapshot[]>([])
const drafts = ref<SummaryDraft[]>([])
const records = ref<SummaryRecord[]>([])
const profileRuns = ref<PeripheralProfileRun[]>([])
const busy = ref(false)
const message = ref('')
const latest = computed(() => snapshots.value[0] ?? null)
const latestStatusRun = computed(() => profileRuns.value.find((run) => run.assessment_profile === 'PROJECT_STATUS_SUMMARY') ?? null)

function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) }
function count(value: unknown) { return typeof value === 'number' ? value : '—' }
function mapCount(summary: Record<string, unknown>, key: string) { const value = summary[key]; return value && typeof value === 'object' ? Object.entries(value as Record<string, unknown>) : [] }
function serialise(value: unknown) { return JSON.stringify(value ?? {}, null, 2) }

async function load() {
  const projectId = selectedProjectId.value
  if (!projectId) { snapshots.value = []; drafts.value = []; records.value = []; profileRuns.value = []; return }
  busy.value = true
  try {
    const [health, draftList, recordList, runs] = await Promise.all([
      apiRequest<HealthSnapshot[]>(`/projects/${projectId}/health-snapshots`, { headers: projectHeaders() }),
      apiRequest<SummaryDraft[]>(`/projects/${projectId}/project-summary-drafts`, { headers: projectHeaders() }),
      apiRequest<SummaryRecord[]>(`/projects/${projectId}/project-summary-records`, { headers: projectHeaders() }),
      apiRequest<PeripheralProfileRun[]>(`/projects/${projectId}/peripheral-profile-runs`, { headers: projectHeaders() }),
    ])
    if (projectId !== selectedProjectId.value) return
    snapshots.value = health; drafts.value = draftList; records.value = recordList; profileRuns.value = runs
    message.value = health.length ? '' : '暂无态势快照。'
  } catch (error) { if (projectId === selectedProjectId.value) message.value = error instanceof Error ? error.message : '项目态势加载失败' } finally { if (projectId === selectedProjectId.value) busy.value = false }
}

async function createStatusRun() {
  const projectId = selectedProjectId.value
  const snapshot = latest.value
  if (!projectId || !snapshot) return
  busy.value = true
  try {
    await apiRequest<PeripheralProfileRun>(`/projects/${projectId}/peripheral-profile-runs`, {
      method: 'POST', headers: projectHeaders(true), body: JSON.stringify({ assessment_profile: 'PROJECT_STATUS_SUMMARY', health_snapshot_id: snapshot.id }),
    })
    message.value = '态势快照已保存。'
    await load()
  } catch (error) { message.value = error instanceof Error ? error.message : '项目态势运行创建失败' } finally { busy.value = false }
}

watch(selectedProjectId, () => { void load() }, { immediate: true })
</script>

<template>
  <section class="page page-status"><header class="page-heading"><div><h1>项目态势</h1><p v-if="!selectedProject">请先选择项目。</p></div></header><p class="page-context-note">{{ message }}</p>
    <template v-if="selectedProject && latest"><section class="surface status-summary"><div class="surface-heading"><h2>最新态势快照</h2><time>{{ formatDate(latest.as_of) }}</time></div><div class="state-brief-grid"><div><strong>纳入事项</strong><p>{{ count(latest.summary.plannedItemCount) }} 项</p></div><div><strong>正式记录覆盖</strong><p>{{ count(latest.summary.formalRecordItemCount) }} 项已有正式记录；{{ count(latest.summary.confirmedChangeLinkedItemCount) }} 项已确认变更归属。</p></div><div><strong>待归属开发活动</strong><p>{{ count((latest.summary.unattributedActivity as Record<string, unknown> | undefined)?.gitSnapshotCount) }} 个冻结 Git 范围尚未归属到事项。</p></div></div><div class="status-breakdown"><section><h3>外部计划状态</h3><p v-for="[status, value] in mapCount(latest.summary, 'planningStatusCounts')" :key="status"><span>{{ status }}</span><strong>{{ value }}</strong></p></section><section><h3>本系统核验状态</h3><p v-for="[status, value] in mapCount(latest.summary, 'verificationStatusCounts')" :key="status"><span>{{ status }}</span><strong>{{ value }}</strong></p></section><section><h3>数据缺口</h3><p v-if="latest.coverage.dataGaps?.length" v-for="gap in latest.coverage.dataGaps" :key="gap">{{ gap }}</p><p v-else>当前快照未记录数据缺口。</p></section></div><details class="ui-disclosure"><summary>版本信息</summary><p class="immutable-note"><code>{{ latest.snapshot_hash }}</code></p></details></section>
      <section class="surface profile-run-panel"><div class="surface-heading"><div><h2>态势总结运行</h2></div><button class="primary-button" type="button" :disabled="busy" @click="createStatusRun">固化本次运行</button></div><template v-if="latestStatusRun"><div class="profile-run-record"><div><strong>最近运行</strong><p>{{ formatDate(latestStatusRun.created_at) }} · {{ latestStatusRun.run_status }}</p></div><div><strong>输入哈希</strong><p>{{ latestStatusRun.input_hash }}</p></div></div><pre class="profile-run-output">{{ serialise(latestStatusRun.output) }}</pre><p v-for="item in latestStatusRun.limitations" :key="item" class="profile-run-limit">{{ item }}</p></template><p v-else class="empty-row">暂无态势运行。</p></section>
      <section class="surface"><div class="surface-heading"><h2>总结草稿与已确认记录</h2></div><div class="data-table"><div class="table-row table-header"><span>类型</span><span>标题或记录号</span><span>状态</span><span>更新时间</span></div><div v-for="draft in drafts" :key="draft.id" class="table-row"><span>{{ draft.period_type }}</span><strong>{{ draft.title }}</strong><span>{{ draft.draft_status }}</span><time>{{ formatDate(draft.updated_at) }}</time></div><div v-for="record in records" :key="record.id" class="table-row"><span>已确认总结</span><strong>{{ record.record_no }}</strong><span>{{ record.confirmation_type }}</span><time>{{ formatDate(record.published_at) }}</time></div></div><p v-if="!drafts.length && !records.length" class="empty-row">暂无项目总结草稿或已确认的总结记录。</p></section>
    </template>
  </section>
</template>
