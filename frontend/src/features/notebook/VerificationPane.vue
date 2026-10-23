<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { VerificationConclusion } from "../../types/workbench";

type GitFile = {
  path: string;
  old_path?: string | null;
  edit_type: string;
  additions: number;
  deletions: number;
  binary: boolean;
  hunks: Array<{ header: string; payload: string }>;
};
type DiffLine = {
  oldNo: string;
  newNo: string;
  kind: "added" | "deleted" | "context";
  content: string;
};

const props = defineProps<{
  conclusions: VerificationConclusion[];
  selectedId: string;
  live?: boolean;
  view: "conclusions" | "diff";
  selectedFile?: GitFile | null;
}>();
const emit = defineEmits<{
  select: [id: string];
  changeView: [view: "conclusions" | "diff"];
}>();

const summary = computed(() => ({
  confirmed: props.conclusions.filter((item) => ["自动通过", "代码证据支持", "已确认"].includes(item.status) && !item.needsHumanDecision)
    .length,
  partial: props.conclusions.filter((item) => item.status === "部分支持")
    .length,
  insufficient: props.conclusions.filter((item) => item.status === "证据不足")
    .length,
  conflicting: props.conclusions.filter((item) => item.status === "存在冲突")
    .length,
  pending: props.conclusions.filter((item) => item.needsHumanDecision).length,
  unanalyzed: props.conclusions.filter((item) => item.status === "未完成分析").length,
}));

const filter = ref<"all" | "attention" | "passed">("all");
const isPassed = (item: VerificationConclusion) =>
  ["自动通过", "代码证据支持", "已确认"].includes(item.status) && !item.needsHumanDecision;
const visibleConclusions = computed(() => props.conclusions.filter((item) =>
  filter.value === "all" || (filter.value === "passed" ? isPassed(item) : !isPassed(item)),
));
watch(filter, () => {
  if (!visibleConclusions.value.some((item) => item.id === props.selectedId) && visibleConclusions.value[0])
    emit("select", visibleConclusions.value[0].id);
});
watch(() => props.selectedId, () => {
  if (!visibleConclusions.value.some((item) => item.id === props.selectedId)) filter.value = "all";
});

function diffLines(header: string, payload: string): DiffLine[] {
  const match = /@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@/.exec(header);
  let oldLine = Number(match?.[1] ?? 1);
  let newLine = Number(match?.[2] ?? 1);
  return payload.split("\n").map((line) => {
    if (line.startsWith("+") && !line.startsWith("+++"))
      return {
        oldNo: "",
        newNo: String(newLine++),
        kind: "added" as const,
        content: line.slice(1),
      };
    if (line.startsWith("-") && !line.startsWith("---"))
      return {
        oldNo: String(oldLine++),
        newNo: "",
        kind: "deleted" as const,
        content: line.slice(1),
      };
    return {
      oldNo: String(oldLine++),
      newNo: String(newLine++),
      kind: "context" as const,
      content: line.startsWith(" ") ? line.slice(1) : line,
    };
  });
}
</script>

<template>
  <section class="notebook-pane notebook-verification">
    <header class="notebook-pane-header">
      <div>
        <h2>{{ view === "conclusions" ? "审查结论" : "代码变更" }}</h2>
      </div>
    </header>
    <nav class="workspace-tabs" aria-label="审查内容">
      <button
        type="button"
        :class="{ active: view === 'conclusions' }"
        @click="emit('changeView', 'conclusions')"
      >
        交付结论</button
      ><button
        type="button"
        :class="{ active: view === 'diff' }"
        @click="emit('changeView', 'diff')"
      >
        代码变更
      </button>
    </nav>
    <template v-if="view === 'conclusions'">
      <div class="review-result-filters" role="group" aria-label="筛选审查结论">
        <button type="button" :aria-pressed="filter === 'all'" @click="filter = 'all'">全部 {{ conclusions.length }}</button>
        <button type="button" :disabled="conclusions.length === summary.confirmed" :aria-pressed="filter === 'attention'" @click="filter = 'attention'">待解决 {{ conclusions.length - summary.confirmed }}</button>
        <button type="button" :disabled="!summary.confirmed" :aria-pressed="filter === 'passed'" @click="filter = 'passed'">已通过 {{ summary.confirmed }}</button>
      </div>
      <ol class="conclusion-list">
        <li
          v-for="item in visibleConclusions"
          :key="item.id"
          :class="{ selected: selectedId === item.id }"
        >
          <button type="button" :aria-current="selectedId === item.id ? 'true' : undefined" @click="emit('select', item.id)">
            <div class="conclusion-top">
              <strong>{{ item.requirement }}</strong
              ><span :class="['conclusion-status', item.status]">{{
                item.status
              }}</span>
            </div>
            <small
              ><span v-if="item.risk" :class="['risk-chip', item.risk]">{{
                item.risk
              }}</span
              >{{
                item.humanDecision
                  ? "已人工复核"
                  : item.needsHumanDecision
                  ? "待人工复核"
                  : `${item.evidenceIds.length} 条依据`
              }}</small
            >
          </button>
        </li>
      </ol><p v-if="!visibleConclusions.length" class="notebook-empty">该分类暂无结论，可切换到其他分类查看。</p></template
    >
    <section v-else-if="selectedFile" class="center-diff-view">
      <header>
        <div>
          <strong>{{ selectedFile.path }}</strong
          ><small
            >{{ selectedFile.edit_type }} · +{{ selectedFile.additions }} / -{{
              selectedFile.deletions
            }}</small
          >
        </div>
        <span>{{ selectedFile.hunks.length }} 个片段</span>
      </header>
      <p v-if="selectedFile.binary" class="quiet-note">
        二进制文件，暂不支持预览。
      </p>
      <p v-else-if="!selectedFile.hunks.length" class="quiet-note">
        该文件没有可展示的文本变更片段。
      </p>
      <div
        v-else
        v-for="(hunk, index) in selectedFile.hunks"
        :key="`${selectedFile.path}-${index}`"
        class="center-diff-editor"
      >
        <header>
          <span>片段 {{ index + 1 }}</span
          ><code>{{ hunk.header }}</code>
        </header>
        <div
          v-for="(line, lineIndex) in diffLines(hunk.header, hunk.payload)"
          :key="lineIndex"
          :class="['center-diff-line', line.kind]"
        >
          <span>{{ line.oldNo }}</span
          ><span>{{ line.newNo }}</span
          ><i>{{
            line.kind === "added" ? "+" : line.kind === "deleted" ? "−" : " "
          }}</i
          ><code>{{ line.content }}</code>
        </div>
      </div>
    </section>
    <p v-else class="notebook-empty">
      选择文件查看 Diff。
    </p>
  </section>
</template>
