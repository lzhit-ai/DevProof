<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiRequest, projectHeaders, selectedProject, selectedProjectId } from '../features/projects/project-context'

interface ScanArtifact { id: string; repository_id: string; target_sha: string; scan_type: string; scanner_name: string; scanner_version: string; rule_set_version: string; coverage: Record<string, unknown>; content_hash: string; finding_count: number; created_at: string }
interface SecurityBaseline { id: string; target_sha: string; snapshot_hash: string; summary: Record<string, unknown>; coverage: Record<string, unknown>; created_at: string }
interface BaselineRecord { id: string; record_no: string; confirmation_reason: string; confirmed_at: string }
interface SecurityExplanation { scope: Record<string, unknown>; summary: Record<string, unknown>; observations: string[]; limitations: string[] }
interface QualityTrendPoint { artifact_id: string; target_sha: string; created_at: string; content_hash: string; finding_count: number; severity_counts: Record<string, number>; status_counts: Record<string, number>; coverage: Record<string, unknown> }
interface QualityTrendSeries { series_key: string; repository_id: string; scan_type: string; scanner_name: string; scanner_version: string; rule_set_version: string; points: QualityTrendPoint[] }
interface QualityTrend { series: QualityTrendSeries[]; limitations: string[] }
interface PeripheralProfileRun { id: string; assessment_profile: string; run_status: string; input_hash: string; output: Record<string, unknown>; coverage: Record<string, unknown>; limitations: string[]; created_at: string }

const artifacts = ref<ScanArtifact[]>([])
const baselines = ref<SecurityBaseline[]>([])
const records = ref<BaselineRecord[]>([])
const qualityTrend = ref<QualityTrend>({ series: [], limitations: [] })
const profileRuns = ref<PeripheralProfileRun[]>([])
const selectedArtifact = ref<ScanArtifact | null>(null)
const explanation = ref<SecurityExplanation | null>(null)
const busy = ref(false)
const message = ref('')
const latest = computed(() => baselines.value[0] ?? null)
const latestBaselineRun = computed(() => profileRuns.value.find((run) => run.assessment_profile === 'SECURITY_BASELINE') ?? null)
const latestTrendRun = computed(() => profileRuns.value.find((run) => run.assessment_profile === 'QUALITY_TREND') ?? null)

function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) }
function serialise(value: unknown) { return JSON.stringify(value ?? {}, null, 2) }

async function load() {
  const projectId = selectedProjectId.value
  if (!projectId) { artifacts.value = []; baselines.value = []; records.value = []; qualityTrend.value = { series: [], limitations: [] }; profileRuns.value = []; selectedArtifact.value = null; explanation.value = null; return }
  busy.value = true
  try {
    const [artifactList, baselineList, recordList, trend, runs] = await Promise.all([
      apiRequest<ScanArtifact[]>(`/projects/${projectId}/security-scan-artifacts`, { headers: projectHeaders() }),
      apiRequest<SecurityBaseline[]>(`/projects/${projectId}/security-baselines`, { headers: projectHeaders() }),
      apiRequest<BaselineRecord[]>(`/projects/${projectId}/security-baseline-records`, { headers: projectHeaders() }),
      apiRequest<QualityTrend>(`/projects/${projectId}/quality-trend`, { headers: projectHeaders() }),
      apiRequest<PeripheralProfileRun[]>(`/projects/${projectId}/peripheral-profile-runs`, { headers: projectHeaders() }),
    ])
    if (projectId !== selectedProjectId.value) return
    artifacts.value = artifactList; baselines.value = baselineList; records.value = recordList; qualityTrend.value = trend; profileRuns.value = runs
    message.value = baselineList.length ? '' : '暂无扫描结果。'
  } catch (error) { if (projectId === selectedProjectId.value) message.value = error instanceof Error ? error.message : '安全基线加载失败' } finally { if (projectId === selectedProjectId.value) busy.value = false }
}

async function showExplanation(artifact: ScanArtifact) {
  const projectId = selectedProjectId.value
  if (!projectId) return
  selectedArtifact.value = artifact
  explanation.value = null
  busy.value = true
  try {
    explanation.value = await apiRequest<SecurityExplanation>(`/projects/${projectId}/security-scan-artifacts/${artifact.id}/explanation`, { headers: projectHeaders() })
  } catch (error) {
    message.value = error instanceof Error ? error.message : '安全解释加载失败'
  } finally { busy.value = false }
}

function closeExplanation() { selectedArtifact.value = null; explanation.value = null }

async function createBaselineRun() {
  const projectId = selectedProjectId.value
  const baseline = latest.value
  if (!projectId || !baseline) return
  busy.value = true
  try {
    await apiRequest<PeripheralProfileRun>(`/projects/${projectId}/peripheral-profile-runs`, {
      method: 'POST', headers: projectHeaders(true), body: JSON.stringify({ assessment_profile: 'SECURITY_BASELINE', security_baseline_id: baseline.id }),
    })
    message.value = '安全基线已保存。'
    await load()
  } catch (error) { message.value = error instanceof Error ? error.message : '安全基线运行创建失败' } finally { busy.value = false }
}

async function createTrendRun(series: QualityTrendSeries) {
  const projectId = selectedProjectId.value
  if (!projectId || series.points.length < 2 || series.points.length > 300) return
  busy.value = true
  try {
    await apiRequest<PeripheralProfileRun>(`/projects/${projectId}/peripheral-profile-runs`, {
      method: 'POST', headers: projectHeaders(true), body: JSON.stringify({ assessment_profile: 'QUALITY_TREND', scan_artifact_ids: series.points.map((point) => point.artifact_id) }),
    })
    message.value = '趋势快照已保存。'
    await load()
  } catch (error) { message.value = error instanceof Error ? error.message : '质量趋势运行创建失败' } finally { busy.value = false }
}

watch(selectedProjectId, () => { void load() }, { immediate: true })
</script>

<template>
  <section class="page page-security"><header class="page-heading"><div><h1>安全与质量</h1><p v-if="!selectedProject">请先选择项目。</p></div></header><p class="page-context-note">{{ message }}</p>
    <template v-if="selectedProject"><section v-if="latest" class="surface status-summary"><div class="surface-heading"><h2>最新安全基线</h2><time>{{ formatDate(latest.created_at) }}</time></div><div class="state-brief-grid"><div><strong>目标 SHA</strong><p>{{ latest.target_sha }}</p></div><div><strong>基线哈希</strong><p>{{ latest.snapshot_hash }}</p></div><div><strong>覆盖说明</strong><p>只对应基线中引用的扫描工件、扫描器版本与规则版本。</p></div></div><div class="security-json"><section><h3>风险汇总</h3><pre>{{ serialise(latest.summary) }}</pre></section><section><h3>覆盖范围与缺口</h3><pre>{{ serialise(latest.coverage) }}</pre></section></div></section>
      <section v-if="latest" class="surface profile-run-panel"><div class="surface-heading"><div><h2>安全基线运行</h2></div><button class="primary-button" type="button" :disabled="busy" @click="createBaselineRun">固化本次运行</button></div><template v-if="latestBaselineRun"><div class="profile-run-record"><div><strong>最近运行</strong><p>{{ formatDate(latestBaselineRun.created_at) }} · {{ latestBaselineRun.run_status }}</p></div><div><strong>输入哈希</strong><p>{{ latestBaselineRun.input_hash }}</p></div></div><pre class="profile-run-output">{{ serialise(latestBaselineRun.output) }}</pre><p v-for="item in latestBaselineRun.limitations" :key="item" class="profile-run-limit">{{ item }}</p></template><p v-else class="empty-row">暂无基线运行。</p></section>
      <section v-if="selectedArtifact" class="surface security-explanation"><div class="surface-heading"><div><h2>安全解释</h2><p>{{ selectedArtifact.scan_type }} · {{ selectedArtifact.target_sha.slice(0, 12) }}…</p></div><button type="button" @click="closeExplanation">关闭</button></div><template v-if="explanation"><div class="security-json"><section><h3>已导入事实汇总</h3><pre>{{ serialise(explanation.summary) }}</pre></section><section><h3>范围与定位</h3><pre>{{ serialise(explanation.scope) }}</pre></section></div><div class="security-explanation-copy"><section><h3>解释</h3><p v-for="item in explanation.observations" :key="item">{{ item }}</p></section><section><h3>限制</h3><p v-for="item in explanation.limitations" :key="item">{{ item }}</p></section></div></template><p v-else class="empty-row">正在读取选定扫描工件的已导入事实。</p></section>
      <section class="surface"><div class="surface-heading"><h2>导入的扫描工件</h2></div><div v-if="artifacts.length" class="data-table security-artifact-table"><div class="table-row table-header"><span>扫描类型</span><span>扫描器 / 规则</span><span>目标 SHA</span><span>发现数</span><span>导入时间</span><span>操作</span></div><div v-for="artifact in artifacts" :key="artifact.id" class="table-row"><strong>{{ artifact.scan_type }}</strong><span>{{ artifact.scanner_name }} {{ artifact.scanner_version }} · {{ artifact.rule_set_version }}</span><span>{{ artifact.target_sha.slice(0, 12) }}…</span><span>{{ artifact.finding_count }}</span><time>{{ formatDate(artifact.created_at) }}</time><button type="button" :disabled="busy" @click="showExplanation(artifact)">解释范围</button></div></div><p v-else class="empty-row">暂无导入的扫描工件。</p></section>
      <section class="surface quality-trend"><div class="surface-heading"><h2>质量趋势</h2></div><p class="table-note">选择同一仓库和扫描规则下的结果。</p><div v-for="series in qualityTrend.series" :key="series.series_key" class="quality-series"><header><strong>{{ series.scan_type }} · {{ series.scanner_name }} {{ series.scanner_version }}</strong><small>规则 {{ series.rule_set_version }} · {{ series.points.length }} 个可比工件</small></header><div v-for="point in series.points" :key="point.artifact_id" class="quality-point"><time>{{ formatDate(point.created_at) }}</time><span>{{ point.target_sha.slice(0, 12) }}…</span><strong>{{ point.finding_count }} 项发现</strong><small>严重度 {{ serialise(point.severity_counts) }}</small></div></div><p v-if="!qualityTrend.series.length" class="empty-row">暂无可比较的导入扫描或 CI 工件。</p><div v-if="qualityTrend.limitations.length" class="quality-limitations"><p v-for="item in qualityTrend.limitations" :key="item">{{ item }}</p></div></section>
      <section v-if="qualityTrend.series.length" class="surface profile-run-panel"><div class="surface-heading"><div><h2>质量趋势运行</h2><p>请选择至少包含两份扫描结果的序列。</p></div></div><article v-for="series in qualityTrend.series" :key="series.series_key" class="profile-run-choice"><div><strong>{{ series.scan_type }} · {{ series.scanner_name }} {{ series.scanner_version }}</strong><p>规则 {{ series.rule_set_version }} · {{ series.points.length }} 个可比工件</p></div><button type="button" :disabled="busy || series.points.length < 2 || series.points.length > 300" @click="createTrendRun(series)">固化该序列</button></article><template v-if="latestTrendRun"><div class="profile-run-record"><div><strong>最近运行</strong><p>{{ formatDate(latestTrendRun.created_at) }} · {{ latestTrendRun.run_status }}</p></div><div><strong>输入哈希</strong><p>{{ latestTrendRun.input_hash }}</p></div></div><pre class="profile-run-output">{{ serialise(latestTrendRun.output) }}</pre><p v-for="item in latestTrendRun.limitations" :key="item" class="profile-run-limit">{{ item }}</p></template></section>
      <section class="surface"><div class="surface-heading"><h2>已确认的基线记录</h2></div><div v-if="records.length" class="data-table"><div class="table-row table-header"><span>记录号</span><span>确认说明</span><span>确认时间</span></div><div v-for="record in records" :key="record.id" class="table-row"><strong>{{ record.record_no }}</strong><span>{{ record.confirmation_reason }}</span><time>{{ formatDate(record.confirmed_at) }}</time></div></div><p v-else class="empty-row">暂无已确认的安全基线记录。</p></section>
    </template>
  </section>
</template>
