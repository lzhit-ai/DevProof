import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { apiRequest, projectHeaders, selectedProjectId } from '../projects/project-context'
import type { AgentEvent, Idea, PlanBody, PlanDiff, PlanningDetail, PlanningPermissions, PlanVersion, RepositoryOption, RepositorySnapshot } from './types'

export function usePlanning() {
  const ideas = ref<Idea[]>([]), repositories = ref<RepositoryOption[]>([]), snapshots = ref<RepositorySnapshot[]>([])
  const permissions = ref<PlanningPermissions | null>(null), detail = ref<PlanningDetail | null>(null)
  const selectedIdeaId = ref(''), selectedPlanId = ref(''), repositoryId = ref(''), snapshotId = ref(''), gitRef = ref('')
  const editor = ref<PlanBody | null>(null), baseVersion = ref(0), baseText = ref(''), newVersionMode = ref(false)
  const events = ref<AgentEvent[]>([]), answers = ref<Record<string, string>>({}), diff = ref<PlanDiff | null>(null), diffFrom = ref('')
  const loading = ref(false), detailLoading = ref(false), busy = ref(''), error = ref(''), notice = ref('')
  const currentPlan = computed(() => detail.value?.plans.find(plan => plan.id === selectedPlanId.value) ?? null)
  const dirty = computed(() => editor.value !== null && JSON.stringify(editor.value) !== baseText.value)
  const active = computed(() => ['QUEUED', 'RUNNING'].includes(detail.value?.agentTask?.status ?? ''))
  const pendingQuestions = computed(() => detail.value?.questions.filter(question => question.planning_run_id === detail.value?.latestRun?.id && question.answer === null) ?? [])
  const readonly = computed(() => !permissions.value?.canPlan || (currentPlan.value?.status !== 'DRAFT' && !newVersionMode.value))
  let generation = 0, detailGeneration = 0, timer: ReturnType<typeof setTimeout> | undefined, disposed = false
  const path = (projectId: string) => `/projects/${projectId}`
  const same = (projectId: string, ideaId = selectedIdeaId.value) => !disposed && projectId === selectedProjectId.value && ideaId === selectedIdeaId.value
  const message = (cause: unknown) => cause instanceof Error ? cause.message : '请求失败，请稍后重试'
  function resetEditor(plan: PlanVersion | null) {
    editor.value = plan ? JSON.parse(JSON.stringify(plan.body)) as PlanBody : null
    baseText.value = JSON.stringify(editor.value); baseVersion.value = plan?.version ?? 0; newVersionMode.value = false
  }
  function choosePlan(id: string) {
    if (dirty.value || newVersionMode.value) return
    selectedPlanId.value = id; diff.value = null; resetEditor(currentPlan.value)
    diffFrom.value = currentPlan.value?.parent_plan_id ?? ''
  }
  function schedulePoll() {
    clearTimeout(timer)
    if (active.value && !disposed) timer = setTimeout(() => { void loadDetail(true) }, 2000)
  }
  async function loadDetail(silent = false, force = false) {
    const projectId = selectedProjectId.value, ideaId = selectedIdeaId.value, request = ++detailGeneration
    if (!projectId || !ideaId) return
    if (!silent) detailLoading.value = true
    try {
      const loaded = await apiRequest<PlanningDetail>(`${path(projectId)}/ideas/${ideaId}`, { headers: projectHeaders() })
      if (!same(projectId, ideaId) || request !== detailGeneration) return
      const wasDirty = dirty.value || newVersionMode.value
      detail.value = loaded
      const selected = loaded.plans.find(plan => plan.id === selectedPlanId.value) ?? loaded.plans[0] ?? null
      const changed = selected?.id !== selectedPlanId.value
      selectedPlanId.value = selected?.id ?? ''
      if (force || changed || !wasDirty) resetEditor(selected)
      if (!diffFrom.value) diffFrom.value = selected?.parent_plan_id ?? ''
      if (loaded.agentTask) {
        const log = await apiRequest<AgentEvent[]>(`/agent-tasks/${loaded.agentTask.id}/events`, { headers: projectHeaders() })
        if (same(projectId, ideaId) && request === detailGeneration) events.value = log
      } else events.value = []
    } catch (cause) {
      if (same(projectId, ideaId) && request === detailGeneration) error.value = message(cause)
    } finally {
      if (same(projectId, ideaId) && request === detailGeneration) { detailLoading.value = false; schedulePoll() }
    }
  }
  async function chooseIdea(id: string) {
    if (dirty.value || newVersionMode.value || busy.value) return
    clearTimeout(timer); selectedIdeaId.value = id; selectedPlanId.value = ''; diffFrom.value = ''
    detail.value = null; events.value = []; answers.value = {}; diff.value = null; resetEditor(null)
    await loadDetail()
  }
  async function loadProject() {
    const projectId = selectedProjectId.value, request = ++generation
    ++detailGeneration; clearTimeout(timer)
    ideas.value = []; repositories.value = []; snapshots.value = []; permissions.value = null
    detail.value = null; selectedIdeaId.value = ''; selectedPlanId.value = ''; snapshotId.value = ''; repositoryId.value = ''; gitRef.value = ''
    events.value = []; diff.value = null; diffFrom.value = ''; answers.value = {}; resetEditor(null)
    error.value = ''; notice.value = ''; busy.value = ''; loading.value = Boolean(projectId)
    if (!projectId) return
    try {
      const [ideaList, repositoryList, snapshotList, grants] = await Promise.all([
        apiRequest<Idea[]>(`${path(projectId)}/ideas`, { headers: projectHeaders() }),
        apiRequest<RepositoryOption[]>(`${path(projectId)}/planning-repositories`, { headers: projectHeaders() }),
        apiRequest<RepositorySnapshot[]>(`${path(projectId)}/repository-snapshots`, { headers: projectHeaders() }),
        apiRequest<PlanningPermissions>(`${path(projectId)}/planning-permissions`, { headers: projectHeaders() }),
      ])
      if (disposed || request !== generation || projectId !== selectedProjectId.value) return
      ideas.value = ideaList; repositories.value = repositoryList; snapshots.value = snapshotList; permissions.value = grants
      repositoryId.value = repositoryList[0]?.id ?? ''; snapshotId.value = snapshotList[0]?.id ?? ''
      if (ideaList.length) await chooseIdea(ideaList[0]!.id)
    } catch (cause) { if (request === generation && projectId === selectedProjectId.value) error.value = message(cause) }
    finally { if (request === generation) loading.value = false }
  }
  async function action(name: string, execute: (projectId: string) => Promise<void>) {
    const projectId = selectedProjectId.value
    if (!projectId || busy.value) return
    busy.value = name; error.value = ''; notice.value = ''
    try { await execute(projectId) }
    catch (cause) { if (same(projectId)) error.value = message(cause) }
    finally { if (same(projectId)) busy.value = '' }
  }
  async function capture() {
    await action('capture', async projectId => {
      const captured = await apiRequest<{ id: string }>(`${path(projectId)}/repository-snapshots`, { method: 'POST', headers: projectHeaders(true), body: JSON.stringify({ repositoryId: repositoryId.value, ref: gitRef.value.trim() }) })
      const list = await apiRequest<RepositorySnapshot[]>(`${path(projectId)}/repository-snapshots`, { headers: projectHeaders() })
      if (same(projectId)) { snapshots.value = list; snapshotId.value = captured.id; notice.value = '仓库版本已冻结，可用于本次规划。' }
    })
  }
  async function saveIdea(title: string, content: string, revise: boolean): Promise<boolean> {
    let saved = false
    await action('idea', async projectId => {
      const existing = detail.value
      const loaded = await apiRequest<PlanningDetail>(`${path(projectId)}/ideas${revise && existing ? `/${existing.idea.id}` : ''}`, {
        method: revise ? 'PUT' : 'POST', headers: projectHeaders(true),
        body: JSON.stringify({ title, content, ...(revise && existing ? { expectedVersion: existing.idea.version } : {}) }),
      })
      const list = await apiRequest<Idea[]>(`${path(projectId)}/ideas`, { headers: projectHeaders() })
      if (same(projectId)) {
        ideas.value = list; selectedIdeaId.value = loaded.idea.id; selectedPlanId.value = ''; detail.value = loaded
        resetEditor(loaded.plans[0] ?? null); selectedPlanId.value = loaded.plans[0]?.id ?? ''; events.value = []; diffFrom.value = ''; diff.value = null; answers.value = {}; saved = true
        notice.value = revise ? '需求已保存为新修订，原计划与核验基线保留。' : '需求已保存，选择仓库版本后即可开始分析。'
      }
    })
    return saved
  }
  async function start() {
    if (!detail.value || !snapshotId.value) return
    await action('run', async projectId => {
      await apiRequest(`${path(projectId)}/ideas/${selectedIdeaId.value}/planning-runs`, { method: 'POST', headers: projectHeaders(true),
        body: JSON.stringify({ repositorySnapshotId: snapshotId.value, expectedIdeaVersion: detail.value!.idea.version }) })
      if (same(projectId)) { notice.value = '规划任务已排队，执行状态将根据真实事件更新。'; await loadDetail(true) }
    })
  }
  async function sendAnswers() {
    if (pendingQuestions.value.some(question => !answers.value[question.id]?.trim())) { error.value = '请回答当前全部澄清问题后再继续。'; return }
    const submitted = pendingQuestions.value.map(question => ({ questionId: question.id, answer: answers.value[question.id]!.trim() }))
    await action('answers', async projectId => {
      await apiRequest(`${path(projectId)}/ideas/${selectedIdeaId.value}/answers`, { method: 'POST', headers: projectHeaders(true), body: JSON.stringify({ answers: submitted }) })
      if (same(projectId)) { answers.value = {}; notice.value = '回答已保存，正在继续规划。'; await loadDetail(true) }
    })
  }
  async function savePlan() {
    const plan = currentPlan.value
    if (!plan || !editor.value) return
    await action('plan', async projectId => {
      const saved = await apiRequest<PlanVersion>(`${path(projectId)}/plans/${plan.id}${newVersionMode.value ? '/revisions' : ''}`, {
        method: newVersionMode.value ? 'POST' : 'PUT', headers: projectHeaders(true), body: JSON.stringify({ expectedVersion: baseVersion.value, body: editor.value }),
      })
      if (same(projectId)) { selectedPlanId.value = saved.id; notice.value = '计划草案已保存，尚待有权人员确认。'; await loadDetail(true, true) }
    })
  }
  async function confirm() {
    const plan = currentPlan.value
    if (!plan || dirty.value || newVersionMode.value) return
    await action('confirm', async projectId => {
      await apiRequest(`${path(projectId)}/plans/${plan.id}/confirm`, { method: 'POST', headers: projectHeaders(true), body: JSON.stringify({ expectedVersion: baseVersion.value, contentHash: plan.content_hash }) })
      if (same(projectId)) { notice.value = '该版本已确认为计划基线，后续修改将创建新版本。'; await loadDetail(true, true) }
    })
  }
  async function compare() {
    if (!currentPlan.value || !diffFrom.value) return
    await action('compare', async projectId => {
      const compared = await apiRequest<PlanDiff>(`${path(projectId)}/ideas/${selectedIdeaId.value}/plan-diff?from=${encodeURIComponent(diffFrom.value)}&to=${encodeURIComponent(selectedPlanId.value)}`, { headers: projectHeaders() })
      if (same(projectId)) diff.value = compared
    })
  }
  async function cancel() {
    if (!detail.value?.agentTask) return
    const taskId = detail.value.agentTask.id
    await action('cancel', async projectId => {
      await apiRequest(`/agent-tasks/${taskId}/cancel`, { method: 'POST', headers: projectHeaders(true) })
      if (same(projectId)) { notice.value = '已请求取消，本次结果不能继续推进计划状态。'; await loadDetail(true) }
    })
  }
  watch(selectedProjectId, () => { void loadProject() }, { immediate: true })
  onBeforeUnmount(() => { disposed = true; generation++; detailGeneration++; clearTimeout(timer) })
  return { ideas, repositories, snapshots, permissions, detail, selectedIdeaId, selectedPlanId, repositoryId, snapshotId, gitRef,
    editor, newVersionMode, events, answers, diff, diffFrom, loading, detailLoading, busy, error, notice, currentPlan, dirty, active,
    pendingQuestions, readonly, choosePlan, chooseIdea, loadProject, loadDetail, capture, saveIdea, start, sendAnswers, savePlan, confirm, compare, cancel,
    discard: () => resetEditor(currentPlan.value) }
}
