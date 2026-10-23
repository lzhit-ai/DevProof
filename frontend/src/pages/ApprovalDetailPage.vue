<script setup lang="ts">
import { ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import {
  apiRequest,
  projectHeaders,
  selectedProject,
  selectedProjectId,
} from "../features/projects/project-context";

interface ProjectReport {
  id: string;
  task_title: string;
  requirement_key: string;
  sequence_no: number;
  status: string;
  snapshot_hash: string;
  content_hash: string;
  editorial_note: string;
  submitted_by_name: string | null;
  submitted_at: string | null;
  latest_approval_action: string | null;
  latest_approval_reason: string | null;
  latest_approval_at: string | null;
}
interface ReportContent extends ProjectReport {
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
    citations: Array<{
      id: string;
      sourceType: string;
      excerpt: string;
    }>;
  }>;
}

const route = useRoute();
const report = ref<ProjectReport | null>(null);
const reportContent = ref<ReportContent | null>(null);
const reason = ref("");
const busy = ref(false);
const message = ref("正在读取待审批的冻结报告内容。");

function formatDate(value: string | null) {
  return value
    ? new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "—";
}
function statusLabel(value: string) {
  return (
    {
      SUBMITTED: "待审批",
      APPROVED: "已批准",
      PUBLISHED: "已固化",
      REJECTED: "已驳回",
      CHANGES_REQUESTED: "已要求补证",
      DRAFT: "草稿",
    } as Record<string, string>
  )[value] ?? value;
}
function conclusionStatus(item: ReportContent["items"][number]) {
  const decision = item.result.humanDecision?.decision;
  if (decision === "CONFIRM_SUPPORT") return "已确认";
  if (decision === "CONFIRM_PARTIAL") return "部分支持";
  if (
    decision === "CONFIRM_INSUFFICIENT" ||
    decision === "RETURN_FOR_EVIDENCE"
  )
    return "证据不足";
  return (
    {
      SUPPORTED: "代码证据支持",
      PARTIALLY_SUPPORTED: "部分支持",
      NOT_PROVEN: "当前证据未证明",
      NOT_ANALYZED: "未完成分析",
      CONFLICTING: "存在冲突",
    } as Record<string, string>
  )[item.result.status] ?? item.result.status;
}
function decisionLabel(decision: string) {
  return (
    {
      CONFIRM_SUPPORT: "确认交付支持",
      CONFIRM_PARTIAL: "确认部分支持",
      CONFIRM_INSUFFICIENT: "确认当前证据不足",
      RETURN_FOR_EVIDENCE: "退回补充证据",
    } as Record<string, string>
  )[decision] ?? decision;
}

async function load() {
  const projectId = selectedProjectId.value;
  const reportId = String(route.params.approvalId ?? "");
  if (!projectId || !reportId) {
    report.value = null;
    reportContent.value = null;
    return;
  }
  busy.value = true;
  try {
    report.value = await apiRequest<ProjectReport>(
      `/projects/${projectId}/report-versions/${reportId}`,
      { headers: projectHeaders() },
    );
    try {
      reportContent.value = await apiRequest<ReportContent>(
        `/projects/${projectId}/report-versions/${reportId}/content`,
        { headers: projectHeaders() },
      );
      message.value = "请基于下方已冻结的报告内容和引用作出审批决定。";
    } catch (error) {
      reportContent.value = null;
      message.value =
        error instanceof Error
          ? `无法读取该报告的冻结内容，暂不能审批：${error.message}`
          : "无法读取该报告的冻结内容，暂不能审批。";
    }
  } catch (error) {
    report.value = null;
    reportContent.value = null;
    message.value = error instanceof Error ? error.message : "审批详情加载失败";
  } finally {
    busy.value = false;
  }
}

async function act(action: "approve" | "request-changes" | "reject") {
  if (!report.value || !reportContent.value || !reason.value.trim()) {
    message.value = !reportContent.value
      ? "报告内容尚未加载，不能在只看到哈希的情况下审批。"
      : "请先填写审批依据。";
    return;
  }
  busy.value = true;
  try {
    await apiRequest(`/report-versions/${report.value.id}/${action}`, {
      method: "POST",
      headers: projectHeaders(true),
      body: JSON.stringify({ reason: reason.value.trim() }),
    });
    reason.value = "";
    message.value = "审批动作已记录，并绑定本页所展示的报告版本与输入快照。";
    await load();
  } catch (error) {
    message.value = error instanceof Error ? error.message : "审批动作失败";
  } finally {
    busy.value = false;
  }
}

async function publishRecord() {
  if (!report.value || report.value.status !== "APPROVED") return;
  busy.value = true;
  try {
    const record = await apiRequest<{ recordNo: string }>(
      `/report-versions/${report.value.id}/publish`,
      { method: "POST", headers: projectHeaders(true) },
    );
    message.value = `已固化正式记录 ${record.recordNo}。该轮次和报告版本现为不可写历史。`;
    await load();
  } catch (error) {
    message.value =
      error instanceof Error ? error.message : "正式记录固化失败";
  } finally {
    busy.value = false;
  }
}

watch(
  [selectedProjectId, () => route.params.approvalId],
  () => {
    void load();
  },
  { immediate: true },
);
</script>

<template>
  <section class="page page-detail approval-page">
    <RouterLink class="back-link" to="/approvals">返回待审批队列</RouterLink>
    <header class="page-heading detail-heading">
      <div>
        <h1>审批报告</h1>
        <p v-if="report">{{ report.task_title }} · 报告版本 v{{ report.sequence_no }}</p>
        <p v-else>读取当前项目中的报告版本。</p>
      </div>
      <span v-if="report" class="status-mark attention">{{ statusLabel(report.status) }}</span>
    </header>
    <p class="page-context-note">{{ message }}</p>

    <section v-if="report && selectedProject" class="surface formal-document approval-document">
      <div class="record-meta">
        <span>需求标识：{{ report.requirement_key }}</span>
        <span>提交人：{{ report.submitted_by_name || "—" }}</span>
        <span>提交时间：{{ formatDate(report.submitted_at) }}</span>
      </div>

      <section v-if="reportContent" class="document-section approval-report-body">
        <h2>本次交付结论</h2>

        <article v-for="item in reportContent.items" :key="item.id" class="approval-claim">
          <div class="approval-claim-heading">
            <strong>{{ item.claimText }}</strong>
            <span class="status-mark">{{ conclusionStatus(item) }}</span>
          </div>
          <p v-if="item.result.reason">{{ item.result.reason }}</p>
          <p v-if="item.result.humanDecision" class="approval-human-decision">
            人工裁决：{{ decisionLabel(item.result.humanDecision.decision) }}
            <template v-if="item.result.humanDecision.note"> · {{ item.result.humanDecision.note }}</template>
            <template v-if="item.result.humanDecision.createdAt"> · {{ formatDate(item.result.humanDecision.createdAt) }}</template>
          </p>
          <details v-if="item.citations.length" class="approval-citations ui-disclosure">
            <summary>查看冻结引用（{{ item.citations.length }}）</summary>
            <div v-for="citation in item.citations" :key="citation.id" class="approval-citation">
              <span>{{ citation.sourceType }}</span>
              <p>{{ citation.excerpt }}</p>
            </div>
          </details>
        </article>
        <p v-if="!reportContent.items.length" class="quiet-note">该报告版本没有可供审批的交付主张。</p>
        <p v-if="reportContent.editorial_note" class="approval-editorial-note"><strong>提交说明</strong>{{ reportContent.editorial_note }}</p>
      </section>

      <div class="document-section approval-decision">
        <h2>审批决定</h2>
        <label class="form-label" for="approval-comment">说明你依据哪些已冻结事实作出决定</label>
        <textarea id="approval-comment" v-model="reason" :disabled="busy || report.status !== 'SUBMITTED' || !reportContent" placeholder="例如：两项交付主张均已确认，冻结引用覆盖实现范围，接受本次交付。"></textarea>
        <p v-if="report.latest_approval_reason" class="history-note">最近审批说明：{{ report.latest_approval_reason }}</p>
      </div>

      <details class="approval-integrity ui-disclosure">
        <summary>版本与校验</summary>
        <dl class="run-details">
          <div><dt>报告内容哈希</dt><dd>{{ report.content_hash }}</dd></div>
          <div><dt>输入快照哈希</dt><dd>{{ report.snapshot_hash }}</dd></div>
          <div><dt>上一审批动作</dt><dd>{{ report.latest_approval_action || "尚无" }}</dd></div>
        </dl>
      </details>

      <div class="document-actions">
        <div>

          <p>补证将创建新草稿。</p>
        </div>
        <div class="action-buttons">
          <button type="button" :disabled="busy || report.status !== 'SUBMITTED' || !reportContent" @click="act('request-changes')">要求补证</button>
          <button type="button" :disabled="busy || report.status !== 'SUBMITTED' || !reportContent" @click="act('reject')">驳回</button>
          <button class="primary-button" type="button" :disabled="busy || report.status !== 'SUBMITTED' || !reportContent" @click="act('approve')">批准</button>
          <button v-if="report.status === 'APPROVED'" class="primary-button" type="button" :disabled="busy" @click="publishRecord">管理员固化正式记录</button>
        </div>
      </div>
    </section>
  </section>
</template>
