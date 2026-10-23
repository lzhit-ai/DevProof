<script setup lang="ts">
import { computed } from "vue";
import type { EvidenceReference, VerificationConclusion } from "../../types/workbench";

const props = defineProps<{
  conclusion?: VerificationConclusion;
  evidence: EvidenceReference[];
  canDecide?: boolean;
}>();
const relatedEvidence = computed(() =>
  props.evidence.filter((item) => props.conclusion?.evidenceIds.includes(item.id)),
);
const readableReason = computed(() => {
  const reason = props.conclusion?.summary ?? "";
  return ({
    "模型分析结果已绑定到当前冻结 Diff Hunk；必要代码上下文仅用于解释，不作为独立证据": "AI 已找到支持目标的具体代码变更。下方列出对应位置和分析理由。",
    "已发现冻结 Git 范围内的直接代码标识符命中，但尚未形成足以证明完整目标的语义证据": "代码中出现了相关名称，但仅凭这些匹配，还不能证明功能已经完整实现。",
    "已关联人工补证；该补证不能单独证明本次冻结 PR 的代码交付范围": "已找到人工补充的材料，还需要本次代码变更中的直接证据。",
    "存在与冻结代码证据关联的反驳结论，需要核对业务语义": "部分代码证据与交付目标不一致，需要核对具体实现和预期行为。",
    "冻结代码输入或必要模型分析不可用，当前不能完成该目标的核验": "代码材料或 AI 分析未能完成，本项暂时没有有效结论。",
    "已完成当前冻结代码范围分析，但没有足够的直接证据证明该交付目标": "本轮分析未找到足够的代码证据，无法确认这个目标已经实现。",
  } as Record<string, string>)[reason] ?? reason;
});
const nextStep = computed(() => {
  const item = props.conclusion;
  if (!item) return "选择一条交付目标，查看审查依据。";
  if (item.needsHumanDecision) return item.status === "存在冲突"
    ? "证据之间存在冲突，请核对上方依据并记录处理意见。"
    : "本项仍有需要人工判断的内容，请核对上方依据并记录处理意见。";
  if (item.status === "自动通过" || item.status === "已确认")
    return "本项无需逐条确认，可以继续查看其他结论或整份交付报告。";
  if (item.status === "部分支持") return "已找到部分关联证据，但尚不足以证明整个目标。补齐缺失实现或验证材料后，再发起新一轮审查。";
  if (item.status === "证据不足") return "现有证据无法证明目标已完成。补充相关代码或验证材料后，再发起新一轮审查。";
  if (item.status === "存在冲突") return "查看冲突依据，修正实现或补充说明后，再发起新一轮审查。";
  return "尚未得到有效结论。审查中会自动更新；若运行已结束，请查看运行记录中的失败或范围限制。";
});
</script>

<template>
  <aside class="notebook-pane notebook-detail">
    <header class="notebook-pane-header">
      <h2>结论详情</h2>
    </header>
    <template v-if="conclusion">
      <section class="review-verdict">
        <span :class="['conclusion-status', conclusion.status]">{{ conclusion.status }}</span>
        <h3>{{ conclusion.requirement }}</h3>
        <span v-if="conclusion.risk" class="review-risk-label">风险等级 {{ conclusion.risk }}</span>
      </section>
      <section class="review-detail-section">
        <h3>判断依据</h3>
        <p class="review-reason">{{ readableReason }}</p>
        <div class="review-evidence-list">
          <article v-for="item in relatedEvidence" :key="item.id" class="review-evidence">
            <div class="review-evidence-heading"><span class="source-kind">{{ item.kind }}</span><span>{{ item.locator }}</span></div>
            <p v-for="(assessment, index) in (conclusion.evidenceAssessments ?? []).filter((entry) => entry.evidenceId === item.id)" :key="index" class="review-assessment">
              <strong>{{ assessment.relation === 'CONTRADICTS' ? '冲突依据' : assessment.relation === 'SUPPORTS' ? '支持依据' : '关联依据' }} · {{ assessment.producedBy === 'MODEL' ? 'AI 分析' : assessment.producedBy === 'HUMAN' ? '人工补充' : '规则匹配' }}</strong>
              {{ assessment.reason }}
            </p>
            <details class="ui-disclosure"><summary>原文片段</summary><pre>{{ item.excerpt }}</pre></details>
          </article>
        </div>
        <p v-if="!relatedEvidence.length" class="review-muted">尚无可定位的引用证据。</p>
      </section>
      <section v-if="conclusion.status !== '自动通过' && conclusion.status !== '已确认'" class="review-detail-section review-next-step" aria-live="polite">
        <h3>{{ conclusion.needsHumanDecision ? '需要你复核' : '下一步' }}</h3>
        <p>{{ nextStep }}</p>
      </section>
      <section v-if="conclusion.needsHumanDecision" class="review-detail-section"><slot name="decision" /></section>
      <details v-else-if="canDecide || conclusion.humanDecision" :key="conclusion.id" class="review-override ui-disclosure">
        <summary>{{ conclusion.humanDecision ? '人工处理记录' : '人工复核' }}</summary>
        <slot name="decision" />
      </details>
    </template>
    <p v-else class="notebook-empty">本轮尚未生成审查结论。</p>
  </aside>
</template>
