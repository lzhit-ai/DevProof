<script setup lang="ts">
import { computed } from 'vue'
import type { EvidenceReference } from '../../types/workbench'

type GitFile = { path: string; old_path?: string | null; edit_type: string; additions: number; deletions: number; binary: boolean; hunks: Array<{ header: string; payload: string }> }
type GitDiff = { files: GitFile[]; coverage: Record<string, unknown> }
type Challenge = { state: string; verdict: string | null; reason: string | null; evidenceIds: string[] }
type CodeReview = { findings: Array<{ id: string; evidenceId: string; severity: string; findingKind: string; title: string; problem: string; triggerScenario: string; recommendation: string; confidence: number; challenge: Challenge }>; coverage: Array<{ scopeKind: string; state: string; reasonCode: string | null; details: Record<string, unknown> }> }

const props = defineProps<{ evidence: EvidenceReference[]; snapshotLabel?: string | null; live?: boolean; runStatus?: string | null; gitDiff?: GitDiff | null; codeReview?: CodeReview | null; selectedFilePath?: string | null }>()
const emit = defineEmits<{ selectFile: [path: string]; showRunLog: [] }>()

const reviewSummary = computed(() => {
  const coverage = props.codeReview?.coverage.find(item => item.scopeKind === 'CODE_REVIEW')
  const count = props.codeReview?.findings.length ?? 0
  if (!coverage) return ['QUEUED', 'RUNNING'].includes(props.runStatus ?? '')
    ? { label: '检查中', message: '检查结果尚未生成。', incomplete: false }
    : { label: '未完成', message: '本轮未生成有效的代码检查结果。', incomplete: true }
  if (coverage.state === 'ANALYZED' && !coverage.reasonCode)
    return { label: count ? `${count} 项发现` : '未发现问题', message: count ? '' : '本轮已检查范围内未发现代码问题。', incomplete: false }
  if (coverage.state === 'PARTIAL')
    return { label: '部分完成', message: `${count ? `已生成 ${count} 项发现。` : ''}${reasonLabel(coverage.reasonCode) || '本轮仅完成部分代码检查。'}`, incomplete: true }
  if (coverage.state === 'SKIPPED' || coverage.state === 'NOT_APPLICABLE')
    return { label: '未执行', message: reasonLabel(coverage.reasonCode) || '本轮未执行代码检查。', incomplete: false }
  return { label: '未完成', message: reasonLabel(coverage.reasonCode) || '代码检查未能完成，请查看运行记录。', incomplete: true }
})

function reasonLabel(code: string | null) {
  if (!code) return ''
  const labels: Record<string, string> = {
    MODEL_UNAVAILABLE: '模型分析不可用，代码检查未能完成。',
    MODEL_NOT_CONFIGURED: '尚未配置分析模型。',
    MODEL_FINDING_INVALID: '部分模型结果未通过校验，已排除。',
    NO_CODE_REVIEW_FINDINGS: '没有生成需要复核的问题，本步骤无需执行。',
    NO_CITABLE_CODE_EVIDENCE: '缺少可引用的代码片段。',
    NO_TEXT_HUNKS: '本次变更没有可分析的文本片段。',
    DISABLED_BY_TEMPLATE: '本轮配置未启用此步骤。',
    NO_SUPPLEMENT_CONTEXT: '未找到可补充的代码上下文。',
    GIT_ARTIFACT_MISSING: '本轮代码材料缺失。',
    GIT_ARTIFACT_UNAVAILABLE: '本轮代码材料暂时无法读取。',
    GIT_ARTIFACT_HASH_MISMATCH: '代码材料校验失败。',
  }
  if (labels[code]) return labels[code]
  if (code.includes('BUDGET')) return '分析额度已用尽，部分内容尚未检查。'
  if (code.startsWith('MODEL_')) return '模型分析未能完成，具体原因请查看运行记录。'
  return '本步骤未能完整执行，具体原因请查看运行记录。'
}

function scopeLabel(scope: string) {
  return ({ GIT_CAPTURE: '代码读取', STANDARD_VERIFICATION: '综合检查', CODE_REVIEW: '代码检查', FINDING_CHALLENGE: '问题复核', MODEL: '目标分析', CONTEXT_SUPPLEMENT: '上下文补充', AGENT: '补充分析', AGENT_TOOL: '工具调用' } as Record<string, string>)[scope] ?? '其他检查'
}

function stateLabel(state: string) {
  return ({ ANALYZED: '已完成', PARTIAL: '部分完成', UNAVAILABLE: '未完成', NOT_APPLICABLE: '无需执行', SKIPPED: '已跳过', TEMPORARY: '临时结果' } as Record<string, string>)[state] ?? '状态待确认'
}

function challengeLabel(challenge: Challenge) {
  if (challenge.verdict === 'SUPPORTED') return '证据支持'
  if (challenge.verdict === 'UNSUPPORTED') return '当前证据不足'
  if (challenge.verdict === 'NEEDS_HUMAN') return '需人工确认'
  return '复核未完成'
}

function editLabel(editType: string) {
  return ({ ADDED: '新增', MODIFIED: '修改', DELETED: '删除', RENAMED: '重命名' } as Record<string, string>)[editType] ?? editType
}

function editMark(editType: string) {
  return ({ ADDED: 'A', MODIFIED: 'M', DELETED: 'D', RENAMED: 'R' } as Record<string, string>)[editType] ?? '•'
}

function selectFile(file: GitFile) { emit('selectFile', file.path) }
</script>

<template>
  <aside class="notebook-pane notebook-sources">
    <header class="notebook-pane-header source-pane-header"><div><h2>审查来源</h2></div><span v-if="gitDiff" class="source-file-count">{{ gitDiff.files.length }}</span></header>
    <section class="source-input-overview"><div><span>输入版本</span><strong :title="snapshotLabel ?? ''">{{ snapshotLabel ? `${snapshotLabel.slice(0, 12)}…` : '尚未创建' }}</strong></div><div><span>变更文件</span><strong>{{ gitDiff?.files.length ?? 0 }}</strong></div><div><span>已引用</span><strong>{{ evidence.length }}</strong></div></section>
    <section v-if="gitDiff" class="source-file-section"><header><div><h3>代码变更</h3></div><span>{{ gitDiff.files.length }} 个文件</span></header><div class="source-file-list"><button v-for="file in gitDiff.files" :key="`${file.path}-${file.edit_type}`" :class="['source-file-item', { selected: props.selectedFilePath === file.path }]" type="button" @click="selectFile(file)"><span :class="['source-file-mark', file.edit_type.toLowerCase()]">{{ editMark(file.edit_type) }}</span><span class="source-file-copy"><strong :title="file.path">{{ file.path }}</strong><small>{{ editLabel(file.edit_type) }} · +{{ file.additions }} / -{{ file.deletions }}<template v-if="file.binary"> · 二进制文件</template></small></span></button></div></section>
    <details v-if="codeReview" class="source-check-details ui-disclosure">
      <summary><span>代码检查</span><strong :class="{ 'check-incomplete': reviewSummary.incomplete }">{{ reviewSummary.label }}</strong></summary>
      <p v-if="reviewSummary.message">{{ reviewSummary.message }}</p>
      <button v-if="reviewSummary.incomplete" type="button" class="check-log-link" @click="emit('showRunLog')">查看运行记录</button>
      <article v-for="finding in codeReview.findings" :key="finding.id" class="source-item">
        <div>
          <span class="source-kind">{{ ({ HIGH: '高风险', MEDIUM: '中风险', LOW: '低风险' } as Record<string, string>)[finding.severity] ?? finding.severity }}</span>
          <strong>{{ finding.title }}</strong>
          <small>{{ challengeLabel(finding.challenge) }}</small>
          <p>{{ finding.problem }}</p><p>触发：{{ finding.triggerScenario }}</p><p>建议：{{ finding.recommendation }}</p>
          <p v-if="finding.challenge.reason">复核依据：{{ finding.challenge.reason }}</p>
        </div>
      </article>
      <details v-if="codeReview.coverage.length" class="check-technical-details ui-disclosure">
        <summary>技术详情</summary>
        <div v-for="(coverage, index) in codeReview.coverage" :key="index" class="check-stage">
          <div><strong>{{ scopeLabel(coverage.scopeKind) }}</strong><span>{{ stateLabel(coverage.state) }}</span></div>
          <p v-if="coverage.reasonCode">{{ reasonLabel(coverage.reasonCode) }}</p>
          <code>{{ coverage.scopeKind }} · {{ coverage.state }}<template v-if="coverage.reasonCode"> · {{ coverage.reasonCode }}</template></code>
        </div>
      </details>
    </details>
    <details v-if="evidence.length" class="source-citation-section source-check-details ui-disclosure"><summary>全部引用 · {{ evidence.length }} 条</summary><div class="source-list"><article v-for="item in evidence" :key="item.id" class="source-item"><div><span class="source-kind">{{ item.kind }}</span><strong>{{ item.title }}</strong><small>{{ item.locator }}</small></div><span :class="['source-state', item.state === '待补充' ? 'pending' : 'cited']">{{ item.state }}</span></article></div></details>
  </aside>
</template>
