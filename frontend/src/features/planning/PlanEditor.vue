<script setup lang="ts">
import { ref } from 'vue'
import type { PlanBody } from './types'

const draft = defineModel<PlanBody>({ required: true })
const props = defineProps<{ readonly: boolean; targetSha: string }>()
const key = (prefix: string) => `${prefix}-${crypto.randomUUID().slice(0, 8)}`
const addedIssueKey = ref('')
function lines(event: Event): string[] { return (event.target as HTMLTextAreaElement).value.split('\n').map(value => value.trim()).filter(Boolean) }
function addIssue() {
  addedIssueKey.value = key('ISS')
  draft.value.issues.push({ key: addedIssueKey.value, title: '', goal: '', scope: '', acceptanceCriteria: [], reuseRefs: [], deliverables: [], assumptions: [] })
}
</script>

<template>
  <fieldset class="plan-editor" :disabled="props.readonly">
    <legend class="sr-only">计划内容</legend>
    <label>计划摘要<textarea v-model="draft.summary" required maxlength="12000" rows="3" /></label>
    <div class="planning-section-heading"><h3>工作项与验收</h3><button v-if="!readonly" type="button" class="secondary" @click="addIssue">添加工作项</button></div>
    <details v-for="(issue, issueIndex) in draft.issues" :key="issueIndex" class="plan-issue ui-disclosure" :open="issue.key === addedIssueKey">
      <summary>{{ issue.key }} · {{ issue.title || '待填写标题' }}</summary>
      <label>标题<input v-model="issue.title" required maxlength="300" /></label>
      <label>目标与价值<textarea v-model="issue.goal" required maxlength="8000" rows="2" /></label>
      <label>范围与边界<textarea v-model="issue.scope" required maxlength="12000" rows="2" /></label>
      <fieldset v-for="(criterion, criterionIndex) in issue.acceptanceCriteria" :key="criterionIndex" class="plan-subsection">
        <legend>验收条件 {{ criterionIndex + 1 }}</legend>
        <label>可观察的完成条件<textarea v-model="criterion.condition" required maxlength="6000" rows="2" /></label>
        <label>检查方式<textarea v-model="criterion.verificationMethod" required maxlength="6000" rows="2" /></label>
        <label>所需证据，每行一项<textarea :value="criterion.requiredEvidence.join('\n')" required rows="2" @change="criterion.requiredEvidence = lines($event)" /></label>
        <button v-if="!readonly" type="button" class="text-button danger" @click="issue.acceptanceCriteria.splice(criterionIndex, 1)">移除此验收项</button>
      </fieldset>
      <button v-if="!readonly" type="button" class="secondary" @click="issue.acceptanceCriteria.push({ key: key('AC'), condition: '', verificationMethod: '', requiredEvidence: [] })">添加验收条件</button>
      <fieldset v-for="(artifact, artifactIndex) in issue.deliverables" :key="artifactIndex" class="plan-subsection">
        <legend>交付内容 {{ artifactIndex + 1 }}</legend>
        <label>类型<select v-model="artifact.kind"><option value="API">接口</option><option value="DATA">数据</option><option value="COMPONENT">组件</option><option value="DOCUMENT">文档</option><option value="OTHER">其他</option></select></label>
        <label>约定内容<textarea v-model="artifact.description" required maxlength="6000" rows="2" /></label>
        <label>约定版本<input v-model="artifact.version" required maxlength="100" /></label>
        <label>何时可供依赖方使用<textarea v-model="artifact.availabilityCondition" required maxlength="6000" rows="2" /></label>
        <button v-if="!readonly" type="button" class="text-button danger" @click="issue.deliverables.splice(artifactIndex, 1)">移除此产物</button>
      </fieldset>
      <button v-if="!readonly" type="button" class="secondary" @click="issue.deliverables.push({ key: key('OUT'), kind: 'OTHER', description: '', version: '', availabilityCondition: '' })">添加交付内容</button>
      <details class="plan-references ui-disclosure"><summary>仓库复用依据 · {{ issue.reuseRefs.length }} 项</summary>
        <fieldset v-for="(reference, referenceIndex) in issue.reuseRefs" :key="referenceIndex" class="plan-subsection">
          <legend>代码引用 {{ referenceIndex + 1 }}</legend>
          <label>文件路径<input v-model="reference.path" required /></label>
          <div class="planning-fields two-fields"><label>起始行<input v-model.number="reference.startLine" type="number" min="1" required /></label><label>结束行<input v-model.number="reference.endLine" type="number" :min="reference.startLine" required /></label></div>
          <label>复用理由<textarea v-model="reference.reason" required rows="2" /></label>
          <p class="planning-caption">代码版本 <code>{{ reference.targetSha }}</code></p>
          <button v-if="!readonly" type="button" class="text-button danger" @click="issue.reuseRefs.splice(referenceIndex, 1)">移除此依据</button>
        </fieldset>
        <button v-if="!readonly" type="button" class="secondary" @click="issue.reuseRefs.push({ path: '', targetSha: targetSha, startLine: 1, endLine: 1, reason: '' })">添加代码依据</button>
      </details>
      <label>待核对假设，每行一项<textarea :value="issue.assumptions.join('\n')" rows="2" @change="issue.assumptions = lines($event)" /></label>
      <button v-if="!readonly" type="button" class="text-button danger" @click="draft.issues.splice(issueIndex, 1)">移除此工作项</button>
    </details>
    <div class="planning-section-heading"><h3>产物依赖</h3><button v-if="!readonly" type="button" class="secondary" @click="draft.dependencies.push({ consumer: '', provider: '', deliverable: '', condition: '', reason: '' })">添加依赖</button></div>
    <p v-if="!draft.dependencies.length" class="planning-caption">当前计划没有声明工作项之间的产物依赖。</p>
    <fieldset v-for="(dependency, index) in draft.dependencies" :key="index" class="plan-subsection">
      <legend>依赖 {{ index + 1 }}</legend>
      <div class="planning-fields two-fields"><label>使用方<select v-model="dependency.consumer" required><option value="">选择工作项</option><option v-for="issue in draft.issues" :key="issue.key" :value="issue.key">{{ issue.key }} · {{ issue.title }}</option></select></label><label>提供方<select v-model="dependency.provider" required @change="dependency.deliverable = ''"><option value="">选择工作项</option><option v-for="issue in draft.issues" :key="issue.key" :value="issue.key">{{ issue.key }} · {{ issue.title }}</option></select></label></div>
      <label>依赖产物<select v-model="dependency.deliverable" required><option value="">选择提供方的产物</option><option v-for="artifact in draft.issues.find(issue => issue.key === dependency.provider)?.deliverables ?? []" :key="artifact.key" :value="artifact.key">{{ artifact.key }} · {{ artifact.description }}</option></select></label>
      <label>成立条件<textarea v-model="dependency.condition" required rows="2" /></label>
      <label>依赖理由<textarea v-model="dependency.reason" required rows="2" /></label>
      <button v-if="!readonly" type="button" class="text-button danger" @click="draft.dependencies.splice(index, 1)">移除此依赖</button>
    </fieldset>
    <label>计划风险，每行一项<textarea :value="draft.risks.join('\n')" rows="3" @change="draft.risks = lines($event)" /></label>
  </fieldset>
</template>
