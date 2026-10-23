# 标准交付核验：内置审查与可解释性设计

**状态：已确认设计，待用户审阅文档后制定实施计划**  
**日期：2026-08-25**

## 1. 目标与边界

将当前交付核验从“冻结资料与 Diff 后生成代码 Finding”收敛为唯一的**标准核验**模式：内置、不可由普通用户编辑、可完整回放。

标准核验用于回答“已确认的验收目标是否在指定冻结 Diff 范围内获得资料与代码证据支持”，不回答项目整体是否完成、是否安全，也不替代 CI、构建、测试或人工代码评审。

本次不做：快速/深度模式选择、面向用户的 Agent 画布、任意 Prompt/节点编排、仓库 checkout 或执行、Git/GitHub 写操作、模型降级或 Fake 结论。

## 2. 固定流程

```text
正式输入快照
  → 读取冻结资料 / Claim / Diff 制品
  → 产生并校验 GIT_DIFF_HUNK 证据
  → DeepSeek 代码 Finding 草稿
  → Finding 反证复核
  → 覆盖范围汇总
  → 既有确定性链接与证据裁决
  → 报告草稿 / 审批 / 正式记录
```

现有 `load_snapshot`、`collect_git_evidence`、`create_claims`、`review_code`、`link_deterministic`、`reconcile` 和报告审批链保留。新增步骤只位于锁定的 `delivery-git-diff` 内部，不能改变 `VerificationResult` 的确定性生成规则。

## 3. 内置专业步骤

### 3.1 代码 Finding

复用当前 `review_code`：只向 DeepSeek 提交已冻结的 Claim、Hunk 与受预算限制的只读上下文；输出 `CodeReviewFinding`。模型不能读取远端仓库、执行命令或直接声明核验通过。

### 3.2 Finding 反证复核

新增固定 `challenge_code_findings` 步骤。它按每条已保存的 Finding 重新提供：原始 Finding、所关联的 Hunk、Claim 摘要、可用的局部上下文。DeepSeek 仅输出结构化复核草稿：

- `SUPPORTED`：证据足以支持“该 Finding 值得人工处理”；
- `UNSUPPORTED`：当前冻结证据无法证明触发条件；
- `NEEDS_HUMAN`：证据不矛盾但缺少运行态、外部配置或未冻结上下文。

复核输出必须引用原 Finding 和至少一个 Hunk Evidence ID；不能创建新 Finding、不能改 Severity、不能修改 Claim 或 VerificationResult。持久化的复核状态是 Finding 的补充事实，原始 Finding 不被删除或覆盖。

如果 DeepSeek 不可用、结构化输出无效、复核超时或输入缺失，写入模型调用、Manifest 降级与 Coverage；所有未复核 Finding 显示为“复核未完成”，不会伪装为已反证通过。

### 3.3 覆盖范围汇总

新增固定 `summarize_code_coverage` 步骤，完全由代码计算，不能调用模型。它以冻结 Bundle、可展示 Hunk、代码审查输入计划与反证结果为唯一输入，输出：

- 文件数、Hunk 总数、进入代码审查的 Hunk 数；
- 因二进制、空 Diff、上下文大小/总预算、模型不可用、复核失败而未处理的范围与原因码；
- Finding 数、按复核状态分组的数量。

Coverage 是如实描述范围的不可变运行事实；不得导出“已完成百分比”“全量审查”或“无风险”措辞。

## 4. 数据与接口契约

### 4.1 数据模型

追加迁移，保留历史运行可读：

- `CodeReviewFindingChallenge`：`analysis_run_id`、`finding_id`、`verdict`、`reason`、`evidence_ids`、`model_call_id`、`schema_version`、`created_at`；同一运行同一 Finding 至多一条成功复核记录。
- `AnalysisCoverage` 复用 `scope_kind/state/reason_code/details`，新增标准化 `CODE_REVIEW`、`FINDING_CHALLENGE`、`STANDARD_VERIFICATION` 范围记录；`details` 仅保存计数、Hunk/文件标识摘要和原因码。
- `RunManifest` 记录固定 `workflowVersion`、启用的内置步骤、降级原因及制品哈希；不保存模型思维链。

### 4.2 模型契约

新增 `CodeReviewChallengeProposal` / `CodeReviewChallengeBatch` 与 `CodeReviewChallengeRequest/Result`。Generation Port 仅增加 `challenge_code_findings`；`FakeGenerationModel`、Gemini 或任何未配置 Provider 必须显式失败，不能返回占位复核结果。

DeepSeek 输出以 JSON Schema 校验。服务层再校验 Finding、Hunk Evidence、Claim 和运行归属，拒绝跨运行、跨快照或不存在引用。

### 4.3 只读投影

扩展已有 `GET /analysis-runs/{runId}/code-review`：每项 Finding 返回原始内容、复核状态/理由/Hunk 定位；根级返回 Coverage、Manifest degradation 和模型失败原因。接口不返回或接受任意 Prompt、模型思维链、仓库路径之外的内容。

## 5. Notebook 体验

Notebook 继续是任务行钻取页，不新增 Agent 工作台入口。运行结果区域按固定顺序显示：

1. “标准核验”标签与冻结快照标识；
2. 冻结 Diff 文件和可展开的 Hunk 原文；
3. Finding（原始问题、触发情形、建议、关联 Hunk）；
4. 复核标记：`证据支持`、`当前证据不足`、`需人工确认`、`复核未完成`；
5. 覆盖说明和下一步动作。

“当前证据不足”只影响该 Finding 的展示优先级，不能删除审计记录；“需人工确认”提供进入报告处置的上下文，但不自动创建报告结论。

## 6. 状态、失败与权限

- 标准核验始终绑定 `DELIVERY_VERIFICATION`、正式输入快照和同源 Git Diff；不改变快照、报告、审批和发布的既有权限门禁。
- Finding 反证仅在代码审查成功且至少存在一个 Finding 时运行；没有 Finding 时写 `NOT_APPLICABLE` Coverage，流程继续。
- Diff 制品缺失、哈希不匹配、模型密钥缺失、限流、超时、结构化校验失败均为受控降级，Notebook 必须给出原因和下一步，禁止成功样式或完成率。
- 分析可重试，但历史 AnalysisRun、Finding、Challenge 和 Coverage 不可回写；重新运行必须使用新的 AnalysisRun，并仍绑定原正式快照。

## 7. 验收与测试

1. 构造冻结 Diff、Claim、Hunk 与有效 DeepSeek Mock，确认 Finding → Challenge → Coverage 的顺序、关联约束和持久化。
2. 验证 `UNSUPPORTED`、`NEEDS_HUMAN`、无 Finding、模型不可用、无效 JSON、跨运行引用、缺少 Hunk 分别产生正确状态或拒绝。
3. 验证 Deterministic `VerificationResult` 在新增步骤前后遵循同一证据裁决规则，Challenge 不可改写结论。
4. 验证只读 API 不泄露 Prompt/思维链，并能返回 Hunk、复核和 Coverage。
5. 前端组件覆盖四种复核状态和模型失败/未覆盖展示；运行前端构建与定向后端回归。
6. Docker/数据库恢复、配置有效 DeepSeek Key 后，再进行一次公开仓库的真实端到端运行；不以静态测试代替该项。

## 8. 演进边界

后续“深度核验”只能作为新的内置版本在标准流程之后追加受限步骤，例如跨文件影响、接口兼容或资料一致性检查。它们仍共享快照、制品、权限、Coverage、审批与正式记录；不会开放给普通用户自由连线。
