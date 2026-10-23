# 交付代码审查核心 v2 设计

状态：已获方案确认，待规格复核
日期：2026-08-25
范围：在现有 `delivery-git-diff` 内增量增强交付代码审查能力。

## 1. 目标与边界

本切片回答：在指定、冻结且可回放的 Git Diff 范围内，变更是否存在可定位的代码问题，以及这些问题与已存在验收项的关系。

它不回答 Issue 是否整体完成、项目是否完成或安全是否通过。现有固定主链保持不变：

`requirement-claim-core -> delivery-git-diff -> evidence-reconciliation`

其中 `delivery-git-diff` 的能力键不变，内部升级为“交付代码审查核心 v2”。DeepSeek 只能产出受 schema 约束的 Finding 与 Claim 关联草稿；`evidence-reconciliation` 继续是唯一能写入最终 `VerificationResult` 的确定性裁决者。

禁止行为：checkout、执行仓库代码、运行构建/测试/Hook、Git 写操作、GitHub 评论/标签/审批回写、模型或 Provider 自动回退。

## 2. 输入冻结与制品

### 2.1 Git 范围

用户在现有 Notebook 中填写 base/target ref。系统解析并保存：

- requested base SHA；
- target SHA；
- merge-base SHA；
- effective base SHA；
- diff mode；
- 路径范围；
- 完整 Diff 的 SHA-256、大小与采集版本。

当前手工 ref 流程的默认模式是 `DIRECT_SHA_RANGE`，即精确对比用户选择的 base SHA 与 target SHA，不在升级时静默改变范围。后续由已确认 GitHub PR 创建的范围可显式使用 `MERGE_BASE_TO_HEAD`，但不在本切片新增 PR 自动创建流程。

### 2.2 ArtifactObject

新增项目级、不可变 `ArtifactObject`，以统一方式保存哈希、大小、媒体类型、schema version、存储 URI 与创建时间。首批类型：

- `GIT_DIFF`：UTF-8 或二进制安全保存的完整原始 Diff；
- `CODE_CHANGE_BUNDLE`：规范化文件/Hunk、受限代码上下文和 Coverage 的 JSON。

`GitSnapshot` 新增对以上两个制品的引用，并保存采集元数据。历史快照保持可读且可为空；新 v2 正式快照没有通过制品哈希校验时不得启动分析。

文件全文只在 `CODE_CHANGE_BUNDLE` 中作为 `CONTEXT_ONLY` 供模型理解，永远不能直接作为正式支持或冲突结论的依据。正式可引用代码证据只能是 `GIT_DIFF` 中的规范化 Hunk。

## 3. 代码采集与规范化

新增受控组件：

1. `GitChangeCaptureService`：调用现有只读 Git 基础设施，采集 Diff 与元数据。
2. `CanonicalDiffParser`：解析文件、Hunk、旧/新行号、重命名、复制、二进制和删除。
3. `CodeContextReader`：只用 `git show SHA:path` 读取 base/target 内容，并施加文件类型、单文件大小和总预算限制。
4. `CodeReviewPlanner`：按相关验收项、变更风险和输入预算生成批次与覆盖清单。

每个规范化文件至少包括：

- `path`、`old_path`、edit type；
- additions、deletions、binary 标记；
- 完整 patch 与结构化 hunk；
- base/target context 状态；
- context reason code。

支持 `ADDED`、`MODIFIED`、`DELETED`、`RENAMED`、`COPIED`、`TYPE_CHANGED`、`BINARY`、`SUBMODULE` 和 `UNKNOWN`。机器可读的文件名/统计解析使用 NUL 分隔，确保中文路径和空格路径不会丢失身份。

## 4. Coverage 与预算

不以“调用模型成功”代表审查完整。每次运行记录结构化 `AnalysisCoverage.details`：

- 总文件、文本文件、二进制文件、Patch 文件与 Hunk 数；
- 有完整上下文、仅 Patch、跳过与读取失败的文件/Hunk；
- 每批输入字符预算、已使用量、未分析范围及原因；
- 模型成功、失败和被定位校验拒绝的 Finding 数。

首版使用保守字符预算，而不是假设 DeepSeek tokenizer 与本地 tokenizer 完全一致。优先级是：与现有 Claim 文本重合的 Hunk、具有高变更风险的 Hunk、其余 Hunk。预算耗尽时必须保留未覆盖清单，不能生成全量覆盖语义。

## 5. 模型契约与校验

新增 `CodeReviewFindingProposal`，字段固定为：

- `evidence_id`；
- `related_claim_ids`；
- `finding_kind`；
- `severity`；
- `title`；
- `problem`；
- `trigger_scenario`；
- `recommendation`；
- `confidence`。

Prompt 强制要求：仅审查输入 Diff 引入的问题；仅使用提供的 ID；无可靠问题时返回空数组；不得把上下文全文当成可引用证据；不得声称 Issue 完成、项目完成或安全通过。

`CodeFindingValidator` 验证 evidence 和 claim 是否属于同一冻结输入、文件与 Hunk 是否可定位、字段长度与枚举是否合法、置信度是否在范围内、同一运行是否已存在同指纹 Finding。失败 Proposal 不写入正式 Finding，仅写入 Coverage/事件中的受限错误摘要。

没有 claim 的一般代码 Finding 只作为代码审查风险展示，不自动改变验收结论。已经定位且明确关联 Claim 的模型关系仍带 `requires_human_confirmation`，由现有确定性协调规则决定其能否影响最终结果。

## 6. 持久化对象

新增：

- `ArtifactObject`；
- `CodeReviewFinding`。

扩展：

- `GitSnapshot`：Diff/Bundle Artifact、effective base SHA、diff mode、采集版本；
- `AnalysisCoverage`：`details` JSON；
- `ModelCall`：允许关联受限结构化响应制品或记录批次标识，不记录凭据和未经校验的可执行内容。

`CodeReviewFinding` 包含 run、evidence、可选 claim、fingerprint、类型、严重度、标题、问题、触发场景、建议、置信度、生成/验证版本、是否需人工确认及创建时间。唯一键为 `(analysis_run_id, fingerprint)`。

迁移文件编号为 `028_delivery_code_review_core.py`，其 `down_revision` 必须基于当前 027 的实际 revision id；不得修改既有迁移或重写历史事实。

## 7. API 与 Notebook

既有 Git Snapshot 冻结与分析启动接口保持为唯一写入口。新增只读接口：

- `GET /git-snapshots/{snapshotId}/diff`：规范化文件、Hunk、Diff 元数据与 Coverage；
- `GET /analysis-runs/{runId}/code-review`：Finding、关联 Claim、定位、触发场景、建议、Coverage 与模型失败状态。

Notebook 保持现有三栏布局：

- 左栏：验收项；
- 中栏：资料证据与只读 Diff 文件/Hunk；
- 右栏：最终裁决、代码 Finding、触发场景、建议和人工确认状态。

页面必须显示未分析范围、二进制跳过、上下文读取失败、制品损坏和模型不可用等真实状态；不显示伪造成功率或“审查完成”。

## 8. 错误语义

| 场景 | 行为 |
| --- | --- |
| ref 不存在、跨仓库或 Diff 为空 | 拒绝冻结，不创建 GitSnapshot |
| Diff/Bundle 写入失败 | 不创建正式快照 |
| Artifact 哈希不一致 | 阻止运行，记录 `GIT_ARTIFACT_HASH_MISMATCH` |
| 二进制、超限或不支持的文件 | 不送模型，写入 Coverage |
| 上下文读取失败 | 可 Patch-only 继续，状态为部分覆盖 |
| 输入预算耗尽 | 分批处理并保留未覆盖路径/Hunk |
| DeepSeek 不可用 | 不切换 Fake 或其他模型，运行部分完成或失败 |
| 模型虚构 ID/定位 | 丢弃 Proposal，记录 `MODEL_FINDING_INVALID` |

## 9. 定向验证

后端回归覆盖：

- 新增制品的哈希与快照门禁；
- 新增/修改/删除/重命名/二进制文件；
- 中文路径、空格路径与无末尾换行 Diff；
- base/target 错误与跨仓库拒绝；
- 预算截断与 Coverage；
- 模型不可用与虚构 evidence/claim/定位；
- Finding 指纹幂等。

前端验证覆盖：Diff/覆盖状态/模型失败/Finding 映射的组件级逻辑，以及现有生产构建。不会执行项目仓库代码或引入 Fake 模型来取得成功结果。

## 10. 实施顺序

1. 迁移、枚举、模型与制品存储契约。
2. 只读 Git 采集、Diff Parser、上下文 Bundle 与 Coverage。
3. 模型契约、代码审查节点、Finding 校验与确定性协调接入。
4. 只读 API、Notebook 展示和错误状态。
5. 定向回归、真实公开仓库链路验证和承接文档更新。

每一步保持可独立提交，提交只包含本切片文件，使用中文提交说明，不推送远端。
