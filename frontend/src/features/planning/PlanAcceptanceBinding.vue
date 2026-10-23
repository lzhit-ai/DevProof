<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { apiRequest, projectHeaders } from '../projects/project-context'
import type { PlanVersion, PlanningPermissions } from './types'

export interface PlanClaimReference {
  planVersionId: string; planContentHash: string; issueKey: string; acceptanceKey: string; condition: string
}
interface Mapping { issueKey: string; acceptanceKey: string; claimId: string; claimKey: string; criterion: { condition: string } }
interface Selection {
  id: string; sequence_no: number; content_hash: string
  body: { planVersionId: string; planContentHash: string; ideaRevisionNo: number; planSequenceNo: number; planningTargetSha: string; mappings: Mapping[] }
}
interface SelectionState { selection: Selection | null; frozen: boolean; history: Selection[] }
interface PlanOption { id: string; title: string; idea_revision_no: number; sequence_no: number; status: string; target_sha: string }
interface SubmittedClaim { id?: string; text: string; planAcceptance?: PlanClaimReference }
interface ConfirmedClaim { id: string; text: string }
interface TraceRun { snapshot_id: string; run_id: string | null; run_status: string | null; target_sha: string; plan_version_id: string; selection_id: string; results: { claim_key: string; status: string | null }[]; reports: { id: string; sequence_no: number; status: string; record_no: string | null }[] }
const props = defineProps<{ projectId: string; cycleId: string; frozen: boolean; disabled: boolean }>()
const emit = defineEmits<{ apply: []; clear: [] }>()
const selection = ref<Selection | null>(null)
const history = ref<Selection[]>([])
const options = ref<PlanOption[]>([])
const plan = ref<PlanVersion | null>(null)
const selectedPlanId = ref('')
const checked = ref<string[]>([])
const importedPlan = ref<{ id: string; hash: string } | null>(null)
const canEdit = ref(false)
const loading = ref(false)
const choosing = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')
const loaded = ref(false)
const frozenOnServer = ref(false)
const trace = ref<TraceRun[] | null>(null)
let scopeVersion = 0
let planRequest = 0
let loadRequest: Promise<void> = Promise.resolve()
const locked = computed(() => props.frozen || frozenOnServer.value)
const disabled = computed(() => props.disabled || loading.value || choosing.value || saving.value || !canEdit.value || locked.value)
const criteria = computed(() => plan.value?.body.issues.flatMap(issue => issue.acceptanceCriteria.map(criterion => ({
  issue, criterion, key: JSON.stringify([issue.key, criterion.key]),
}))) ?? [])
const path = () => `/projects/${props.projectId}/cycles/${props.cycleId}`

async function load(reset = true) {
  const version = ++scopeVersion
  ++planRequest
  const base = path(), project = props.projectId
  if (reset) {
    selection.value = null; history.value = []; options.value = []; plan.value = null
    selectedPlanId.value = ''; checked.value = []; importedPlan.value = null; notice.value = ''; trace.value = null
  }
  error.value = ''; canEdit.value = false
  loaded.value = false; frozenOnServer.value = false; choosing.value = false; saving.value = false; loading.value = true
  const [current, available, permissions] = await Promise.allSettled([
    apiRequest<SelectionState>(`${base}/plan-selection`, { headers: projectHeaders() }),
    apiRequest<PlanOption[]>(`/projects/${project}/plan-options`, { headers: projectHeaders() }),
    apiRequest<PlanningPermissions>(`/projects/${project}/planning-permissions`, { headers: projectHeaders() }),
  ])
  if (version !== scopeVersion) return
  const failures: string[] = []
  if (current.status === 'fulfilled') {
    selection.value = current.value.selection; history.value = current.value.history; frozenOnServer.value = current.value.frozen
    loaded.value = true
  } else failures.push(current.reason instanceof Error ? current.reason.message : '计划关联读取失败')
  if (available.status === 'fulfilled') options.value = available.value
  else failures.push(available.reason instanceof Error ? available.reason.message : '计划列表读取失败')
  if (permissions.status === 'fulfilled') canEdit.value = permissions.value.canPlan
  else failures.push(permissions.reason instanceof Error ? permissions.reason.message : '计划权限读取失败')
  error.value = [...new Set(failures)].join('；')
  loading.value = false
}
watch(() => [props.projectId, props.cycleId], () => { loadRequest = load() }, { immediate: true })

async function choose() {
  const version = scopeVersion, request = ++planRequest, id = selectedPlanId.value
  plan.value = null; checked.value = []; error.value = ''
  if (!id) return
  choosing.value = true
  try {
    const result = await apiRequest<PlanVersion>(`/projects/${props.projectId}/plans/${id}`, { headers: projectHeaders() })
    if (version !== scopeVersion || request !== planRequest) return
    plan.value = result
  } catch (cause) {
    if (version === scopeVersion && request === planRequest) error.value = cause instanceof Error ? cause.message : '计划读取失败'
  } finally { if (version === scopeVersion && request === planRequest) choosing.value = false }
}
function imports() {
  if (!plan.value || !checked.value.length || disabled.value) return null
  const selected = plan.value
  return {
    plan: { id: selected.id, hash: selected.content_hash },
    replaceClaimIds: selection.value?.body.mappings.map(item => item.claimId) ?? [],
    claims: criteria.value.filter(item => checked.value.includes(item.key)).map(item => ({
      planVersionId: selected.id, planContentHash: selected.content_hash,
      issueKey: item.issue.key, acceptanceKey: item.criterion.key, condition: item.criterion.condition,
    })),
  }
}
function markImported(value: { id: string; hash: string }) {
  importedPlan.value = value
  notice.value = '所选验收项已加入交付内容，开始审查时将保存版本关联。'
}
async function beforeFreeze(confirmed: ConfirmedClaim[], submitted: SubmittedClaim[]) {
  await loadRequest
  const version = scopeVersion, base = path()
  let planId: string, hash: string, mappings: { issueKey: string; acceptanceKey: string; claimId: string }[]
  if (importedPlan.value) {
    planId = importedPlan.value.id; hash = importedPlan.value.hash
    mappings = []
    submitted.forEach((item, index) => {
      const reference = item.planAcceptance
      if (!reference) return
      if (reference.planVersionId !== planId || reference.planContentHash !== hash || item.text.trim() !== reference.condition.trim()
          || confirmed[index]?.text.trim() !== reference.condition.trim()) throw new Error('已关联的验收内容发生变化，请重新应用计划验收项')
      mappings.push({ issueKey: reference.issueKey, acceptanceKey: reference.acceptanceKey, claimId: confirmed[index]!.id })
    })
    if (!mappings.length) throw new Error('请至少保留一条所选计划验收项，或先清除计划关联')
  } else if (selection.value) {
    planId = selection.value.body.planVersionId; hash = selection.value.body.planContentHash
    mappings = selection.value.body.mappings.map(item => {
      const claim = confirmed.find(candidate => candidate.id === item.claimId)
      if (!claim || claim.text.trim() !== item.criterion.condition.trim()) throw new Error('已保存的计划验收项已移除或修改，请重新应用或清除计划关联')
      return { issueKey: item.issueKey, acceptanceKey: item.acceptanceKey, claimId: claim.id }
    })
  } else return
  const result = await apiRequest<SelectionState>(`${base}/plan-selection`, {
    method: 'POST', headers: projectHeaders(true), body: JSON.stringify({ planVersionId: planId, planContentHash: hash, expectedSelectionId: selection.value?.id ?? null, mappings }),
  })
  if (version !== scopeVersion) return
  selection.value = result.selection; history.value = result.history; frozenOnServer.value = result.frozen
}
async function clear() {
  if (disabled.value) return
  const version = scopeVersion
  saving.value = true; error.value = ''
  try {
    const result = await apiRequest<SelectionState>(`${path()}/plan-selection`, {
      method: 'DELETE', headers: projectHeaders(true), body: JSON.stringify({ expectedSelectionId: selection.value?.id ?? null }),
    })
    if (version !== scopeVersion) return
    selection.value = result.selection; history.value = result.history; importedPlan.value = null
    emit('clear'); notice.value = '已清除本轮计划关联，交付文本仍保留。'
  } catch (cause) { if (version === scopeVersion) error.value = cause instanceof Error ? cause.message : '清除关联失败' }
  finally { if (version === scopeVersion) saving.value = false }
}
async function readTrace() {
  const version = scopeVersion
  saving.value = true; error.value = ''
  try {
    const result = await apiRequest<{ runs: TraceRun[] }>(`${path()}/plan-trace`, { headers: projectHeaders() })
    if (version === scopeVersion) trace.value = result.runs
  } catch (cause) { if (version === scopeVersion) error.value = cause instanceof Error ? cause.message : '核验关联读取失败' }
  finally { if (version === scopeVersion) saving.value = false }
}
defineExpose({ imports, markImported, beforeFreeze })
</script>

<template>
  <details class="surface plan-acceptance-binding ui-disclosure">
    <summary><span>计划验收关联</span><small>{{ importedPlan ? `待保存关联 · ${importedPlan.id.slice(0, 8)}` : selection ? `Idea v${selection.body.ideaRevisionNo} · 计划 #${selection.body.planSequenceNo} · ${selection.body.mappings.length} 项` : '可选' }}</small></summary>
    <div class="plan-binding-content" :aria-busy="loading || choosing || saving">
      <p v-if="loading" role="status">正在读取计划关联…</p>
      <p v-if="error" role="alert">计划服务：{{ error }}</p>
      <button v-if="error" type="button" :disabled="props.disabled || loading || saving" @click="loadRequest = load(false)">重新读取</button>
      <div v-if="selection" class="plan-binding-baseline">
        <p>已保存计划 <code>{{ selection.body.planVersionId }}</code>，基于提交 <code>{{ selection.body.planningTargetSha.slice(0, 12) }}</code>。</p>
        <ul><li v-for="item in selection.body.mappings" :key="JSON.stringify([item.issueKey, item.acceptanceKey])"><strong>{{ item.issueKey }} / {{ item.acceptanceKey }}</strong> {{ item.criterion.condition }}</li></ul>

      </div>
      <template v-if="!locked && canEdit">
        <label>已确认计划<select v-model="selectedPlanId" :disabled="disabled" @change="choose"><option value="">选择指定版本</option><option v-for="option in options" :key="option.id" :value="option.id">{{ option.title }} · Idea v{{ option.idea_revision_no }} / 计划 #{{ option.sequence_no }}{{ option.status === 'SUPERSEDED' ? '（历史确认版）' : '' }} · {{ option.target_sha.slice(0, 8) }}</option></select></label>
        <p v-if="loaded && !options.length && !error">当前项目没有可选的已确认计划。<RouterLink to="/planning">选择计划</RouterLink></p>
        <p v-if="choosing" role="status">正在读取验收项…</p>
        <label v-for="item in criteria" :key="item.key" class="plan-binding-criterion"><input v-model="checked" type="checkbox" :value="item.key" :disabled="disabled" /><span><strong>{{ item.issue.title }} · {{ item.criterion.key }}</strong>{{ item.criterion.condition }}<small>核验方式：{{ item.criterion.verificationMethod }}；所需证据：{{ item.criterion.requiredEvidence.join('、') }}</small></span></label>
        <div class="plan-binding-actions"><button type="button" :disabled="disabled || !checked.length" @click="emit('apply')">应用所选验收项</button><button v-if="selection || importedPlan" type="button" :disabled="disabled" @click="clear">清除计划关联</button></div>
      </template>
      <p v-if="notice" role="status">{{ notice }}</p>
      <p v-if="history.length > 1">关联历史 · {{ history.length }} 次</p>
      <button v-if="selection" type="button" :disabled="loading || saving" @click="readTrace">读取核验与报告关联</button>
      <p v-if="trace && !trace.length">尚未创建绑定该计划的正式输入。</p>
      <article v-for="run in trace" :key="`${run.snapshot_id}/${run.run_id}`" class="plan-binding-trace">
        <p>开发提交 <code>{{ run.target_sha.slice(0, 12) }}</code> · {{ run.run_status ?? '尚未启动核验' }}</p>
        <ul><li v-for="result in run.results" :key="result.claim_key">{{ result.claim_key }}：{{ result.status ?? '尚无结论' }}</li></ul>
        <p v-for="report in run.reports" :key="report.id">报告 #{{ report.sequence_no }} · {{ report.status }}<span v-if="report.record_no"> · 归档 {{ report.record_no }}</span></p>
      </article>
    </div>
  </details>
</template>

<style scoped>
.plan-acceptance-binding { margin: 12px 0; padding: 14px 18px; }
summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; cursor: pointer; }
summary small, .plan-binding-criterion small { color: var(--muted); }
.plan-binding-content { display: grid; gap: 12px; margin-top: 14px; }
.plan-binding-content p { margin: 0; overflow-wrap: anywhere; }
.plan-binding-content label { display: grid; gap: 6px; }
.plan-binding-content select { width: 100%; padding: 8px; }
.plan-binding-content .plan-binding-criterion { grid-template-columns: auto 1fr; align-items: start; gap: 10px; }
.plan-binding-criterion span { display: grid; gap: 4px; }
.plan-binding-criterion input { margin-top: 4px; }
.plan-binding-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.plan-binding-trace { border-top: 1px solid var(--border, var(--line)); padding-top: 12px; }
.plan-binding-content ul { margin: 0; padding-left: 20px; }
code { overflow-wrap: anywhere; }
</style>
