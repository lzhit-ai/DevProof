<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import ReviewDetailPane from "../features/notebook/ReviewDetailPane.vue";
import SourceEvidencePane from "../features/notebook/SourceEvidencePane.vue";
import VerificationPane from "../features/notebook/VerificationPane.vue";
import PlanAcceptanceBinding, { type PlanClaimReference } from "../features/planning/PlanAcceptanceBinding.vue";
import {
  apiRequest,
  projectHeaders,
  selectedProjectId,
} from "../features/projects/project-context";
import type {
  EvidenceReference,
  VerificationConclusion,
} from "../types/workbench";

type AnalysisRun = { id: string; snapshot_id: string; run_status: string };
type RunEvent = {
  id: string;
  nodeId: string | null;
  eventType: string;
  status: string;
  details: Record<string, unknown>;
  createdAt: string;
};
type SourceItem = {
  id: string;
  logical_name: string;
  source_role: string;
  revision_no: number;
  processing_status: string;
};
type GitRepository = { id: string; display_url: string; read_only: boolean };
type GitSnapshot = {
  id: string;
  base_sha: string;
  target_sha: string;
  diff_hash: string;
  coverage: { changedFiles?: string[] };
};
type GitDiff = {
  files: Array<{
    path: string;
    old_path?: string | null;
    edit_type: string;
    additions: number;
    deletions: number;
    binary: boolean;
    hunks: Array<{ header: string; payload: string }>;
  }>;
  coverage: Record<string, unknown>;
};
type CodeReview = {
  gitSnapshotId: string | null;
  findings: Array<{
    id: string;
    evidenceId: string;
    severity: string;
    findingKind: string;
    title: string;
    problem: string;
    triggerScenario: string;
    recommendation: string;
    confidence: number;
    challenge: {
      state: string;
      verdict: string | null;
      reason: string | null;
      evidenceIds: string[];
    };
  }>;
  coverage: Array<{
    scopeKind: string;
    state: string;
    reasonCode: string | null;
    details: Record<string, unknown>;
  }>;
};
type ProjectReport = {
  id: string;
  cycle_id: string;
  sequence_no: number;
  status: string;
  editorial_note: string;
  version: number;
  content_hash: string;
};
type ReportPreview = ProjectReport & {
  snapshot_hash: string;
  task_title: string;
  requirement_key: string;
  items: Array<{
    id: string;
    claimText: string;
    result: {
      status: string;
      reason: string;
      humanDecision: {
        decision: string;
        note: string;
        createdAt: string | null;
      } | null;
    };
    disposition: string | null;
    citations: Array<{
      id: string;
      sourceType: string;
      excerpt: string;
      locator: Record<string, unknown>;
    }>;
  }>;
};
type RunOrchestration = {
  contentHash: string;
  template: { name: string; version: number };
  nodes: Array<{
    capabilityKey: string;
    capabilityName: string;
    capabilityVersion: number;
    displayOrder: number;
    locked: boolean;
    tools: Array<{ key: string }>;
  }>;
};
type ResultEvidence = {
  id: string;
  sourceType: string;
  excerpt: string;
  locator: Record<string, unknown>;
  precision: string;
};
type AnalysisResult = {
  id: string;
  claim_text: string;
  status: string;
  reason: string;
  requires_human_confirmation: boolean;
  evidence: ResultEvidence[];
  evidence_assessments?: VerificationConclusion["evidenceAssessments"];
  risks: Array<{ severity: string }>;
  human_decision: {
    id: string;
    decision: string;
    note: string;
    actorId: string;
    createdAt: string | null;
  } | null;
  allowed_human_decisions: string[];
};
type DeliveryClaim = {
  id: string;
  claim_key: string;
  text: string;
  rationale: string;
  origin: "MODEL" | "HUMAN";
  status: "CANDIDATE" | "CONFIRMED";
  source_manifest: Record<string, unknown>;
};
type ToolExecution = {
  id: string;
  analysis_run_id: string;
  capability_key: string;
  tool_key: string;
  content_hash: string;
  excerpt_safe: string;
  locator: Record<string, unknown>;
  status: string;
  imported_manual_evidence_id: string | null;
};
type PullRequestRange = {
  number: string;
  baseRef: string;
  baseSha: string;
  headRef: string;
  headSha: string;
  mergedAt: string | null;
};
type TaskContext = {
  id: string;
  title: string;
  cycle_id: string | null;
  cycle_status: string;
  formal_snapshot_id: string | null;
  formal_snapshot_hash: string | null;
  report_id: string | null;
  report_status: string | null;
  delivery_pull_request: PullRequestRange | null;
};

const route = useRoute();
const selectedId = ref("pending-result");
const task = ref<TaskContext | null>(null);
const sources = ref<SourceItem[]>([]);
const repositories = ref<GitRepository[]>([]);
const selectedSourceIds = ref<string[]>([]);
const claimEdits = ref<
  Array<{
    id?: string;
    text: string;
    rationale: string;
    origin: "MODEL" | "HUMAN";
    status: "CANDIDATE" | "CONFIRMED";
    selected: boolean;
    planAcceptance?: PlanClaimReference;
  }>
>([]);
const planBinding = ref<InstanceType<typeof PlanAcceptanceBinding> | null>(null);
const gitForm = ref({
  repositoryId: "",
  baseRef: "main",
  targetRef: "HEAD",
  diffMode: "TWO_DOT",
  includePaths: "",
  excludePaths: "",
});
const gitSnapshot = ref<GitSnapshot | null>(null);
const liveRun = ref<AnalysisRun | null>(null);
const liveEvents = ref<RunEvent[]>([]);
const liveOrchestration = ref<RunOrchestration | null>(null);
const liveResults = ref<AnalysisResult[]>([]);
const liveCodeReview = ref<CodeReview>({
  gitSnapshotId: null,
  findings: [],
  coverage: [],
});
const liveGitDiff = ref<GitDiff | null>(null);
const toolExecutions = ref<ToolExecution[]>([]);
const report = ref<ProjectReport | null>(null);
const reportPreview = ref<ReportPreview | null>(null);
const reportNote = ref("");
const decisionNote = ref("");
const decisionMessage = ref("");
const busy = ref(false);
const startPhase = ref("");
const startError = ref("");
const detailPaneOpen = ref(true);
const reportOpen = ref(false);
let frozenGitSelection = "";
let startRequestKey = "";
const runLogOpen = ref(false);
const centerView = ref<"conclusions" | "diff">("conclusions");
const selectedDiffPath = ref("");
const preparationMessage = ref("");
const claimMessage = ref(
  "从 PR 提取的目标默认纳入本轮，可直接修改或移除。",
);
const reportMessage = ref(
  "运行结束后，系统会根据冻结结果生成可提交的报告草稿。",
);
const toolImportNames = ref<Record<string, string>>({});
const importingToolExecutionId = ref("");
const toolExecutionError = ref("");
const toolImportMessage = ref("");
const liveLoadError = ref("");
let pollTimer: ReturnType<typeof window.setTimeout> | undefined;
let claimProposalEpoch = 0;
const activeClaimProposal = ref("");
const claimCancelling = ref(false);

const readySources = computed(() =>
  sources.value.filter((source) => source.processing_status === "READY"),
);
const confirmedClaimCount = computed(
  () =>
    claimEdits.value.filter(
      (claim) => claim.status === "CONFIRMED" && claim.text.trim().length >= 3,
    ).length,
);
const selectedClaimCount = computed(
  () =>
    claimEdits.value.filter(
      (claim) => claim.selected && claim.text.trim().length >= 3,
    ).length,
);
const canFreezeGit = computed(() =>
  Boolean(
    task.value?.cycle_id &&
    gitForm.value.repositoryId &&
    gitForm.value.baseRef.trim() &&
    gitForm.value.targetRef.trim(),
  ),
);
const claimsConfirmed = computed(() => confirmedClaimCount.value > 0 &&
  claimEdits.value.every((claim) => claim.selected && claim.status === "CONFIRMED"));
const canStartRun = computed(() =>
  Boolean(
    (task.value?.formal_snapshot_id ? confirmedClaimCount.value > 0 :
      selectedClaimCount.value > 0 && claimEdits.value.every((claim) => !claim.selected || claim.text.trim().length >= 3)) &&
    (task.value?.formal_snapshot_id || canFreezeGit.value),
  ),
);
const reviewStatus = computed(() => {
  const status = liveRun.value?.run_status ?? task.value?.cycle_status ?? "";
  return ({ QUEUED: "等待审查", RUNNING: "审查中", SUCCEEDED: "审查完成",
    PARTIALLY_COMPLETED: "部分完成", FAILED: "审查失败", CANCELLED: "已取消",
    DRAFT: "待开始", ANALYZING: "审查中", DRAFT_READY: "待提交",
    NEEDS_EVIDENCE: "待补证", NEEDS_CONFIRMATION: "待确认", PENDING_REVIEW: "待审批",
    APPROVED: "已批准", PUBLISHED: "已留档" } as Record<string, string>)[status] ?? "待准备";
});
const activeRun = computed(() =>
  Boolean(
    liveRun.value &&
    !["SUCCEEDED", "PARTIALLY_COMPLETED", "FAILED", "CANCELLED"].includes(
      liveRun.value.run_status,
    ),
  ),
);
const pendingReportDraft = computed(() => {
  const last = liveEvents.value.filter(event => event.eventType === "REPORT_DRAFT").at(-1);
  return Boolean(last && ["QUEUED", "RUNNING"].includes(last.status));
});
const selectedDiffFile = computed(() => {
  const files = liveGitDiff.value?.files ?? [];
  return (
    files.find((file) => file.path === selectedDiffPath.value) ??
    files[0] ??
    null
  );
});

function splitPaths(value: string) {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}
function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
function runStepLabel(nodeId: string | null) {
  return (
    (
      {
        run_custom_agents: "补充分析",
        reconcile: "汇总证据与结论",
        "report-draft": "生成报告草稿",
        worker: "后台任务",
      } as Record<string, string>
    )[nodeId ?? ""] ?? "核验处理"
  );
}
function runStepStatus(status: string) {
  return (
    (
      {
        RUNNING: "进行中",
        SUCCEEDED: "已完成",
        FAILED: "失败",
        CANCELLED: "已取消",
        PENDING: "等待中",
      } as Record<string, string>
    )[status] ?? status
  );
}
function isUuid(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value,
    )
  );
}
function mapStatus(status: string): VerificationConclusion["status"] {
  if (status === "SUPPORTED") return "自动通过";
  if (status === "PARTIALLY_SUPPORTED") return "部分支持";
  if (status === "NOT_PROVEN") return "证据不足";
  if (status === "NOT_ANALYZED") return "未完成分析";
  if (status === "CONFLICTING" || status === "CONFLICT") return "存在冲突";
  return "待人工确认";
}
function effectiveConclusionStatus(item: AnalysisResult): VerificationConclusion["status"] {
  if (item.human_decision?.decision === "CONFIRM_SUPPORT") return "已确认";
  if (item.human_decision?.decision === "CONFIRM_PARTIAL") return "部分支持";
  if (
    item.human_decision?.decision === "CONFIRM_INSUFFICIENT" ||
    item.human_decision?.decision === "RETURN_FOR_EVIDENCE"
  )
    return "证据不足";
  return mapStatus(item.status);
}
function reportConclusionStatus(item: ReportPreview["items"][number]) {
  const decision = item.result.humanDecision?.decision;
  if (decision === "CONFIRM_SUPPORT") return "已确认";
  if (decision === "CONFIRM_PARTIAL") return "部分支持";
  if (
    decision === "CONFIRM_INSUFFICIENT" ||
    decision === "RETURN_FOR_EVIDENCE"
  )
    return "证据不足";
  return mapStatus(item.result.status);
}
function reportStatusLabel(status: string) {
  return ({ DRAFT: "草稿", SUBMITTED: "待审批", APPROVED: "已批准", REJECTED: "已退回", PUBLISHED: "已留档", SUPERSEDED: "已有新版本" } as Record<string, string>)[status] ?? status;
}

function openPendingConclusion() {
  const pending = liveConclusions.value.find((item) => item.needsHumanDecision);
  if (pending) selectConclusion(pending.id);
  centerView.value = "conclusions";
  reportOpen.value = false;
}

function mapEvidenceKind(sourceType: string): EvidenceReference["kind"] {
  if (sourceType === "CODE") return "代码";
  if (sourceType === "TEST" || sourceType === "BUILD") return "测试";
  if (sourceType === "MANUAL") return "人工补证";
  return "需求";
}
function locatorLabel(locator: Record<string, unknown>): string {
  return String(
    locator.path ??
      locator.hunk ??
      locator.toolKey ??
      locator.sourceRevisionId ??
      "冻结快照证据",
  );
}
function stopPolling() {
  if (pollTimer) window.clearTimeout(pollTimer);
  pollTimer = undefined;
}

const liveEvidence = computed<EvidenceReference[]>(() => {
  const byId = new Map<string, EvidenceReference>();
  for (const result of liveResults.value)
    for (const item of result.evidence)
      if (!byId.has(item.id))
        byId.set(item.id, {
          id: item.id,
          kind: mapEvidenceKind(item.sourceType),
          title: `${mapEvidenceKind(item.sourceType)}依据`,
          locator: locatorLabel(item.locator),
          excerpt: item.excerpt,
          state: "已引用",
        });
  return [...byId.values()];
});
const liveConclusions = computed<VerificationConclusion[]>(() =>
  liveResults.value.map((item) => ({
    id: item.id,
    requirement: item.claim_text,
    status: effectiveConclusionStatus(item),
    summary: item.reason,
    needsHumanDecision: item.requires_human_confirmation && !item.human_decision,
    risk: item.risks.some((risk) => risk.severity === "HIGH")
      ? "P0"
      : item.risks.length
        ? "P1"
        : null,
    evidenceIds: item.evidence.map((evidence) => evidence.id),
    systemStatus: item.status,
    humanDecision: item.human_decision,
    allowedHumanDecisions: item.allowed_human_decisions,
    evidenceAssessments: item.evidence_assessments,
  })),
);
const displayedConclusions = computed<VerificationConclusion[]>(() =>
  liveRun.value && liveConclusions.value.length
    ? liveConclusions.value
    : claimEdits.value
        .filter((claim) => claim.selected && claim.text.trim())
        .map((claim, index) => ({
          id: `pending-${claim.id ?? index}`,
          requirement: claim.text,
          status: "未完成分析",
          summary: liveRun.value
            ? "该主张尚未产生可展示的核验结果。请查看运行记录中的真实失败或处理状态。"
            : "该主张已确认，但尚未冻结输入并启动核验。",
          needsHumanDecision: false,
          risk: null,
          evidenceIds: [],
        })),
);
const selectedConclusion = computed(
  () =>
    displayedConclusions.value.find((item) => item.id === selectedId.value) ??
    displayedConclusions.value[0],
);
const unresolvedDecisionCount = computed(
  () =>
    liveResults.value.filter(
      (item) => item.requires_human_confirmation && !item.human_decision,
    ).length,
);

async function loadRun(run: AnalysisRun) {
  const cycleId = task.value?.cycle_id;
  const projectId = selectedProjectId.value;
  const isCurrent = () => task.value?.cycle_id === cycleId && selectedProjectId.value === projectId && liveRun.value?.id === run.id;
  liveRun.value = run;
  const results = await apiRequest<AnalysisResult[]>(
    `/analysis-runs/${run.id}/results`,
    { headers: projectHeaders() },
  );
  if (!isCurrent()) return;
  liveResults.value = results;
  if (!results.some((item) => item.id === selectedId.value))
    selectedId.value = results[0]?.id ?? "pending-result";

  const [orchestrationResult, eventsResult, codeReviewResult] =
    await Promise.allSettled([
      apiRequest<RunOrchestration>(`/analysis-runs/${run.id}/orchestration`, {
        headers: projectHeaders(),
      }),
      apiRequest<{ items: RunEvent[] }>(`/analysis-runs/${run.id}/events`, {
        headers: projectHeaders(),
      }),
      apiRequest<CodeReview>(`/analysis-runs/${run.id}/code-review`, {
        headers: projectHeaders(),
      }),
    ]);
  if (!isCurrent()) return;
  if (orchestrationResult.status === "fulfilled")
    liveOrchestration.value = orchestrationResult.value;
  if (eventsResult.status === "fulfilled")
    liveEvents.value = eventsResult.value.items;
  if (codeReviewResult.status === "fulfilled") {
    liveCodeReview.value = codeReviewResult.value;
  }
  if (
    codeReviewResult.status === "fulfilled" &&
    codeReviewResult.value.gitSnapshotId
  ) {
    try {
      const diff = await apiRequest<GitDiff>(
        `/git-snapshots/${codeReviewResult.value.gitSnapshotId}/diff`,
        { headers: projectHeaders() },
      );
      if (!isCurrent()) return;
      liveGitDiff.value = diff;
    } catch {
      if (!isCurrent()) return;
      liveGitDiff.value = null;
    }
  }
  try {
    const executions = await apiRequest<ToolExecution[]>(
      `/analysis-runs/${run.id}/tool-executions`,
      { headers: projectHeaders() },
    );
    if (!isCurrent()) return;
    toolExecutions.value = executions;
  } catch (error) {
    if (!isCurrent()) return;
    toolExecutionError.value =
      error instanceof Error
        ? `临时工具结果读取失败：${error.message}`
        : "临时工具结果读取失败。";
  }
}

async function loadReport(projectId: string, cycleId: string | null) {
  if (!cycleId) {
    report.value = null;
    reportPreview.value = null;
    return;
  }
  const reports = await apiRequest<ProjectReport[]>(
    `/projects/${projectId}/report-versions`,
    { headers: projectHeaders() },
  );
  report.value = reports.find((item) => item.cycle_id === cycleId) ?? null;
  reportNote.value = report.value?.editorial_note ?? "";
  if (!report.value) {
    reportPreview.value = null;
    return;
  }
  try {
    reportPreview.value = await apiRequest<ReportPreview>(
      `/projects/${projectId}/report-versions/${report.value.id}/content`,
      { headers: projectHeaders() },
    );
  } catch (error) {
    reportPreview.value = null;
    reportMessage.value =
      error instanceof Error
        ? `报告已保存，但内容回看暂时不可用：${error.message}`
        : "报告已保存，但内容回看暂时不可用。";
  }
}

function applyClaims(claims: DeliveryClaim[]) {
  const hasSavedScope = claims.some((claim) => claim.status === "CONFIRMED");
  const visibleClaims = task.value?.formal_snapshot_id
    ? claims.filter((claim) => claim.status === "CONFIRMED") : claims;
  claimEdits.value = visibleClaims.map((claim) => ({
    id: claim.id,
    text: claim.text,
    rationale: claim.rationale,
    origin: claim.origin,
    status: claim.status,
    selected: !hasSavedScope || claim.status === "CONFIRMED",
  }));
}

type ClaimProposalRun = { agent_task_id: string; status: string };

async function loadClaims(projectId: string, taskId: string) {
  const epoch = claimProposalEpoch;
  const [claims, runs] = await Promise.all([
    apiRequest<DeliveryClaim[]>(`/projects/${projectId}/verification-tasks/${taskId}/delivery-claims`, { headers: projectHeaders() }),
    apiRequest<ClaimProposalRun[]>(`/projects/${projectId}/verification-tasks/${taskId}/delivery-claims/proposal-runs`, { headers: projectHeaders() }),
  ]);
  if (epoch !== claimProposalEpoch || projectId !== selectedProjectId.value || taskId !== task.value?.id) return;
  applyClaims(claims);
  const active = runs.find(run => ["QUEUED", "RUNNING"].includes(run.status));
  if (active) void followClaimProposal(projectId, taskId, active.agent_task_id);
}

async function followClaimProposal(projectId: string, taskId: string, agentTaskId: string) {
  const epoch = ++claimProposalEpoch;
  const current = () => epoch === claimProposalEpoch && projectId === selectedProjectId.value && taskId === task.value?.id;
  activeClaimProposal.value = agentTaskId;
  busy.value = true;
  let previousStatus = "";
  try {
    while (current()) {
      const state = await apiRequest<{ status: string; last_error_code: string | null }>(`/agent-tasks/${agentTaskId}`, { headers: projectHeaders() });
      if (!current()) return;
      if (state.status === "SUCCEEDED") {
        const claims = await apiRequest<DeliveryClaim[]>(`/projects/${projectId}/verification-tasks/${taskId}/delivery-claims`, { headers: projectHeaders() });
        if (!current()) return;
        applyClaims(claims);
        claimMessage.value = claims.length ? "候选已提取，可调整或移除；开始审查时将确认所选交付内容。" : "现有材料不足以识别可核验交付内容，请手动补充。";
        return;
      }
      if (state.status === "FAILED" || state.status === "CANCELLED") {
        claimMessage.value = state.status === "CANCELLED" ? "候选提取任务已取消。" : `候选提取失败：${state.last_error_code ?? "执行失败"}`;
        return;
      }
      if (!["QUEUED", "RUNNING"].includes(state.status)) throw new Error("任务返回了无法识别的状态");
      if (state.status !== previousStatus) claimMessage.value = state.status === "QUEUED" ? "候选提取已排队，等待执行。" : "正在根据本次冻结的 PR 和资料提取候选…";
      previousStatus = state.status;
      await new Promise(resolve => window.setTimeout(resolve, 1000));
    }
  } catch (error) {
    if (current()) claimMessage.value = `任务状态读取失败：${error instanceof Error ? error.message : "连接失败"}。刷新页面可恢复跟踪。`;
  } finally {
    if (current()) { busy.value = false; activeClaimProposal.value = ""; }
  }
}

async function cancelClaimProposal() {
  if (!activeClaimProposal.value || claimCancelling.value) return;
  const epoch = claimProposalEpoch;
  const agentTaskId = activeClaimProposal.value;
  claimCancelling.value = true;
  try {
    await apiRequest(`/agent-tasks/${agentTaskId}/cancel`, { method: "POST", headers: projectHeaders(true) });
  } catch (error) {
    if (epoch === claimProposalEpoch) claimMessage.value = error instanceof Error ? `取消失败：${error.message}` : "取消失败。";
  } finally { if (epoch === claimProposalEpoch) claimCancelling.value = false; }
}

async function proposeClaims() {
  const projectId = selectedProjectId.value;
  const taskId = task.value?.id;
  if (!projectId || !taskId) return;
  if (claimEdits.value.length > 0 && !window.confirm("重新提取会替换当前未确认的候选交付内容。尚未确认的手动补充也会被替换，是否继续？")) return;
  const epoch = claimProposalEpoch;
  busy.value = true;
  claimMessage.value = "正在提交候选提取任务…";
  try {
    const run = await apiRequest<ClaimProposalRun>(`/projects/${projectId}/verification-tasks/${taskId}/delivery-claims/propose`, {
      method: "POST", headers: projectHeaders(true), body: JSON.stringify({ source_revision_ids: selectedSourceIds.value }),
    });
    if (epoch !== claimProposalEpoch || projectId !== selectedProjectId.value || taskId !== task.value?.id) return;
    await followClaimProposal(projectId, taskId, run.agent_task_id);
  } catch (error) {
    if (epoch === claimProposalEpoch) claimMessage.value = error instanceof Error ? `候选提取未提交：${error.message}` : "候选提取未提交，请检查实际模型配置后重试。";
  } finally {
    if (epoch === claimProposalEpoch && !activeClaimProposal.value && projectId === selectedProjectId.value && taskId === task.value?.id) busy.value = false;
  }
}

function addManualClaim() {
  if (claimEdits.value.length >= 12) return;
  claimEdits.value.push({
    text: "",
    rationale: "提交人补充的交付内容",
    origin: "HUMAN",
    status: "CANDIDATE",
    selected: true,
  });
}

function removeClaim(index: number) {
  claimEdits.value.splice(index, 1);
}

function applyPlanAcceptance() {
  const binding = planBinding.value?.imports();
  if (!binding || busy.value || task.value?.formal_snapshot_id) return;
  const retained = claimEdits.value.filter(claim => !claim.planAcceptance && (!claim.id || !binding.replaceClaimIds.includes(claim.id)));
  if (retained.length + binding.claims.length > 12) {
    claimMessage.value = "本轮最多纳入 12 条交付内容，请减少已有内容或所选验收项。";
    return;
  }
  claimEdits.value = [...retained, ...binding.claims.map(reference => ({
    text: reference.condition, rationale: `${reference.issueKey} / ${reference.acceptanceKey}`,
    origin: "HUMAN" as const, status: "CANDIDATE" as const, selected: true, planAcceptance: reference,
  }))];
  planBinding.value?.markImported(binding.plan);
  claimMessage.value = "已应用指定计划版本的验收项，开始审查时会保存来源关联。";
}

function clearPlanAcceptance() {
  for (const claim of claimEdits.value) delete claim.planAcceptance;
}

async function createNextCycle() {
  const projectId = selectedProjectId.value;
  const taskId = task.value?.id;
  if (!projectId || !taskId) return;
  busy.value = true;
  try {
    await apiRequest(
      `/projects/${projectId}/verification-tasks/${taskId}/cycles`,
      {
        method: "POST",
        headers: projectHeaders(true),
      },
    );
    preparationMessage.value =
      "已创建新的核验轮次。请重新确认交付内容并冻结新的输入。";
    await loadWorkspace();
  } catch (error) {
    preparationMessage.value =
      error instanceof Error
        ? `创建新轮次失败：${error.message}`
        : "创建新轮次失败。";
  } finally {
    busy.value = false;
  }
}

async function loadWorkspace() {
  stopPolling();
  claimProposalEpoch++;
  activeClaimProposal.value = "";
  claimCancelling.value = false;
  liveRun.value = null;
  liveEvents.value = [];
  liveOrchestration.value = null;
  liveResults.value = [];
  liveCodeReview.value = { gitSnapshotId: null, findings: [], coverage: [] };
  liveGitDiff.value = null;
  toolExecutions.value = [];
  toolExecutionError.value = "";
  liveLoadError.value = "";
  task.value = null;
  busy.value = false;
  gitSnapshot.value = null;
  frozenGitSelection = "";
  startRequestKey = "";
  startPhase.value = "";
  startError.value = "";
  preparationMessage.value = "";
  claimMessage.value = "从 PR 提取的目标默认纳入本轮，可直接修改或移除。";
  reportOpen.value = false;
  decisionNote.value = "";
  decisionMessage.value = "";
  gitForm.value = { repositoryId: "", baseRef: "main", targetRef: "HEAD", diffMode: "TWO_DOT", includePaths: "", excludePaths: "" };
  selectedSourceIds.value = [];
  report.value = null;
  reportPreview.value = null;
  claimEdits.value = [];
  centerView.value = "conclusions";
  selectedDiffPath.value = "";
  const projectId = selectedProjectId.value;
  const taskId = route.params.taskId;
  if (!projectId || !isUuid(taskId)) return;
  try {
    const [taskList, sourceList, repositoryList] = await Promise.all([
      apiRequest<TaskContext[]>(`/projects/${projectId}/verification-tasks`, {
        headers: projectHeaders(),
      }),
      apiRequest<SourceItem[]>(`/projects/${projectId}/sources`, {
        headers: projectHeaders(),
      }),
      apiRequest<GitRepository[]>(`/projects/${projectId}/git-repositories`, {
        headers: projectHeaders(),
      }),
    ]);
    if (projectId !== selectedProjectId.value || taskId !== route.params.taskId) return;
    const matchedTask = taskList.find((item) => item.id === taskId);
    if (!matchedTask)
      throw new Error("该核验任务不属于当前项目，或已无权访问。");
    task.value = matchedTask;
    sources.value = sourceList;
    repositories.value = repositoryList;
    if (!gitForm.value.repositoryId && repositoryList.length)
      gitForm.value.repositoryId = repositoryList[0].id;
    if (!matchedTask.formal_snapshot_id && matchedTask.delivery_pull_request) {
      gitForm.value.baseRef =
        matchedTask.delivery_pull_request.baseSha ||
        matchedTask.delivery_pull_request.baseRef ||
        "main";
      gitForm.value.targetRef =
        matchedTask.delivery_pull_request.headSha ||
        matchedTask.delivery_pull_request.headRef ||
        "HEAD";
      gitForm.value.diffMode = "THREE_DOT";
    }
    if (!selectedSourceIds.value.length)
      selectedSourceIds.value = sourceList
        .filter((item) => item.processing_status === "READY")
        .map((item) => item.id);
    await Promise.all([
      loadReport(projectId, matchedTask.cycle_id),
      loadClaims(projectId, matchedTask.id),
    ]);
    if (projectId !== selectedProjectId.value || taskId !== route.params.taskId) return;
    if (claimsConfirmed.value) claimMessage.value = `已确认 ${confirmedClaimCount.value} 条交付内容。`;
    try {
      const run = await apiRequest<AnalysisRun>(
        `/verification-tasks/${taskId}/latest-analysis-run`,
        { headers: projectHeaders() },
      );
      if (projectId !== selectedProjectId.value || taskId !== route.params.taskId) return;
      await loadRun(run);
      if (
        !["SUCCEEDED", "PARTIALLY_COMPLETED", "FAILED", "CANCELLED"].includes(
          run.run_status,
        ) || pendingReportDraft.value
      )
        schedulePoll();
    } catch {
      liveLoadError.value = matchedTask.formal_snapshot_id
        ? "本轮输入已保存，可以继续开始审查。"
        : "";
    }
  } catch (error) {
    liveLoadError.value =
      error instanceof Error ? error.message : "核验任务加载失败";
  }
}

function schedulePoll() {
  stopPolling();
  pollTimer = window.setTimeout(() => {
    void refreshRun();
  }, 3000);
}
async function refreshRun() {
  const runId = liveRun.value?.id;
  const projectId = selectedProjectId.value;
  if (!runId || !projectId) return;
  try {
    const run = await apiRequest<AnalysisRun>(`/analysis-runs/${runId}`, {
      headers: projectHeaders(),
    });
    if (projectId !== selectedProjectId.value || runId !== liveRun.value?.id) return;
    await loadRun(run);
    if (projectId !== selectedProjectId.value || runId !== liveRun.value?.id) return;
    liveLoadError.value = "";
    if (
      !["SUCCEEDED", "PARTIALLY_COMPLETED", "FAILED", "CANCELLED"].includes(
        run.run_status,
      ) || pendingReportDraft.value
    ) {
      if (pendingReportDraft.value) reportMessage.value = "审查已结束，报告草稿正在生成。";
      schedulePoll();
    } else {
      await loadReport(projectId, task.value?.cycle_id ?? null);
      reportMessage.value = report.value
        ? "已生成报告草稿。请补充提交说明后提交审批。"
        : "运行已结束，但当前模板没有生成报告草稿。";
    }
  } catch (error) {
    if (projectId !== selectedProjectId.value || runId !== liveRun.value?.id) return;
    liveLoadError.value =
      error instanceof Error
        ? `运行状态读取失败：${error.message}`
        : "运行状态读取失败。";
    if (activeRun.value || pendingReportDraft.value) schedulePoll();
  }
}

async function startRun() {
  const currentTask = task.value;
  const cycleId = currentTask?.cycle_id;
  const projectId = selectedProjectId.value;
  if (busy.value || !currentTask || !cycleId || !canStartRun.value) return;
  const isCurrent = () => task.value?.cycle_id === cycleId && selectedProjectId.value === projectId;
  busy.value = true;
  startError.value = "";
  liveLoadError.value = "";
  try {
    if (!currentTask.formal_snapshot_id) {
      startPhase.value = "正在保存交付目标…";
      const submittedClaims = claimEdits.value.filter((claim) => claim.selected);
      const claims = submittedClaims.map((claim) => ({ id: claim.id, text: claim.text.trim() }));
      const confirmed = await apiRequest<DeliveryClaim[]>(
        `/projects/${projectId}/verification-tasks/${currentTask.id}/delivery-claims`, {
          method: "PUT", headers: projectHeaders(true), body: JSON.stringify({ claims }),
        },
      );
      if (!isCurrent()) return;
      applyClaims(confirmed);
      // Retain server-issued claim identities and plan provenance on an uncertain retry.
      claimEdits.value.forEach((claim, index) => {
        if (submittedClaims[index]?.planAcceptance) claim.planAcceptance = submittedClaims[index]!.planAcceptance;
      });
      startPhase.value = "正在保存计划验收关联…";
      await planBinding.value?.beforeFreeze(confirmed, submittedClaims);
      if (!isCurrent()) return;
      const gitSelection = JSON.stringify({
        repository_id: gitForm.value.repositoryId,
        base_ref: gitForm.value.baseRef.trim(),
        target_ref: gitForm.value.targetRef.trim(),
        diff_mode: gitForm.value.diffMode,
        include_paths: splitPaths(gitForm.value.includePaths),
        exclude_paths: splitPaths(gitForm.value.excludePaths),
      });
      if (!gitSnapshot.value || frozenGitSelection !== gitSelection) {
        startPhase.value = "正在准备代码变更…";
        const git = await apiRequest<GitSnapshot>(`/cycles/${cycleId}/git-snapshots`, {
          method: "POST", headers: projectHeaders(true), body: gitSelection,
        });
        if (!isCurrent()) return;
        gitSnapshot.value = git;
        frozenGitSelection = gitSelection;
      }
      startPhase.value = "正在保存本轮输入…";
      const snapshot = await apiRequest<{ id: string; snapshot_hash: string }>(
        `/cycles/${cycleId}/input-snapshots/formal`, {
          method: "POST", headers: projectHeaders(true),
          body: JSON.stringify({ source_revision_ids: selectedSourceIds.value,
            git_snapshot_id: gitSnapshot.value.id, external_evidence_ids: [], manual_evidence_ids: [] }),
        },
      );
      if (!isCurrent()) return;
      currentTask.formal_snapshot_id = snapshot.id;
      currentTask.formal_snapshot_hash = snapshot.snapshot_hash;
    }
    startPhase.value = "正在启动审查…";
    // Keep the same request key when retrying an uncertain start response.
    startRequestKey ||= crypto.randomUUID();
    const headers = new Headers(projectHeaders(true));
    headers.set("Idempotency-Key", startRequestKey);
    const run = await apiRequest<AnalysisRun>(
      `/input-snapshots/${currentTask.formal_snapshot_id}/analysis-runs`, { method: "POST", headers },
    );
    if (!isCurrent()) return;
    liveRun.value = run;
    preparationMessage.value = "本轮范围已固定，审查结果将自动更新。";
    await loadRun(run);
    if (isCurrent()) schedulePoll();
  } catch (error) {
    if (!isCurrent()) return;
    const reason = error instanceof Error ? error.message : "请求未完成";
    if (liveRun.value) {
      liveLoadError.value = `审查已启动，结果暂时无法读取：${reason}。正在重新获取。`;
      schedulePoll();
      return;
    }
    // A lost freeze response may still have committed. Recover its identity before retrying.
    if (!currentTask.formal_snapshot_id) {
      try {
        const tasks = await apiRequest<TaskContext[]>(`/projects/${projectId}/verification-tasks`, { headers: projectHeaders() });
        if (!isCurrent()) return;
        const saved = tasks.find((item) => item.id === currentTask.id && item.cycle_id === cycleId);
        if (saved?.formal_snapshot_id) {
          currentTask.formal_snapshot_id = saved.formal_snapshot_id;
          currentTask.formal_snapshot_hash = saved.formal_snapshot_hash;
        }
      } catch { /* Keep the original failure available to the user. */ }
    }
    if (!isCurrent()) return;
    startError.value = reason.includes("指定范围没有可冻结的 Git Diff")
      ? "未找到代码差异，请展开代码范围，检查目标分支和基准分支后重试。"
      : `${startPhase.value.replace(/…$/, "")}失败：${reason.replace(/。$/, "")}。${currentTask.formal_snapshot_id ? "本轮输入已保存，重试会沿用该版本。" : ""}`;
  } finally {
    if (isCurrent()) { busy.value = false; startPhase.value = ""; }
  }
}

async function saveReport(): Promise<boolean> {
  if (!report.value) return false;
  busy.value = true;
  try {
    const updated = await apiRequest<ProjectReport>(
      `/report-versions/${report.value.id}`,
      {
        method: "PUT",
        headers: projectHeaders(true),
        body: JSON.stringify({
          editorial_note: reportNote.value.trim(),
          item_dispositions: {},
          expected_version: report.value.version,
        }),
      },
    );
    report.value = updated;
    if (selectedProjectId.value && task.value?.cycle_id)
      await loadReport(selectedProjectId.value, task.value.cycle_id);
    if (reportPreview.value)
      reportMessage.value = "报告草稿已保存，可在下方回看本版本内容。";
    return true;
  } catch (error) {
    reportMessage.value =
      error instanceof Error ? error.message : "报告草稿保存失败";
    return false;
  } finally {
    busy.value = false;
  }
}

async function submitReport() {
  if (!report.value || report.value.status !== "DRAFT") return;
  if (unresolvedDecisionCount.value) {
    reportMessage.value = `还有 ${unresolvedDecisionCount.value} 条交付结论等待人工裁决。请在右侧“人工裁决”中逐项处理后再提交。`;
    return;
  }
  busy.value = true;
  try {
    if (
      reportNote.value.trim() !== report.value.editorial_note &&
      !(await saveReport())
    )
      return;
    if (!report.value || report.value.status !== "DRAFT") return;
    report.value = await apiRequest<ProjectReport>(
      `/report-versions/${report.value.id}/submit`,
      { method: "POST", headers: projectHeaders(true) },
    );
    if (selectedProjectId.value && task.value?.cycle_id)
      await loadReport(selectedProjectId.value, task.value.cycle_id);
    reportMessage.value =
      "报告已提交审批。不同成员的审核者可在待审批队列作出决定。";
  } catch (error) {
    reportMessage.value =
      error instanceof Error ? error.message : "报告提交失败";
  } finally {
    busy.value = false;
  }
}

function decisionLabel(decision: string) {
  return ({
    CONFIRM_SUPPORT: "确认交付支持",
    CONFIRM_PARTIAL: "确认部分支持",
    CONFIRM_INSUFFICIENT: "确认当前证据不足",
    RETURN_FOR_EVIDENCE: "退回补充证据",
  } as Record<string, string>)[decision] ?? decision;
}

async function decideConclusion(decision: string) {
  const currentRun = liveRun.value;
  const runId = currentRun?.id;
  const resultId = selectedConclusion.value?.id;
  if (!currentRun || !runId || !resultId || resultId.startsWith("pending-")) return;
  if (
    decision === "RETURN_FOR_EVIDENCE" &&
    !decisionNote.value.trim()
  ) {
    decisionMessage.value = "请说明还需要补充哪些证据。";
    return;
  }
  busy.value = true;
  decisionMessage.value = "正在保存人工裁决…";
  try {
    await apiRequest(`/analysis-runs/${runId}/results/${resultId}/human-decisions`, {
      method: "POST",
      headers: projectHeaders(true),
      body: JSON.stringify({ decision, note: decisionNote.value.trim() }),
    });
    decisionNote.value = "";
    decisionMessage.value = `已${decisionLabel(decision)}，原始系统结论和本次人工裁决都会保留。`;
    await loadRun(currentRun);
    if (selectedProjectId.value && task.value?.cycle_id)
      await loadReport(selectedProjectId.value, task.value.cycle_id);
  } catch (error) {
    decisionMessage.value =
      error instanceof Error ? error.message : "人工裁决保存失败";
  } finally {
    busy.value = false;
  }
}

function toolLocatorLabel(locator: Record<string, unknown>): string {
  return String(locator.host ?? locator.toolKey ?? "已冻结的工具配置");
}
function toolImportName(execution: ToolExecution): string {
  return (
    toolImportNames.value[execution.id] ?? `工具结果-${execution.tool_key}`
  );
}
function showDiffFile(path: string) {
  selectedDiffPath.value = path;
  centerView.value = "diff";
}

function selectConclusion(id: string) {
  selectedId.value = id;
  detailPaneOpen.value = true;
  decisionNote.value = "";
  decisionMessage.value = "";
}
async function importToolExecution(execution: ToolExecution) {
  if (!liveRun.value) return;
  const logicalName = toolImportName(execution).trim();
  if (!logicalName) {
    toolImportMessage.value = "请先填写补证名称，再显式导入。";
    return;
  }
  importingToolExecutionId.value = execution.id;
  toolImportMessage.value = "";
  try {
    const imported = await apiRequest<{ manual_evidence_id: string }>(
      `/analysis-runs/${liveRun.value.id}/tool-executions/${execution.id}/import-manual-evidence`,
      {
        method: "POST",
        headers: projectHeaders(true),
        body: JSON.stringify({ logical_name: logicalName }),
      },
    );
    execution.imported_manual_evidence_id = imported.manual_evidence_id;
    toolImportMessage.value =
      "已导入为人工补证；仍需创建新的正式输入快照后才可正式引用。";
  } catch (error) {
    toolImportMessage.value =
      error instanceof Error
        ? `导入失败：${error.message}`
        : "导入失败，请检查当前轮次是否允许补证。";
  } finally {
    importingToolExecutionId.value = "";
  }
}

watch(
  [selectedProjectId, () => route.params.taskId],
  () => {
    void loadWorkspace();
  },
  { immediate: true },
);
onBeforeUnmount(() => { stopPolling(); claimProposalEpoch++; });
</script>

<template>
  <section class="notebook-page" :class="{ 'is-preparing': !liveRun }">
    <header class="notebook-topbar">
      <RouterLink class="notebook-back-button" to="/tasks"
        >代码交付</RouterLink
      >
      <div class="notebook-title">
        <h1>{{ task?.title ?? "核验任务" }}</h1>
        <nav v-if="liveRun" class="review-page-tabs" aria-label="审查工作区">
          <button type="button" :class="{ active: !reportOpen }" :aria-pressed="!reportOpen" @click="reportOpen = false">审查结果</button>
          <button type="button" :class="{ active: reportOpen }" :aria-pressed="reportOpen" :disabled="!report" :title="!report ? '报告尚未生成' : undefined" @click="reportOpen = true">交付报告</button>
        </nav>
      </div>
      <div class="notebook-header-actions">
        <button
          v-if="liveRun"
          class="run-log-trigger"
          type="button"
          aria-haspopup="dialog"
          @click="runLogOpen = true"
        >
          运行记录</button
        >
        <button v-if="liveRun && !reportOpen" type="button" class="run-log-trigger" :aria-expanded="detailPaneOpen" aria-controls="review-detail-pane" @click="detailPaneOpen = !detailPaneOpen">{{ detailPaneOpen ? '收起详情' : '展开详情' }}</button>
        <span class="notebook-status">{{ reviewStatus }}</span>
      </div>
    </header>
    <p v-if="liveLoadError" class="notebook-live-note">{{ liveLoadError }}</p>
    <PlanAcceptanceBinding v-if="task?.cycle_id" :key="`${selectedProjectId}/${task.cycle_id}`" ref="planBinding"
      :project-id="selectedProjectId" :cycle-id="task.cycle_id" :frozen="Boolean(task.formal_snapshot_id)" :disabled="busy"
      @apply="applyPlanAcceptance" @clear="clearPlanAcceptance" />
    <section v-if="task && !liveRun" class="surface preparation-panel review-preparation" :aria-busy="Boolean(startPhase)">
      <div class="review-preparation-heading">
        <div><h2>交付目标</h2></div>
        <span class="status-mark">{{ selectedClaimCount ? `${selectedClaimCount} 个交付目标` : '待提取目标' }}</span>
      </div>
      <div v-if="task.formal_snapshot_id && !confirmedClaimCount" class="legacy-cycle-notice">
        <div><strong>本轮需要重新准备</strong><p>旧版快照缺少交付内容，请新建一轮审查。</p></div>
        <button type="button" :disabled="busy" @click="createNextCycle">新建一轮</button>
      </div>
      <div class="review-preparation-body">
        <section class="review-claims">
          <div class="review-section-heading"><h3>交付内容</h3>
            <div class="claim-actions">
              <button type="button" :disabled="busy || Boolean(task.formal_snapshot_id) || Boolean(confirmedClaimCount)" @click="proposeClaims">{{ claimEdits.length ? '重新提取' : '从 PR 提取' }}</button>
              <button v-if="activeClaimProposal" type="button" :disabled="claimCancelling" @click="cancelClaimProposal">{{ claimCancelling ? '正在取消…' : '取消提取' }}</button>
              <button type="button" :disabled="busy || Boolean(task.formal_snapshot_id) || claimEdits.length >= 12" @click="addManualClaim">补充内容</button>
            </div>
          </div>
          <p class="claim-feedback" :class="{ confirmed: claimsConfirmed }" role="status">{{ claimMessage }}</p>
          <div v-for="(claim, index) in claimEdits" :key="claim.id ?? `manual-${index}`" class="claim-edit-row">
            <label class="claim-select"><input v-model="claim.selected" type="checkbox" :disabled="busy || Boolean(task.formal_snapshot_id)" @change="claim.status = 'CANDIDATE'" /><span>纳入本轮</span></label>
            <textarea v-model="claim.text" :aria-label="`交付内容 ${index + 1}`" :disabled="busy || Boolean(task.formal_snapshot_id)" placeholder="描述一个需要核验的功能结果" @input="claim.status = 'CANDIDATE'" />
            <small v-if="claim.planAcceptance">计划验收：{{ claim.planAcceptance.issueKey }} / {{ claim.planAcceptance.acceptanceKey }}</small>
            <details v-if="claim.origin === 'MODEL' && claim.rationale" class="claim-rationale ui-disclosure"><summary>提取依据</summary><p>{{ claim.rationale }}</p></details>
            <button type="button" :aria-label="`删除交付内容 ${index + 1}`" :disabled="busy || Boolean(task.formal_snapshot_id)" @click="removeClaim(index)">删除</button>
          </div>
          <div v-if="!claimEdits.length" class="review-claims-empty"><strong>先确定本次交付的功能</strong><p>提取后可编辑，也可手动添加。</p></div>
        </section>
        <details class="review-settings ui-disclosure" :open="!gitForm.repositoryId">
          <summary><span>代码范围</span><small v-if="task.delivery_pull_request">PR #{{ task.delivery_pull_request.number }} · {{ task.delivery_pull_request.headRef }} → {{ task.delivery_pull_request.baseRef }}</small><small v-else>选择仓库与分支</small></summary>
          <div class="review-settings-content">
            <label>仓库<select v-model="gitForm.repositoryId" :disabled="busy || Boolean(task.formal_snapshot_id)"><option value="" disabled>选择已接入仓库</option><option v-for="repository in repositories" :key="repository.id" :value="repository.id">{{ repository.display_url }}</option></select></label>
            <div class="preparation-fields"><label>基准分支 / 提交<input v-model="gitForm.baseRef" :disabled="busy || Boolean(task.formal_snapshot_id)" /></label><label>目标分支 / 提交<input v-model="gitForm.targetRef" :disabled="busy || Boolean(task.formal_snapshot_id)" /></label></div>
            <label>比较方式<select v-model="gitForm.diffMode" :disabled="busy || Boolean(task.formal_snapshot_id)"><option value="THREE_DOT">从共同祖先比较（PR）</option><option value="TWO_DOT">直接比较两个提交</option></select></label>
            <label>包含路径（可选）<input v-model="gitForm.includePaths" :disabled="busy || Boolean(task.formal_snapshot_id)" placeholder="例如 src/, backend/，逗号分隔" /></label>
          </div>
        </details>
        <details class="review-settings ui-disclosure">
          <summary><span>关联资料 <em>可选</em></span><small>{{ selectedSourceIds.length }} 份已选择</small></summary>
          <div class="review-settings-content">
            <label v-for="source in readySources" :key="source.id" class="check-line"><input v-model="selectedSourceIds" type="checkbox" :value="source.id" :disabled="busy || Boolean(task.formal_snapshot_id)" /><span>{{ source.logical_name }}</span><small>v{{ source.revision_no }}</small></label>
            <p v-if="!readySources.length" class="empty-row">暂无可用资料，可直接审查本次代码变更。</p>
          </div>
        </details>
        <details v-if="task.formal_snapshot_hash" class="review-settings ui-disclosure">
          <summary><span>本轮输入已保存</span><small>查看版本详情</small></summary>
          <div class="review-settings-content"><p>本轮已锁定，修改请新建一轮。</p><code class="review-snapshot-hash">{{ task.formal_snapshot_hash }}</code><button type="button" :disabled="busy" @click="createNextCycle">调整范围，开启新一轮</button></div>
        </details>
      </div>
      <footer class="review-start-footer">
        <div aria-live="polite"><strong>{{ startPhase || (startError ? '审查未启动' : task.formal_snapshot_id ? '本轮输入已就绪' : canStartRun ? '可以开始审查了' : !selectedClaimCount ? '请提取或补充交付目标' : '请补全目标与代码范围') }}</strong><p>{{ task.formal_snapshot_id ? '继续审查将沿用已保存的输入版本。' : '开始后，本轮交付内容和资料版本将固定。' }}</p></div>
        <button class="primary-button" type="button" :disabled="busy || !canStartRun" @click="startRun">{{ startPhase ? '正在准备…' : startError ? '重试审查' : '开始审查' }}</button>
        <p v-if="startError" class="review-start-error" role="alert">{{ startError }}</p>
        <p v-else-if="preparationMessage" class="review-preparation-note" role="status">{{ preparationMessage }}</p>
      </footer>
    </section>
    <details
      v-if="liveRun && !reportOpen && (toolExecutions.length || toolExecutionError)"
      class="tool-execution-strip ui-disclosure"
      aria-label="临时工具结果"
    >
      <summary>补充分析材料 · {{ toolExecutions.length }} 项</summary>
      <header>
        <div>
          <h2>临时工具结果</h2>
          <p>工具查询结果</p>
        </div>
        <span>需显式导入</span>
      </header>
      <p v-if="toolExecutionError" class="tool-execution-message error">
        {{ toolExecutionError }}
      </p>
      <div
        v-for="execution in toolExecutions"
        :key="execution.id"
        class="tool-execution-row"
      >
        <div class="tool-execution-copy">
          <strong
            >{{ execution.capability_key }} / {{ execution.tool_key }}</strong
          ><small
            >{{ toolLocatorLabel(execution.locator) }} ·
            {{ execution.content_hash.slice(0, 18) }}</small
          >
          <p>{{ execution.excerpt_safe }}</p>
        </div>
        <div class="tool-execution-action">
          <template v-if="execution.imported_manual_evidence_id"
            ><span class="tool-imported">已导入补证</span
            ><small>{{
              execution.imported_manual_evidence_id
            }}</small></template
          ><template v-else
            ><input
              :value="toolImportName(execution)"
              aria-label="补证名称"
              @input="
                toolImportNames[execution.id] = (
                  $event.target as HTMLInputElement
                ).value
              "
            /><button
              type="button"
              :disabled="importingToolExecutionId === execution.id"
              @click="importToolExecution(execution)"
            >
              {{
                importingToolExecutionId === execution.id
                  ? "导入中…"
                  : "显式导入为补证"
              }}
            </button></template
          >
        </div>
      </div>
      <p v-if="toolImportMessage" class="tool-execution-message">
        {{ toolImportMessage }}
      </p>
    </details>
    <main v-if="liveRun" v-show="!reportOpen" class="notebook-grid" :class="{ 'detail-collapsed': !detailPaneOpen }">
      <SourceEvidencePane
        :evidence="liveEvidence"
        :snapshot-label="liveRun?.snapshot_id ?? task?.formal_snapshot_hash"
        :live="Boolean(liveRun)"
        :git-diff="liveGitDiff"
        :code-review="liveCodeReview"
        :run-status="liveRun?.run_status"
        :selected-file-path="selectedDiffFile?.path"
        @select-file="showDiffFile"
        @show-run-log="runLogOpen = true"
      /><VerificationPane
        :conclusions="displayedConclusions"
        :selected-id="selectedId"
        :live="Boolean(liveRun)"
        :view="centerView"
        :selected-file="selectedDiffFile"
        @select="selectConclusion"
        @change-view="centerView = $event"
      /><ReviewDetailPane
        v-show="detailPaneOpen"
        id="review-detail-pane"
        :conclusion="selectedConclusion"
        :evidence="liveEvidence"
        :can-decide="Boolean(selectedConclusion?.allowedHumanDecisions?.length && !selectedConclusion?.humanDecision)"
        ><template #decision
          ><div class="human-decision-panel">
            <div class="surface-heading">
              <div>
                <h2>复核意见</h2>
              </div>
            </div>
            <template v-if="selectedConclusion?.humanDecision">
              <p class="decision-state">已完成：{{ decisionLabel(selectedConclusion.humanDecision.decision) }}</p>
              <p v-if="selectedConclusion.humanDecision.note" class="quiet-note">{{ selectedConclusion.humanDecision.note }}</p>
              <small>裁决时间：{{ selectedConclusion.humanDecision.createdAt ? formatDate(selectedConclusion.humanDecision.createdAt) : '—' }}</small>
            </template>
            <template v-else-if="selectedConclusion?.allowedHumanDecisions?.length">
              <label>处理说明（退回补证时必填）<textarea v-model="decisionNote" :disabled="busy" placeholder="说明你发现的问题或需要补充的证据。" /></label>
              <div class="action-buttons decision-actions">
                <button v-for="decision in selectedConclusion.allowedHumanDecisions" :key="decision" type="button" :class="{ 'primary-button': decision === 'CONFIRM_SUPPORT' }" :disabled="busy" @click="decideConclusion(decision)">{{ decisionLabel(decision) }}</button>
              </div>
            </template>
            <p v-else class="quiet-note">暂无待复核结论。</p>
            <p v-if="decisionMessage" class="claim-feedback">{{ decisionMessage }}</p>
          </div></template>
      </ReviewDetailPane>
    </main>
    <section v-if="report && reportOpen" class="review-report-workspace" aria-label="交付报告">
          <div class="report-submit-panel">
            <div class="surface-heading">
              <div>
                <h2>交付报告</h2>
              </div>
              <span class="status-mark attention">{{ reportStatusLabel(report.status) }}</span>
            </div>
            <p class="association-note">{{ reportMessage }}</p>
            <section v-if="reportPreview" class="report-preview" aria-label="已保存的交付报告内容">
              <div class="report-preview-meta">
                <strong>已保存的报告内容</strong>
                <span>v{{ reportPreview.version }} · 输入快照 {{ reportPreview.snapshot_hash.slice(0, 12) }}</span>
              </div>
              <article v-for="item in reportPreview.items" :key="item.id" class="report-preview-item">
                <div class="report-preview-item-heading">
                  <strong>{{ item.claimText }}</strong>
                  <span class="status-mark">{{ reportConclusionStatus(item) }}</span>
                </div>
                <p v-if="item.result.reason">{{ item.result.reason }}</p>
                <p v-if="item.result.humanDecision" class="report-human-decision">
                  人工裁决：{{ decisionLabel(item.result.humanDecision.decision) }}
                  <template v-if="item.result.humanDecision.note"> · {{ item.result.humanDecision.note }}</template>
                  <template v-if="item.result.humanDecision.createdAt"> · {{ formatDate(item.result.humanDecision.createdAt) }}</template>
                </p>
                <details v-if="item.citations.length" class="report-citations ui-disclosure">
                  <summary>冻结引用（{{ item.citations.length }}）</summary>
                  <div v-for="citation in item.citations" :key="citation.id" class="report-citation">
                    <span>{{ citation.sourceType }}</span><p>{{ citation.excerpt }}</p>
                  </div>
                </details>
              </article>
              <p v-if="!reportPreview.items.length" class="quiet-note">该报告版本没有可展示的交付主张。</p>
              <p v-if="reportPreview.editorial_note" class="report-editorial-note"><strong>提交说明</strong>{{ reportPreview.editorial_note }}</p>
            </section>
            <p v-else class="quiet-note">正在读取报告…</p>
            <template v-if="report.status === 'DRAFT'"
              ><p v-if="unresolvedDecisionCount" class="report-gate-note">还有 {{ unresolvedDecisionCount }} 条结论需要人工复核。<button type="button" @click="openPendingConclusion">前往处理</button></p><label
                >提交说明<textarea
                  v-model="reportNote"
                  :disabled="busy"
                  placeholder="说明本次核验范围、证据限制和需要人工确认的事项。"
                />
              </label>
              <div class="action-buttons">
                <button type="button" :disabled="busy" @click="saveReport">
                  保存草稿</button
                ><button
                  class="primary-button"
                  type="button"
                  :disabled="busy || Boolean(unresolvedDecisionCount)"
                  @click="submitReport"
                >
                  提交审批
                </button>
              </div></template
            >
            <p v-else class="empty-row">
              当前报告状态：{{ reportStatusLabel(report.status) }}。{{
                report.status === "SUBMITTED"
                  ? "请由不同成员的审核者进入待审批队列处理。"
                  : report.status === "APPROVED"
                    ? "管理员可在审批详情中固化正式记录。"
                    : "该报告版本仅供回放。"
              }}
            </p>
          </div>
    </section>
    <div
      v-if="runLogOpen && liveRun"
      class="run-log-backdrop"
      role="presentation"
      @click.self="runLogOpen = false"
    >
      <section
        class="run-log-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-log-title"
      >
        <header>
          <div>
            <h2 id="run-log-title">运行记录</h2>
            <p>
              {{
                activeRun
                  ? "正在执行，系统每 3 秒自动更新。"
                  : "本次执行已结束，可在此回看处理过程。"
              }}
            </p>
          </div>
          <button
            type="button"
            aria-label="关闭运行记录"
            @click="runLogOpen = false"
          >
            关闭
          </button>
        </header>
        <div class="run-log-body">
          <div v-if="activeRun" class="run-events-refresh">
            <span>正在自动更新。</span
            ><button type="button" :disabled="busy" @click="refreshRun">
              立即刷新
            </button>
          </div>
          <p
            v-for="event in liveEvents.slice(-8)"
            :key="event.id"
            class="run-event"
          >
            <strong>{{ runStepLabel(event.nodeId) }}</strong
            ><span
              >{{ runStepStatus(event.status)
              }}<template v-if="event.details?.errorCode">
                · {{ event.details.errorCode }}</template
              ></span
            ><time>{{ formatDate(event.createdAt) }}</time>
          </p>
          <p v-if="!liveEvents.length" class="empty-row">
            暂时没有可展示的运行事件。
          </p>
          <details v-if="liveOrchestration" class="review-runtime-details ui-disclosure">
            <summary>技术详情与本轮版本</summary>
            <dl class="run-details"><div><dt>输入版本</dt><dd>{{ liveRun.snapshot_id }}</dd></div><div><dt>编排模板</dt><dd>{{ liveOrchestration.template.name }} · v{{ liveOrchestration.template.version }}</dd></div></dl>
            <ol class="run-orchestration-list"><li v-for="node in [...liveOrchestration.nodes].sort((a, b) => a.displayOrder - b.displayOrder)" :key="node.capabilityKey"><span>{{ node.displayOrder }}</span><div><strong>{{ node.capabilityName }}</strong><small>v{{ node.capabilityVersion }}<template v-if="node.tools.length"> · {{ node.tools.map((tool) => tool.key).join('、') }}</template></small></div><em v-if="node.locked">系统锁定</em></li></ol>
          </details>
        </div>
      </section>
    </div>
  </section>
</template>
