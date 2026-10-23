<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { selectedProject, selectedProjectId } from '../features/projects/project-context'
import PlanEditor from '../features/planning/PlanEditor.vue'
import PlanTree from '../features/planning/PlanTree.vue'
import { usePlanning } from '../features/planning/use-planning'
import type { AgentEvent, PlanVersion } from '../features/planning/types'

const { ideas, repositories, snapshots, permissions, detail, selectedIdeaId, selectedPlanId, repositoryId, snapshotId, gitRef,
  editor, newVersionMode, events, answers, diff, diffFrom, loading, detailLoading, busy, error, notice, currentPlan, dirty, active,
  pendingQuestions, readonly, choosePlan, chooseIdea, loadProject, loadDetail, capture, saveIdea, start, sendAnswers, savePlan, confirm, compare, cancel, discard } = usePlanning()
const showIdeaForm = ref(false), editingIdea = ref(false), ideaForm = ref({ title: '', content: '' })
const editingPlan = ref(false)
function previewPlan() { editingPlan.value = !editingPlan.value }
async function saveEditedPlan() {
  await savePlan()
  if (!dirty.value && !newVersionMode.value) editingPlan.value = false
}
function openIdea(revise = false) {
  editingIdea.value = revise
  ideaForm.value = revise && detail.value ? { title: detail.value.idea.title, content: detail.value.revision.content } : { title: '', content: '' }
  showIdeaForm.value = true
}
async function submitIdea() {
  if (await saveIdea(ideaForm.value.title.trim(), ideaForm.value.content.trim(), editingIdea.value)) showIdeaForm.value = false
}
function versionLabel(plan: PlanVersion) { return `需求 r${plan.idea_revision_no} · 计划 v${plan.sequence_no}` }
function status(value: string) { return ({ QUEUED: '等待执行', RUNNING: '正在分析', SUCCEEDED: '本轮分析结束', FAILED: '执行失败', CANCELLED: '已取消', DRAFT: '待确认草案', CONFIRMED: '已确认基线', SUPERSEDED: '历史基线' } as Record<string, string>)[value] ?? value }
function time(value: string | null) { return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)) : '—' }
function eventLabel(event: AgentEvent) {
  if (event.eventType === 'AGENT_DELEGATED') return `委派 ${event.payloadRedacted.agentKey ?? '专业 Agent'}`
  const tool = ({ read_snapshot: '读取冻结输入', search_snapshot: '搜索仓库', read_file: '读取代码' } as Record<string, string>)[event.payloadRedacted.name ?? ''] ?? event.payloadRedacted.name ?? '工具'
  return ({ AGENT_STARTED: '开始分析', MODEL_TURN_COMPLETED: '模型分析返回', TOOL_STARTED: `${tool}：开始`, TOOL_COMPLETED: `${tool}：${event.payloadRedacted.ok ? '已返回' : '失败'}`, AGENT_COMPLETED: 'Agent 分析结束' } as Record<string, string>)[event.eventType] ?? event.eventType
}
watch(selectedProjectId, () => { showIdeaForm.value = false; ideaForm.value = { title: '', content: '' } })
watch(selectedPlanId, () => { editingPlan.value = false })
</script>

<template>
  <section class="page planning-page" :aria-busy="loading || Boolean(busy)">
    <header class="page-heading"><div><h1>需求规划</h1></div><button v-if="permissions?.canPlan" type="button" :disabled="Boolean(busy) || dirty || newVersionMode" @click="openIdea()">新建需求</button></header>
    <p v-if="error" role="alert" class="planning-error">{{ error }} <button type="button" class="text-button" :disabled="Boolean(busy) || dirty" @click="detail ? loadDetail() : loadProject()">重新读取</button></p>
    <p v-if="notice" role="status" class="planning-notice">{{ notice }}</p>
    <p v-if="loading" role="status">正在加载…</p>
    <template v-else-if="selectedProject && permissions">
      <details v-if="!currentPlan" class="planning-source ui-disclosure" :open="!snapshots.length">
        <summary>仓库版本</summary>

        <p v-if="!repositories.length">尚未接入仓库。前往 <RouterLink to="/settings">集成与设置</RouterLink></p>
        <form v-else-if="permissions.canPlan" class="planning-source-form" @submit.prevent="capture">
          <label>已登记仓库<select v-model="repositoryId" required :disabled="Boolean(busy)"><option v-for="repository in repositories" :key="repository.id" :value="repository.id">{{ repository.display_url }}</option></select></label>
          <label>分支、标签或提交 SHA<input v-model="gitRef" required maxlength="255" :disabled="Boolean(busy)" autocomplete="off" /></label>
          <button type="submit" :disabled="Boolean(busy) || !gitRef.trim()">{{ busy === 'capture' ? '正在冻结仓库…' : '冻结仓库版本' }}</button>
        </form>
        <label class="planning-snapshot-picker">本次规划使用的冻结版本<select v-model="snapshotId" :disabled="Boolean(busy) || !snapshots.length"><option value="">选择已冻结版本</option><option v-for="snapshot in snapshots" :key="snapshot.id" :value="snapshot.id">{{ repositories.find(repository => repository.id === snapshot.repository_id)?.display_url }} · {{ snapshot.target_sha.slice(0, 12) }} · {{ time(snapshot.created_at) }}</option></select></label>
      </details>

      <form v-if="showIdeaForm" class="planning-idea-form surface" @submit.prevent="submitIdea">
        <h2>{{ editingIdea ? '保存需求新修订' : '登记实际开发需求' }}</h2>
        <label>需求标题<input v-model="ideaForm.title" required maxlength="300" /></label>
        <label>想完成什么、已有约束和仍不确定的事项<textarea v-model="ideaForm.content" required maxlength="40000" rows="6" /></label>
        <div class="action-row"><button type="submit" :disabled="Boolean(busy)">{{ busy === 'idea' ? '正在保存…' : '保存需求' }}</button><button type="button" class="secondary" :disabled="Boolean(busy)" @click="showIdeaForm = false">收起</button></div>
      </form>

      <div class="planning-board">
        <aside class="planning-sidebar" aria-label="项目需求列表">
          <p v-if="!ideas.length" class="planning-caption">暂无需求。</p>
          <label v-else class="planning-idea-picker">项目需求<select :value="selectedIdeaId" :disabled="Boolean(busy) || dirty || newVersionMode" @change="chooseIdea(($event.target as HTMLSelectElement).value)"><option v-for="idea in ideas" :key="idea.id" :value="idea.id">{{ idea.title }}</option></select></label>
        </aside>
        <div class="planning-detail">
          <p v-if="detailLoading" role="status">正在读取需求详情…</p>
          <template v-if="detail">
            <section class="planning-support" :class="{ 'is-active': active || !currentPlan }" aria-label="需求与规划设置">
            <details class="planning-original ui-disclosure" :open="!currentPlan"><summary><span>原始需求</span><span class="disclosure-meta">r{{ detail.revision.revision_no }}</span></summary><p class="planning-idea-content">{{ detail.revision.content }}</p><button v-if="permissions.canPlan" type="button" class="secondary" :disabled="Boolean(busy) || active || dirty || newVersionMode" @click="openIdea(true)">修改需求</button></details>
            <details class="planning-run-settings ui-disclosure" :open="active || !currentPlan"><summary>{{ active ? '正在分析，查看执行状态' : '重新规划与仓库版本' }}</summary>
              <div v-if="currentPlan" class="planning-source planning-source-inline">
                <p class="planning-caption">当前计划依据的代码版本 <code>{{ currentPlan.target_sha }}</code></p>
                <form v-if="permissions.canPlan" class="planning-source-form" @submit.prevent="capture"><label>已登记仓库<select v-model="repositoryId" required :disabled="Boolean(busy)"><option v-for="repository in repositories" :key="repository.id" :value="repository.id">{{ repository.display_url }}</option></select></label><label>分支、标签或提交 SHA<input v-model="gitRef" required maxlength="255" :disabled="Boolean(busy)" autocomplete="off" /></label><button type="submit" :disabled="Boolean(busy) || !gitRef.trim()">{{ busy === 'capture' ? '正在冻结仓库…' : '冻结仓库版本' }}</button></form>
                <label class="planning-snapshot-picker">下次分析使用的版本<select v-model="snapshotId" :disabled="Boolean(busy) || !snapshots.length"><option value="">选择已冻结版本</option><option v-for="snapshot in snapshots" :key="snapshot.id" :value="snapshot.id">{{ repositories.find(repository => repository.id === snapshot.repository_id)?.display_url }} · {{ snapshot.target_sha.slice(0, 12) }} · {{ time(snapshot.created_at) }}</option></select></label>
              </div>
              <div class="planning-run-controls"><div><span v-if="detail.agentTask" class="status-mark">{{ status(detail.agentTask.status) }}</span><p v-if="detail.agentTask?.last_error_code" class="planning-error">执行错误：{{ detail.agentTask.last_error_code }}。请检查服务配置或输入后重新发起。</p></div><div class="action-row"><button v-if="permissions.canPlan && !active" type="button" :disabled="Boolean(busy) || !snapshotId || dirty || newVersionMode" @click="start">{{ busy === 'run' ? '正在创建任务…' : '分析并生成计划' }}</button><button v-if="permissions.canPlan && active" type="button" class="secondary" :disabled="Boolean(busy)" @click="cancel">取消本轮分析</button><button type="button" class="text-button" :disabled="Boolean(busy)" @click="loadDetail()">刷新状态</button></div></div>
            </details>
            </section>
            <form v-if="pendingQuestions.length" class="planning-questions" @submit.prevent="sendAnswers"><h3>需要你补充的信息</h3><label v-for="question in pendingQuestions" :key="question.id">{{ question.question }}<small>{{ question.reason }}</small><textarea v-model="answers[question.id]" required maxlength="12000" rows="3" :disabled="!permissions.canPlan || Boolean(busy)" /></label><button v-if="permissions.canPlan" type="submit" :disabled="Boolean(busy)">{{ busy === 'answers' ? '正在保存回答…' : '保存回答并继续规划' }}</button></form>
            <details v-if="detail.questions.some(question => question.answer !== null)" class="planning-history ui-disclosure"><summary>已保存的澄清回答</summary><dl><template v-for="question in detail.questions.filter(item => item.answer !== null)" :key="question.id"><dt>{{ question.question }}</dt><dd>{{ question.answer }}</dd></template></dl></details>

            <section v-if="currentPlan && editor" class="planning-plan" aria-label="计划版本与内容">
              <div class="planning-section-heading planning-tree-toolbar"><h3>Issue 关系树</h3><div class="action-row"><select :value="selectedPlanId" aria-label="选择计划版本" :disabled="Boolean(busy) || dirty || newVersionMode" @change="choosePlan(($event.target as HTMLSelectElement).value)"><option v-for="plan in detail.plans" :key="plan.id" :value="plan.id">{{ versionLabel(plan) }} · {{ status(plan.status) }}</option></select><button v-if="!readonly" type="button" class="secondary" :disabled="Boolean(busy)" @click="previewPlan">{{ editingPlan ? '预览关系树' : '编辑计划' }}</button></div></div>
              <p v-if="dirty || newVersionMode" role="status" class="planning-caption">{{ newVersionMode ? '正在编辑新版本。' : '存在尚未保存的本地修改。' }} <button type="button" class="text-button" :disabled="Boolean(busy)" @click="discard">放弃本地修改</button></p>
              <PlanTree v-if="!editingPlan" :key="currentPlan.id" :plan="editor" :title="detail.idea.title" :status="newVersionMode ? '新版本草稿' : status(currentPlan.status)" />
              <form v-else @submit.prevent="saveEditedPlan"><PlanEditor v-model="editor" :readonly="readonly || Boolean(busy)" :target-sha="currentPlan.target_sha" /><div class="action-row"><button v-if="!readonly" type="submit" :disabled="Boolean(busy)">{{ busy === 'plan' ? '正在保存…' : newVersionMode ? '保存为新版本' : '保存草案修改' }}</button></div></form>
              <div class="action-row planning-plan-actions"><button v-if="permissions.canPlan && currentPlan.status !== 'DRAFT' && !newVersionMode" type="button" class="secondary" :disabled="Boolean(busy)" @click="newVersionMode = true; editingPlan = true">创建修改版本</button><button v-if="permissions.canConfirm && currentPlan.status === 'DRAFT'" type="button" :disabled="Boolean(busy) || dirty || newVersionMode" @click="confirm">确认此计划版本</button><span v-if="currentPlan.confirmed_at" class="planning-caption">确认于 {{ time(currentPlan.confirmed_at) }}</span></div>

              <details v-if="detail.plans.length > 1" class="planning-history ui-disclosure"><summary>比较变更与下游影响</summary><div class="planning-compare"><label>比较基线<select v-model="diffFrom"><option value="">选择其他版本</option><option v-for="plan in detail.plans.filter(item => item.id !== currentPlan?.id)" :key="plan.id" :value="plan.id">{{ versionLabel(plan) }} · {{ status(plan.status) }}</option></select></label><button type="button" class="secondary" :disabled="!diffFrom || Boolean(busy)" @click="compare">与当前版本比较</button></div><dl v-if="diff" class="planning-diff"><div><dt>新增工作项</dt><dd>{{ diff.addedIssueKeys.join('、') || '无' }}</dd></div><div><dt>移除工作项</dt><dd>{{ diff.removedIssueKeys.join('、') || '无' }}</dd></div><div><dt>内容变化</dt><dd>{{ diff.changedIssueKeys.join('、') || '无' }}</dd></div><div><dt>受影响工作项</dt><dd>{{ diff.affectedIssueKeys.join('、') || '无' }}</dd></div><div><dt>依赖变化</dt><dd>{{ diff.dependenciesChanged ? '有变化，请核对产物与可用条件' : '没有变化' }}</dd></div></dl></details>
            </section>
            <p v-else-if="!active && !pendingQuestions.length" class="planning-caption">暂无计划，请先生成草案。</p>
            <details v-if="events.length" class="planning-history ui-disclosure"><summary>执行记录</summary><p class="planning-caption"></p><ol class="planning-events"><li v-for="event in events" :key="`${event.agentInstanceId}-${event.eventSeq}`"><time>{{ time(event.occurredAt) }}</time><span>{{ eventLabel(event) }}</span><small v-if="event.parentAgentInstanceId">子 Agent · {{ event.agentInstanceId.slice(0, 8) }}</small></li></ol></details>
          </template>
          <p v-else-if="!detailLoading" class="planning-caption">从左侧选择需求，或新建实际开发需求。</p>
        </div>
      </div>
    </template>
  </section>
</template>

<style src="../features/planning/planning.css"></style>
