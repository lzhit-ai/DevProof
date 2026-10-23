# 交付代码审查核心：承接说明（更新至 2026-08-26）

## 1. 这条核心能力解决什么问题

本项目不是“运行一次大模型就给代码打分”。它只回答一个受限问题：

> 对一条已同步的 GitHub Pull Request，人工确认的交付主张能否在指定、冻结且可回放的 Git Diff 中获得证据支持；同时，这个 Diff 中是否存在需要开发者处理的代码 Finding。

不回答“项目整体是否完成”“是否安全通过”“CI 是否通过”。Git 也始终是只读输入：禁止 checkout 工作区、写远端、执行仓库代码、构建、测试或 Hook。

当前产品不开放面向普通用户的 Agent 画布或自由 Prompt/节点编排。固定双核、证据裁决、人工裁决、报告和审批构成唯一近期主线；既有 `SHARED` 外围 Agent 技术基础仅保留为远期、管理员受控扩展，不得影响正式核验结论。

项目知识库也不等同于本页的“验收资料选择器”。它将独立演进为 NotebookLM 式的项目资料工作区：用户管理来源、限定问答范围、查看可定位的引用、保存笔记和生成知识产物。进入本链路时，用户仍只能选择其中已处理完成的具体 `SourceRevision`，并将其冻结到 `InputSnapshot`；知识库问答或摘要不能直接形成 `Claim`、`VerificationResult` 或报告结论。

## 2. 当前主链路与状态边界

```text
GitHub PR 同步
  -> DeliveryItem(PULL_REQUEST)
  -> 创建 VerificationTask / VerificationCycle
  -> DeepSeek 提取交付主张候选，人工确认
  -> 只读 Git 冻结 base/target/path scope
  -> GitSnapshot + 两份 ArtifactObject
  -> Formal InputSnapshot（锁定 PR revision、Claim、资料、Diff）
  -> AnalysisRun / Worker / 固定双核
  -> VerificationResult + CodeReviewFinding + Challenge + Coverage
  -> HumanVerificationDecision（如系统要求）
  -> ReportVersion / ReportItem
  -> 不同成员审批
  -> PublishedRecord
```

| 阶段 | 主状态/对象 | 可写性与关键门禁 |
| --- | --- | --- |
| 任务准备 | `VerificationCycle` 为 `DRAFT` / `NEEDS_EVIDENCE` / `NEEDS_CONFIRMATION` | 可继续确认主张、冻结 Diff、创建正式快照。跨仓库、空 Diff、资料未就绪、未确认主张都会拒绝。 |
| 正式输入 | `InputSnapshot(purpose=FORMAL)` | 输入哈希由规范 JSON 计算；已有同哈希快照复用。只能绑定当前轮次的 GitSnapshot，且该 GitSnapshot 必须具备两份本地制品。 |
| 分析 | `AnalysisRun`、`RunEvent`、`AnalysisCoverage`、`ModelCall` | Worker 异步消费。模型或制品失败写真实失败/降级状态，不能换 Fake/Gemini 伪造结论。 |
| 人工裁决 | `HumanVerificationDecision` | 仅已结束运行、报告尚未提交时允许；追加新记录并指向被替代记录，不覆盖系统结果。 |
| 报告 | `ReportVersion`、`ReportItem` | DRAFT 可更新说明、处置与随裁决刷新；提交前，所有 `requires_human_confirmation` 的结果必须有人工裁决。 |
| 审批与固化 | `ApprovalAction`、`PublishedRecord` | 提交者不可审批自己的报告；仅 REVIEWER/ADMIN 可审批；仅 ADMIN 可固化 APPROVED 报告；发布后 cycle/report 不可写。 |

## 3. Git 读取、冻结、保存和持久化

### 3.1 冻结时实际发生什么

入口：`POST /api/v1/cycles/{cycleId}/git-snapshots`，实现位于 `backend/app/api/routes/git.py` 和 `backend/app/application/services/git_service.py:freeze_git_snapshot`。

1. 校验调用者是该项目的 `SUBMITTER` 或 `ADMIN`，轮次仍处于可准备状态。
2. `assert_delivery_item_repository_match` 将登记仓库 URL 与该 PR 所属 GitHub 仓库比较；任务绑定 PR 时，不能选择其他仓库。
3. `ReadOnlyGitReader.freeze_range`（`backend/app/infrastructure/git_reader.py`）在受控 artifact 根目录下按 URL hash 找到/创建裸工作副本：
   - 首次：`git clone --no-checkout --filter=blob:none`；
   - 后续：`git fetch --prune origin`；
   - 只允许 `rev-parse`、`merge-base`、`diff --no-ext-diff --find-renames --binary`、`show`、`cat-file` 等白名单命令。
4. 先把用户输入的 `baseRef`、`targetRef` 解析为不可变 commit SHA；`TWO_DOT` 使用 `base..target`，`THREE_DOT` 使用 `merge-base..target`。include/exclude pathspec 一并进入命令与覆盖范围。
5. 读取完整 unified diff bytes，并生成：文件状态、增删行、二进制/删除/子模块/生成文件/超大文件的显式跳过信息；再解析 hunk，并仅补充受字节预算限制的 base/target 上下文，得到 `CODE_CHANGE_BUNDLE`。
6. Diff 为空时立刻返回 `GIT_DIFF_EMPTY`，不会建立 `GitSnapshot` 或正式快照。

### 3.2 代码在哪里保存

冻结不是“把 Git 仓库保存到数据库”。它保存的是可验证的变更制品：

| 层 | 记录内容 | 实体/位置 |
| --- | --- | --- |
| PostgreSQL 元数据 | 制品类型、SHA-256、大小、媒体类型、schema 版本、存储 URI | `artifact_objects` / `ArtifactObject` |
| Artifact storage 原始 Diff | 完整 `payload.diff` bytes | `${ARTIFACT_ROOT}/{projectId}/git-snapshots/{artifactId}/payload.diff` |
| Artifact storage 结构化变更包 | 文件、hunk、可用上下文、跳过原因、覆盖范围 JSON | `${ARTIFACT_ROOT}/{projectId}/git-snapshots/{artifactId}/code-change-bundle.json` |
| PostgreSQL Git 冻结元数据 | 用户选择的 refs、解析后的 SHA、merge base、path scope、diff hash、coverage、两份制品 ID | `git_snapshots` / `GitSnapshot` |
| PostgreSQL 正式快照绑定 | `git_snapshot_id` + Diff hash | `input_snapshot_gits` / `InputSnapshotGit` |

`ArtifactObject` 采用 `(project_id, kind, content_hash)` 唯一约束，同项目同内容同类型可去重。写入顺序是：先创建数据库行并 flush，再写 artifact storage，失败则抛出 `GIT_ARTIFACT_WRITE_FAILED`，外层 route rollback。读取时重新计算 SHA-256；哈希不符为 `GIT_ARTIFACT_HASH_MISMATCH`，制品缺失为 `GIT_ARTIFACT_MISSING/UNAVAILABLE`，不会悄悄重新抓取远端 Git。

### 3.3 为什么分析阶段不再读取 GitHub/Git

`collect_git_evidence`（`backend/app/workflows/verification_graph.py`）只读取正式快照绑定的本地 `GIT_DIFF` 与 `CODE_CHANGE_BUNDLE` 制品，并校验哈希。它为每个 hunk 建立 `EvidenceItem`：

- `source_type=CODE`，`evidence_kind=GIT_DIFF_HUNK`；
- `locator` 含 artifactId、target commit、路径、旧路径、hunk header、新旧行范围；
- `content_hash` 是制品 ID + 路径 + hunk + payload 的规范身份哈希；
- coverage 会记录 `GIT_CAPTURE` 成功、部分覆盖或不可用。

这样即便远端分支已推进、仓库被删或凭据过期，历史运行仍使用当时冻结的输入；若本地制品不存在，系统诚实报告不可回放，不改用远端当前内容。

## 4. 固定双核如何处理代码

编排顺序由 `verification_graph.py` 固定：

`load_snapshot -> collect_git_evidence -> create_claims -> review_code -> challenge_code_findings -> summarize_code_coverage -> link_deterministic -> reconcile -> report-draft`。

| 节点 | 输入 | 输出/持久化 | 约束 |
| --- | --- | --- | --- |
| `create_claims` | `InputSnapshotClaim` 中人工确认的交付主张 | 本运行 `Claim` | 无确认主张即 `CLAIMS_NOT_CONFIRMED`。 |
| `review_code` | 结构化变更包、精确 hunk Evidence、冻结 Claim | `CodeReviewFinding`、`ModelCall(CODE_REVIEW)`、`AnalysisCoverage(CODE_REVIEW)` | 仅 `GENERATION_PROVIDER=deepseek`；Finding 的 claim/evidence/fingerprint 必须校验通过。 |
| `challenge_code_findings` | 已保存 Finding、其原始 hunk、可选 Claim | `CodeReviewFindingChallenge`、`ModelCall(CODE_REVIEW_CHALLENGE)`、Coverage | 只给 `SUPPORTED` / `UNSUPPORTED` / `NEEDS_HUMAN`；不生成新 Finding、不改严重级别、不改 `VerificationResult`。 |
| `summarize_code_coverage` | bundle、两个前序 Coverage、Challenge | `AnalysisCoverage(STANDARD_VERIFICATION)` | 汇总文件/hunk/二进制/已审查 hunk/Finding/反证 verdict/未覆盖原因；不是完成率或“无风险”声明。 |
| `link_deterministic` + `reconcile` | 所有冻结 Evidence、Claim、规则链路 | `ClaimEvidenceLink`、`VerificationResult` | 交付主张结论与 Finding 分开保存；Finding 是风险线索，不能直接替换交付结论。 |

模型不可用、超时、结构化输出不合法或预算不足时，节点写 `ModelCall.status=FAILED`、`AnalysisCoverage.state=UNAVAILABLE/PARTIAL` 和 manifest degradation；页面应提示错误代码与下一步，而不是显示成功。

## 5. 2026-08-24 至 08-26 已落地的新增/修订

以下以 `main@13813fc` 为准；8 月 26 日的人工裁决与报告回看已提交为 `f67f59e`，承接文档更新已提交为 `13813fc`。

| 日期/状态 | 已落地内容 | 承接注意事项 |
| --- | --- | --- |
| 08-25，已提交 `c9cb191` / `fb9e934` | 固定“需求主张核 -> 交付 Git Diff 核 -> 证据汇总”设计，完成可回放 Git 制品、Finding 反证复核和标准核验覆盖的实现基础。 | 不恢复旧的可任意替换核心/任意执行模型路径。 |
| 08-26，已提交 `97a752e` | 多格式知识库解析；Git 仓库列表；PR 作为代码交付入口；交付主张候选/确认；PR 同源仓库限制；正式快照增加 PR revision、Claim、制品绑定；Notebook 读取 Diff/Finding/Coverage。 | `VerificationTask.delivery_item_id` 已要求为 `PULL_REQUEST`，Issue 只保留为背景来源，不再直接创建代码审查。 |
| 08-26，已提交 `5462093` | 工作台、项目创建与接入、知识库、PR 任务中心、Notebook 三栏、审批与记录页改为真实 API 驱动的使用流。 | Notebook 是任务行的钻取页，不放入左侧一级导航。 |
| 08-26，已提交 `f67f59e`：人工裁决 | 增加追加式人工裁决；系统结论与人工有效结论分开展示；提交报告前强制完成必须裁决项；DRAFT 报告会刷新保存人工裁决快照。 | 部署时必须执行 `alembic upgrade head`；不得把人工裁决直接覆盖 `VerificationResult.status`。 |
| 08-26，已提交 `f67f59e`：报告内容回看/审批页 | 新增 `GET /projects/{projectId}/report-versions/{reportId}/content`，从 `ReportItem.result_snapshot` 和正式快照 Evidence 回放内容；Notebook 草稿可看，审批页先展示报告正文和引用，哈希退为校验信息。 | 审批动作在冻结内容读取失败时必须禁用，不能只看 hash 批准。 |

## 6. 关键接口速查

| 用途 | 接口 |
| --- | --- |
| 登记/列出只读仓库 | `POST` / `GET /projects/{projectId}/git-repositories` |
| 冻结与回看 Diff | `POST /cycles/{cycleId}/git-snapshots`；`GET /git-snapshots/{snapshotId}/diff` |
| 创建正式快照与运行 | `POST /cycles/{cycleId}/formal-snapshots`；`POST /input-snapshots/{snapshotId}/analysis-runs` |
| 观察真实运行 | `GET /analysis-runs/{id}`、`/events`、`/results`、`/code-review` |
| 人工裁决 | `POST /analysis-runs/{runId}/results/{resultId}/human-decisions` |
| 报告正文回放 | `GET /projects/{projectId}/report-versions/{reportId}/content` |
| 报告流转 | `PUT /report-versions/{id}`；`POST /submit`、`/approve`、`/request-changes`、`/reject`、`/publish` |

所有写接口需要 `Idempotency-Key`；项目授权以后端 `ProjectMember` 为准。前端项目选择仅是请求上下文，不是权限边界。

## 7. 已验证与未验证

- 已有定向后端测试：`test_delivery_code_review_core.py`、`test_git_repository_listing.py`、`test_report_cycle_immutability.py` 等；最新本地修改已执行 `python -m compileall backend/app`、`pytest -q backend/tests/test_report_cycle_immutability.py`（2 passed）、`npm run build`。
- 08-25 曾以公开仓库完成真实 DeepSeek 代码审查和含 Finding 的公开 Diff 演示；这只证明该次环境/样本，不等于每个私有仓库、模型配额或网络环境可用。
- 当前仍缺少浏览器级自动 E2E、私有仓库 PAT 验收、外部服务限流恢复演练和完整发布记录回放验收。

## 8. 接手前必做检查

1. `git status --short`：承接时先确认工作树是否干净；本次文档更新时，核心功能已在 `f67f59e`，不应再按“未提交改动”处理。
2. `docker compose ps` 与 `docker compose exec -T api alembic current`：确认 API/worker 镜像与数据库确实到 `032_human_verification_decisions`。
3. 先选择一个真实 PR、产生非空 Diff，检查 `ArtifactObject` + artifact storage 是否同时存在，再启动运行。
4. 将“代码存在”“静态构建通过”“容器健康”“真实模型成功”“用户页面可见”分开记录，不互相替代。
