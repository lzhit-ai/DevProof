<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import type { PlanBody, PlannedIssue } from './types'

const props = defineProps<{ plan: PlanBody; title: string; status: string }>()
const selectedKey = ref(props.plan.issues[0]?.key ?? '')
const markerId = useId().replace(/:/g, '')
const panelId = `${markerId}-detail`
const selectedIssue = computed(() => props.plan.issues.find(issue => issue.key === selectedKey.value))
const incoming = computed(() => props.plan.dependencies.filter(edge => edge.consumer === selectedKey.value))
const outgoing = computed(() => props.plan.dependencies.filter(edge => edge.provider === selectedKey.value))
const acceptanceCount = computed(() => props.plan.issues.reduce((count, issue) => count + issue.acceptanceCriteria.length, 0))
watch(() => props.plan, () => {
  if (selectedKey.value && !props.plan.issues.some(issue => issue.key === selectedKey.value)) selectedKey.value = props.plan.issues[0]?.key ?? ''
})
function issueTitle(key: string) { return props.plan.issues.find(issue => issue.key === key)?.title ?? key }

// The persisted plan is a DAG: keep every dependency, including joins across branches.
const graph = computed(() => {
  const nodeWidth = 288, nodeHeight = 138, rootWidth = 342, rootHeight = 104, gapX = 40, gapY = 36, padding = 24
  const levels = new Map<string, number>(props.plan.issues.map(issue => [issue.key, 0]))
  const parents = new Map<string, Set<string>>(props.plan.issues.map(issue => [issue.key, new Set()]))
  const children = new Map<string, Set<string>>(props.plan.issues.map(issue => [issue.key, new Set()]))
  for (const edge of props.plan.dependencies) {
    parents.get(edge.consumer)?.add(edge.provider)
    children.get(edge.provider)?.add(edge.consumer)
  }
  const remaining = new Map([...parents].map(([key, keys]) => [key, keys.size]))
  const queue = props.plan.issues.filter(issue => remaining.get(issue.key) === 0).map(issue => issue.key)
  for (let index = 0; index < queue.length; index++) {
    const key = queue[index]!
    for (const child of children.get(key) ?? []) {
      levels.set(child, Math.max(levels.get(child) ?? 0, (levels.get(key) ?? 0) + 1))
      remaining.set(child, remaining.get(child)! - 1)
      if (remaining.get(child) === 0) queue.push(child)
    }
  }
  const rows: PlannedIssue[][] = []
  for (const issue of props.plan.issues) (rows[levels.get(issue.key) ?? 0] ??= []).push(issue)
  const contentWidth = Math.max(rootWidth, ...rows.map(row => row.length * (nodeWidth + gapX) - gapX))
  const center = padding + contentWidth / 2
  const nodes = rows.flatMap((row, level) => row.map((issue, index) => ({
    issue, level, parallel: row.length > 1,
    parentCount: parents.get(issue.key)?.size ?? 0,
    x: padding + (contentWidth - row.length * (nodeWidth + gapX) + gapX) / 2 + index * (nodeWidth + gapX),
    y: padding + rootHeight + gapY + level * (nodeHeight + gapY),
  })))
  const byKey = new Map(nodes.map(node => [node.issue.key, node]))
  const edges: { key: string; provider: string; consumer: string; path: string; root: boolean }[] = []
  for (const node of nodes.filter(item => item.parentCount === 0)) {
    const endX = node.x + nodeWidth / 2, startY = padding + rootHeight, middle = startY + gapY / 2
    edges.push({ key: `root-${node.issue.key}`, provider: '', consumer: node.issue.key, root: true,
      path: `M ${center} ${startY} C ${center} ${middle}, ${endX} ${middle}, ${endX} ${node.y}` })
  }
  const seen = new Set<string>()
  let sideLanes = 0
  for (const dependency of props.plan.dependencies) {
    const key = JSON.stringify([dependency.provider, dependency.consumer])
    if (seen.has(key)) continue
    seen.add(key)
    const start = byKey.get(dependency.provider), end = byKey.get(dependency.consumer)
    if (!start || !end) continue
    const sx = start.x + nodeWidth / 2, sy = start.y + nodeHeight, ex = end.x + nodeWidth / 2, ey = end.y
    const mid = (sy + ey) / 2
    let path = `M ${sx} ${sy} C ${sx} ${mid}, ${ex} ${mid}, ${ex} ${ey}`
    if (end.level - start.level > 1) {
      const lane = padding + contentWidth + 16 + sideLanes++ * 18
      path = `M ${sx} ${sy} V ${sy + 18} H ${lane} V ${ey - 18} H ${ex} V ${ey}`
    }
    edges.push({ key, provider: dependency.provider, consumer: dependency.consumer, path, root: false })
  }
  return { nodes, edges, nodeWidth, nodeHeight, rootWidth, rootHeight, rootX: center - rootWidth / 2, rootY: padding,
    width: padding * 2 + contentWidth + (sideLanes ? sideLanes * 18 + 22 : 0),
    height: padding * 2 + rootHeight + rows.length * (nodeHeight + gapY) }
})
</script>

<template>
  <div class="plan-tree-workspace">
    <section class="plan-tree-overview" aria-label="PR 与 Issue 依赖关系">
      <header class="plan-tree-panel-heading"><h4>工作项关系</h4><span>{{ plan.issues.length }} 个 Issue</span></header>
      <div class="plan-tree-legend"><span><i class="tree-legend-line" />前置依赖</span><span>同层可并行</span></div>
      <div class="plan-tree-viewport" tabindex="0" aria-label="Issue 关系图，可滚动查看">
        <div class="plan-tree-canvas" :style="{ width: `${graph.width}px`, height: `${graph.height}px` }">
          <svg class="plan-tree-edges" :width="graph.width" :height="graph.height" aria-hidden="true">
            <defs><marker :id="markerId" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 1 1 L 7 4 L 1 7" fill="none" stroke="currentColor" stroke-width="1.4" /></marker></defs>
            <path v-for="edge in graph.edges" :key="edge.key" :d="edge.path" :class="{ 'is-root': edge.root, 'is-selected': selectedKey === edge.consumer || selectedKey === edge.provider }" :marker-end="`url(#${markerId})`" />
          </svg>
          <button type="button" class="plan-tree-root" :class="{ 'is-selected': !selectedKey }" :style="{ left: `${graph.rootX}px`, top: `${graph.rootY}px`, width: `${graph.rootWidth}px`, height: `${graph.rootHeight}px` }" :aria-pressed="!selectedKey" :aria-controls="panelId" @click="selectedKey = ''">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="6" cy="5" r="2.5" /><circle cx="6" cy="19" r="2.5" /><circle cx="18" cy="19" r="2.5" /><path d="M6 7.5v9M18 16.5v-6a5 5 0 0 0-5-5h-1m2.5-2.5L12 5.5 14.5 8" /></svg>
            <span><strong>PR 目标 · {{ title }}</strong><small>{{ status }} · {{ plan.issues.length }} 个 Issue · {{ acceptanceCount }} 条验收</small></span>
          </button>
          <button v-for="node in graph.nodes" :key="node.issue.key" type="button" class="plan-tree-node" :class="{ 'is-selected': selectedKey === node.issue.key }" :style="{ left: `${node.x}px`, top: `${node.y}px`, width: `${graph.nodeWidth}px`, height: `${graph.nodeHeight}px` }" :title="node.issue.title" :aria-pressed="selectedKey === node.issue.key" :aria-controls="panelId" :aria-label="`查看 ${node.issue.key} ${node.issue.title}`" @click="selectedKey = node.issue.key">
            <span class="tree-node-meta"><span>{{ node.issue.key }}</span><span>{{ node.issue.acceptanceCriteria.length }} 条验收</span></span>
            <strong>{{ node.issue.title }}</strong>
            <span class="tree-node-relation" :class="{ 'has-prerequisites': node.parentCount }">{{ node.parentCount ? `前置依赖 ${node.parentCount} 项` : '无前置依赖' }}<span v-if="node.parallel"> · 同层可并行</span></span>
          </button>
        </div>
      </div>

    </section>

    <section :id="panelId" :key="selectedKey" class="plan-issue-reader" :aria-label="selectedIssue ? `${selectedIssue.key} 详情` : 'PR 目标详情'">
      <template v-if="selectedIssue">
        <header class="issue-reader-heading"><span>{{ selectedIssue.key }}</span><h3>{{ selectedIssue.title }}</h3><p>{{ selectedIssue.goal }}</p></header>
        <div v-if="incoming.length || outgoing.length" class="issue-relation-summary">
          <details v-if="incoming.length" class="issue-reader-disclosure ui-disclosure"><summary>前置依赖 · {{ incoming.length }} 项</summary><ul><li v-for="(edge, index) in incoming" :key="index"><button type="button" class="issue-reference-button" @click="selectedKey = edge.provider">{{ edge.provider }} · {{ issueTitle(edge.provider) }}</button><p>{{ edge.condition }}</p></li></ul></details>
          <details v-if="outgoing.length" class="issue-reader-disclosure ui-disclosure"><summary>影响后续 · {{ new Set(outgoing.map(edge => edge.consumer)).size }} 个 Issue</summary><ul><li v-for="(edge, index) in outgoing" :key="index"><button type="button" class="issue-reference-button" @click="selectedKey = edge.consumer">{{ edge.consumer }} · {{ issueTitle(edge.consumer) }}</button><p>{{ edge.reason }}</p></li></ul></details>
        </div>
        <h4>验收条件 <span>{{ selectedIssue.acceptanceCriteria.length }}</span></h4>

        <ol class="issue-acceptance-list">
          <li v-for="criterion in selectedIssue.acceptanceCriteria" :key="criterion.key"><details><summary>{{ criterion.condition }}</summary><div class="issue-acceptance-check"><h5>怎么检查</h5><p>{{ criterion.verificationMethod }}</p><h5>需要的证据</h5><ul><li v-for="(evidence, index) in criterion.requiredEvidence" :key="index">{{ evidence }}</li></ul></div></details></li>
        </ol>
        <details class="issue-reader-disclosure ui-disclosure"><summary>范围与边界</summary><p>{{ selectedIssue.scope }}</p></details>
        <details v-if="selectedIssue.deliverables.length" class="issue-reader-disclosure ui-disclosure"><summary>交付内容 · {{ selectedIssue.deliverables.length }} 项</summary><ul><li v-for="artifact in selectedIssue.deliverables" :key="artifact.key"><p>{{ artifact.description }}</p><small>可供后续使用的条件</small><p>{{ artifact.availabilityCondition }}</p></li></ul></details>
        <details v-if="selectedIssue.reuseRefs.length" class="issue-reader-disclosure ui-disclosure"><summary>代码依据 · {{ selectedIssue.reuseRefs.length }} 处</summary><ul><li v-for="(reference, index) in selectedIssue.reuseRefs" :key="index"><code>{{ reference.path }}:{{ reference.startLine }}–{{ reference.endLine }}</code><p>{{ reference.reason }}</p></li></ul></details>
        <details v-if="selectedIssue.assumptions.length" class="issue-reader-disclosure ui-disclosure"><summary>待核对事项 · {{ selectedIssue.assumptions.length }} 项</summary><ul><li v-for="(assumption, index) in selectedIssue.assumptions" :key="index">{{ assumption }}</li></ul></details>
      </template>
      <template v-else>
        <header class="issue-reader-heading"><h3>{{ title }}</h3><p>{{ status }} · {{ plan.issues.length }} 个 Issue</p></header>
        <h4>计划说明</h4><p class="issue-plan-summary">{{ plan.summary }}</p>
        <details v-if="plan.risks.length" class="issue-reader-disclosure ui-disclosure"><summary>需要关注的风险 · {{ plan.risks.length }} 项</summary><ul><li v-for="(risk, index) in plan.risks" :key="index">{{ risk }}</li></ul></details>
      </template>
    </section>
  </div>
</template>
