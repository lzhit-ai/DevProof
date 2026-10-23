# AI-CodeReview v1 架构设计约束与下一次对话规划

## 1. 文档用途

本文档不是业务实现说明，也不是最终架构文档。它是下一次对话的架构设计任务书，用于固定已确认的产品方向、技术边界、领域不变量和验收标准，使下一次对话能够一次性完成 AI-CodeReview v1 的完整架构设计，避免重新讨论已确定事项或提前进入编码。

下一次对话的唯一目标是产出可直接指导项目骨架搭建的完整架构设计。完成标准是：不存在会导致目录重构、核心数据模型推翻、状态职责混乱或基础设施重新选型的 P0 待定项。

本仓库当前状态：

- 实际项目根目录：`D:\秋招项目\AI应用开发项目\one`
- Git 远程：`https://github.com/yyy2045/one.git`
- 当前分支：`main`
- 当前仓库为空，尚无首个提交
- `zhao-zg/AI-CODEREVIEW` 是误粘贴链接，必须完全忽略

## 2. 产品定位

项目名称：**AI-CodeReview**

建议副标题：**面向研发交付的多源证据核验与交付记录系统**

一个需求对应一次交付核验过程和一份正式交付记录。系统同时分析需求、设计、验收标准、会议纪要、Git Diff、测试或构建结果等材料，判断“要求做什么”与“实际做了什么”是否一致，并在人工审批后发布可追溯的交付记录。

它不是：

- 通用聊天机器人；
- 只给代码建议的 PR Review 工具；
- 完整 SAST 或安全合规平台；
- 在线 IDE、代码执行器或自动修复工具；
- 自治多 Agent 系统。

代码是交付证据之一，不能覆盖需求、设计和验收资料的业务权威性。任何正式结论都必须有证据；证据不足、冲突和推断必须如实展示。

## 3. 首版成功标准

首版必须形成以下完整闭环：

```text
创建核验任务
→ 上传资料并登记一个 Git 仓库
→ 选择并冻结资料版本及 Git 提交范围
→ 异步执行一次受控核验流程
→ 形成 Claim、Evidence 与 VerificationResult
→ 显示确认、部分支持、冲突、证据不足和待确认推断
→ 生成交付记录草稿
→ 提交者补证或提交审核
→ 审核者要求补证、驳回或批准
→ 发布不可变正式记录
→ 输入发生变化时生成新快照和新版本
```

作品集演示至少覆盖：

1. 一条已确认验收项；
2. 一条部分支持验收项；
3. 一条资料与代码相互冲突的验收项；
4. 一条证据不足项；
5. 一个确定性工具命中和一个 AI 语义建议；
6. 模型不可用或结构化输出非法时的真实降级；
7. 分析节点中断后的恢复；
8. 补证、重新分析、审批和发布新版本。

## 4. 已固定且不得重新讨论的技术边界

- 前端：Vue 3、TypeScript、Vite。
- 后端：Python、FastAPI、Pydantic。
- 数据库：PostgreSQL，向量能力使用 pgvector。
- AI 编排：首版引入 LangGraph。
- 模型：Gemini API 作为首个生成模型适配器，生成模型与 Embedding 模型分离。
- 本地运行：Docker Compose。
- 系统形态：模块化单体；API 与 Worker 可分进程运行，但共享同一后端代码库、领域模型和 PostgreSQL。
- PostgreSQL 是项目、任务、证据、报告、审批和正式状态的唯一事实来源。
- 原始资料使用受控本地卷保存，数据库保存元数据、版本、哈希和位置；通过端口保留未来对象存储替换能力。
- 不全面引入 LangChain，不把 LangChain 作为核心依赖，不使用 `create_agent`、通用 Agent 循环或自由多 Agent。
- AI 问答不重复执行完整核验图，只读取已有结构化结果与有权限的原始证据。
- 后续实现按最小可运行闭环提交和推送，所有 Git 提交说明使用中文。

## 5. 推荐架构路线及被放弃方案

### 5.1 采用：模块化单体 + 独立 Worker + PostgreSQL Job

Web 请求由 FastAPI 处理；耗时分析由独立 Worker 领取 PostgreSQL 中的 Job 后执行。两者共享领域代码，但通过应用服务和端口交互。

选择理由：

- 能清晰展示 API、领域、异步任务和 AI 编排边界；
- Worker 重启后可恢复，不依赖 FastAPI 进程内后台任务；
- 不需要额外引入 Redis、Celery、Kafka 或 Temporal；
- 适合一个月作品集的开发和讲解成本。

### 5.2 不采用：FastAPI 进程内后台任务

虽然搭建最简单，但进程重启会丢任务，难以可靠实现租约、恢复、取消和重试，不能支撑正式交付记录的可追溯性。

### 5.3 不采用：微服务或事件驱动平台

会引入服务发现、消息一致性、部署和运维成本，不能增加首版核心业务价值。

## 6. 运行组件与职责

```text
Browser
  │
  ▼
Vue Web ───────► FastAPI API ───────► PostgreSQL + pgvector
                      │                         ▲
                      │ 创建 Job                │ 领取、心跳、写入结构化结果
                      ▼                         │
                 Analysis Worker ───────────────┘
                      │
                      ├─ LangGraph 核验图
                      ├─ 文档解析/检索端口
                      ├─ Git 只读解析端口
                      ├─ 模型网关端口
                      └─ 受控文件卷
```

建议 Compose 组件只有：

- `frontend`：静态页面或 Vite 开发服务；
- `api`：FastAPI HTTP 服务；
- `worker`：与 API 共享后端镜像，通过不同启动命令运行；
- `postgres`：启用 pgvector 扩展；
- `artifact-volume`：资料与只读 Git 工作目录的受控卷。

首版不增加 Redis、消息中间件、对象存储服务和独立可观测性平台。

## 7. 模块边界

| 模块 | 主要职责 | 明确不负责 |
|---|---|---|
| 项目与权限 | 用户、项目成员、提交者/审核者角色、资源权限 | AI 分析和报告内容 |
| 核验任务 | VerificationTask、核验轮次、输入快照、业务状态机 | 文档或 Git 的解析实现 |
| 资料与检索 | 原文件、资料版本、解析、Chunk、Embedding、引用定位 | 核验结论和正式审批 |
| Git 证据 | 仓库登记、提交范围冻结、Diff、文件定位和覆盖范围 | 判断需求是否已完成 |
| 分析执行 | AnalysisJob、AnalysisRun、LangGraph、节点运行和恢复 | 正式审批状态 |
| 证据与核验 | Claim、Evidence、关系、冲突、结果、覆盖度 | 报告发布 |
| 报告与审批 | 报告版本、人工操作、发布记录、版本链 | 改写分析事实 |
| AI 问答 | 基于授权证据和结构化结果进行只读回答 | 启动完整核验图或改变状态 |
| 模型网关 | 生成/Embedding DTO、Gemini 适配、超时、重试、调用记录 | 领域裁决和审批 |
| 审计与可观测性 | 审计事件、节点事件、模型调用、错误和耗时 | 作为业务状态源 |

基础设施能力通过端口接入：

- `DocumentParserPort`
- `GitReaderPort`
- `RetrieverPort`
- `GenerationModelPort`
- `EmbeddingModelPort`
- `ArtifactStoragePort`
- `ReportRendererPort`

领域层不得依赖 FastAPI、LangGraph、Gemini SDK 或 LangChain 类型。路由层不得直接操作 ORM 模型，图节点不得直接修改审批或发布状态。

### 7.1 下一次设计采用的默认目录布局

```text
one/
├─ frontend/                 # Vue 3 工作台
├─ backend/
│  ├─ app/
│  │  ├─ api/               # FastAPI 路由、鉴权和请求响应 DTO
│  │  ├─ application/       # 用例、事务和状态迁移
│  │  ├─ domain/            # 实体、值对象、领域服务和端口
│  │  ├─ infrastructure/    # PostgreSQL、文件、Git、Gemini 等适配器
│  │  ├─ workflows/         # LangGraph 图定义与节点适配
│  │  └─ worker/            # Job 领取、心跳、恢复和执行入口
│  ├─ migrations/           # Alembic 迁移
│  └─ tests/
├─ infra/                   # Compose、镜像和本地运行配置
├─ samples/                 # 固定资料、Git 与评测夹具
└─ docs/                    # 架构、接口和使用说明
```

下一次设计可以细化包名，但不能破坏“领域层向内、框架适配向外”的依赖方向，也不能把 API 与 Worker 拆成两个重复的后端项目。

### 7.2 依赖选择约束

后端核心依赖类别固定为：FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、PostgreSQL 驱动、pgvector Python 适配、LangGraph、Gemini 官方 SDK。测试使用 pytest 体系。具体兼容版本由下一次设计统一锁定，不在不同模块各自选择。

前端核心依赖类别固定为：Vue 3、TypeScript、Vite、Vue Router、Pinia，以及一个轻量 UI 组件库。组件库属于可替换选择，不得影响领域与 API 契约。

禁止为了模型调用引入 LangChain 全家桶。领域层只使用自定义 DTO；若未来确需单个 LangChain 组件，必须通过独立 ADR 说明必要性、替代方案和隔离边界。

## 8. 核心数据主链

```text
Project
├─ ProjectMember
└─ VerificationTask
   ├─ VerificationCycle
   │  ├─ SourceRevision / GitSnapshot
   │  ├─ InputSnapshot
   │  ├─ AnalysisJob
   │  ├─ AnalysisRun
   │  │  ├─ NodeAttempt / ModelCall / RunEvent
   │  │  ├─ Claim ← ClaimEvidenceLink → EvidenceItem
   │  │  ├─ VerificationResult
   │  │  ├─ RiskFinding
   │  │  └─ AnalysisCoverage
   │  └─ ReportVersion
   │     ├─ ReportItem
   │     └─ ApprovalAction
   └─ PublishedRecord
```

关键语义：

- `VerificationTask`：一个需求的稳定核验容器。
- `VerificationCycle`：一次正式核验轮次；发布后输入变化时创建新轮次。
- `SourceRevision`：某份资料的不可变版本。
- `GitSnapshot`：仓库、完整提交 SHA、Diff 模式和路径范围的冻结结果。
- `InputSnapshot`：一次分析所使用全部资料与 Git 输入的不可变集合。
- `AnalysisRun`：针对一个输入快照的一次实际执行，同一快照允许重跑。
- `AnalysisRunManifest`：工作流、规则、Prompt、模型和 Schema 等运行版本清单。
- `Claim`：需要核验的目标、验收条件、约束或需求变更。
- `EvidenceItem`：不可变证据单元。
- `ClaimEvidenceLink`：Claim 与 Evidence 的支持、反驳或上下文关系。
- `VerificationResult`：协调后的事实状态和理由。
- `AnalysisCoverage`：已分析、跳过、失败和不支持的范围。
- `ReportVersion`：可编辑、提交、审批、发布的报告版本。
- `ApprovalAction`：只追加、不覆盖的人工决策。
- `PublishedRecord`：对已批准报告版本的不可变发布记录。

## 9. 不可变输入快照

`InputSnapshot` 至少冻结：

- 所有 `source_revision_id`、内容哈希和解析版本；
- 仓库规范化地址或身份指纹；
- `base_sha`、`target_sha`、`merge_base_sha`；
- two-dot 或 three-dot 比较语义；
- 路径包含/排除规则；
- Diff 内容哈希；
- 外部测试或构建证据的提交 SHA 和内容哈希；
- 核验策略与工作流版本；
- 创建人、创建时间和规范化 `snapshot_hash`。

分支名仅保存为用户选择记录，正式分析和报告必须引用完整 Commit SHA。资料补充、目标分支前移、路径范围变化或测试证据更新，都必须创建新快照，不得覆盖旧快照。

模型实际名称、调用重试和降级信息属于 `AnalysisRunManifest`，不属于业务输入。这样同一快照可以使用不同模型重跑，同时仍能比较结果差异。

## 10. 统一证据协议

逻辑协议为：

```text
Claim → Evidence[] → VerificationResult → ReportItem → HumanApproval
```

数据库实现必须拆为 `Claim`、`EvidenceItem` 和 `ClaimEvidenceLink`，而不是保存一个不可查询、不可约束的自由 JSON 数组。

### 10.1 EvidenceItem 最低字段

- `evidence_id`
- `project_id`
- `snapshot_id`
- `source_type`：文档、代码、测试、工具、人工补证等
- `evidence_kind`：原始事实、确定性工具命中、模型推断、人工注释
- `source_revision_id` 或 `commit_sha`
- `content_hash`
- 原始摘录或安全摘要
- 类型化 `locator`
- `locator_precision`：精确、近似、不可用
- `captured_at`
- 提取方法及工具/规则/模型版本
- 是否需要人工确认

定位器要求：

- 文档：页码、段落、字符范围、Chunk ID；
- 代码：Commit、文件路径、Diff Hunk、旧/新侧、起止行；
- 测试：报告、测试套件、用例名称、退出状态；
- 工具：规则 ID、文件和行号；
- 人工补证：提交人、说明和附件版本。

### 10.2 ClaimEvidenceLink

关系仅允许：

- `SUPPORTS`
- `CONTRADICTS`
- `CONTEXT_ONLY`

链接同时保存关系理由、置信度、产生方式和是否待人工确认。证据不足不是一种链接，而是核验结果在缺少充分链接时的状态。

### 10.3 VerificationResult

状态固定为：

- `CONFIRMED`
- `PARTIALLY_SUPPORTED`
- `CONFLICTING`
- `INSUFFICIENT_EVIDENCE`
- `INFERENCE_REQUIRES_CONFIRMATION`

模型推断不能单独把结果提升为 `CONFIRMED`。最终状态必须由证据协调服务根据有效链接、来源权威性和人工确认规则计算。

来源权威性默认采用：已批准验收标准或需求版本高于已批准设计，已批准设计高于会议纪要；同级资料按批准状态、明确版本和时间判断。代码与测试只能证明“实际做了什么”，不能覆盖“要求做什么”。同级来源冲突不得由模型擅自裁决，必须进入 `CONFLICTING` 或人工确认。

每个 `VerificationResult` 必须保存使用的 Claim 版本、Evidence ID 集合、协议版本、状态、裁决理由、是否需要人工确认和产生方式。`ReportItem` 保存发布当时的结果与引用快照，后续重算不得悄悄改变已经提交或发布的报告。

### 10.4 引用防伪造

模型只能引用当前节点被允许访问的 Evidence ID。中心化 `CitationResolver` 必须校验证据是否真实存在、属于当前项目和快照、调用者有访问权限、定位器有效。无法精确定位时只允许文件级引用，不得虚构页码或行号。

## 11. 独立状态机

### 11.1 资料处理

```text
UPLOADED → PARSING → CHUNKING → INDEXING → READY
任一步骤 → FAILED
```

只有 `READY` 的必需资料可以进入快照。失败必须保存阶段和错误码，不能静默跳过。

### 11.2 分析运行

```text
QUEUED → RUNNING → SUCCEEDED
                 ├→ PARTIALLY_COMPLETED
                 ├→ FAILED
                 └→ CANCELLED
```

重试是运行事件而非正式业务状态。LangGraph checkpoint 仅服务一次 `AnalysisRun` 的恢复。

### 11.3 核验轮次业务状态

```text
DRAFT
→ ANALYZING
→ DRAFT_READY / NEEDS_EVIDENCE / NEEDS_CONFIRMATION
→ PENDING_REVIEW
→ REJECTED / APPROVED
→ PUBLISHED
```

`ANALYZING` 必须绑定活动中的 AnalysisRun；已发布轮次不可回退。新输入创建新轮次。

### 11.4 报告版本

```text
DRAFT → SUBMITTED → CHANGES_REQUESTED / APPROVED
                            APPROVED → PUBLISHED → SUPERSEDED
```

草稿可编辑；提交后内容哈希锁定。要求修改时创建新草稿版本，不能重新打开并覆盖旧版本。

核验结果的“已确认”与报告的“已批准”不是同一概念。审核者可以批准一份仍如实包含证据不足项的报告，但必须给出处理或豁免理由，系统不得把该 Claim 改写为已确认。

## 12. LangGraph 编排边界

推荐流程：

```text
初始化并加载 InputSnapshot
├─ 资料理解：抽取 Claim 与资料证据
└─ Git 采集：Diff、上下文与确定性风险检查
          ↓
代码与 Claim 对齐
          ↓
统一结构与引用校验
          ↓
证据协调、去重、时效和冲突判断
          ↓
风险与最小补证建议
          ↓
交付记录草稿
          ↓
完成或部分完成
```

资料理解和 Git 采集可以并行；“代码是否满足验收条件”的判断必须等待 Claim 形成。

图状态只携带版本化结构和 ID，例如：

- `analysis_run_id`
- `input_snapshot_id`
- `claim_ids`
- `evidence_ids`
- `verification_result_ids`
- `coverage_id`
- `node_errors`
- `workflow_schema_version`

原始全文和 Diff 通过服务端口按需读取，不把大段敏感内容永久塞进 checkpoint。节点输出必须通过 Pydantic Schema 校验后才能进入后续节点。

图节点只能调用文档解析、Git、检索、模型网关和报告草稿服务；不得直接改变核验轮次、审批或发布状态。节点失败必须记录为可观察的技术状态，并通过协调节点生成“部分完成”或“待补证”，不能伪装成完整成功。

## 13. 持久异步任务与恢复

FastAPI 启动分析时：

1. 校验权限、任务状态和输入快照；
2. 在同一事务创建 `AnalysisRun` 与 `AnalysisJob`；
3. 返回 `202 Accepted + analysis_run_id`；
4. 前端首版通过轮询读取进度。

Worker 使用 PostgreSQL 行锁和 `FOR UPDATE SKIP LOCKED` 领取任务，并记录：

- 幂等键；
- 租约持有者与过期时间；
- 心跳时间；
- 尝试次数和最大重试次数；
- 超时、取消请求和最后错误；
- 对应 checkpoint 命名空间。

Worker 异常退出后，过期租约允许另一 Worker 恢复。同一 `(snapshot_hash, analysis_config_hash)` 不得重复生成多个活动运行；重试不得重复发布报告或重复执行审批动作。

## 14. 文档、检索与 Git 边界

### 14.1 文档

首个最小闭环优先支持 Markdown 和纯文本。PDF 仅支持可提取文本的版本时再加入，OCR、复杂表格和全格式文档平台明确后置。

Chunk 必须回链到 `source_revision_id` 和原文位置。Embedding 模型变化时创建新的索引版本，不覆盖旧索引。

### 14.2 检索

首版采用 PostgreSQL 全文检索与 pgvector 混合检索。执行顺序必须是：

```text
项目/任务/资料版本/用户权限过滤
→ 关键词与向量召回
→ 去重和最小重排
→ 返回带 Evidence ID 的候选证据
```

无命中只能返回“未检索到足够证据”，不能生成肯定事实。

### 14.3 Git

首版连接一个已登记 Git 仓库，用户选择基准分支和目标分支或提交范围。开始分析时冻结为完整 SHA。

必须处理并记录：重命名、删除、二进制、生成文件、大文件、子模块和解析失败。所有跳过项写入 `AnalysisCoverage`。

Git 始终只读，不执行仓库代码、构建命令、Git hooks、自动修复或自动提交。测试和构建结果作为外部证据导入，并绑定具体 Commit SHA。

## 15. 模型网关与 AI 问答

领域层只依赖自定义请求与响应 DTO，例如 `GenerationRequest`、`GenerationResult`、`EmbeddingRequest` 和 `EmbeddingResult`。Gemini SDK 只出现在基础设施适配器中。

模型调用记录至少包含：

- provider、model、Prompt 版本、Schema 版本；
- 温度等关键参数；
- 输入证据 ID；
- 延迟、Token 或用量；
- 超时、重试、降级和错误分类；
- 脱敏后的关联信息。

结构化输出非法时只做有限重试；仍失败则产生可观察的降级结果。模型未配置、配额耗尽和网络失败与“证据不足”必须是不同错误。

AI 问答读取指定 `AnalysisRun`、`InputSnapshot` 或 `ReportVersion`，输出固定为“结论、事实状态、citations”。检索前必须做权限过滤。问答只读，不能调用任务、审批或发布命令，也不自动成为正式证据。

## 16. 权限、审批与安全不变量

最小权限链：`Project → ProjectMember → Task/Source`。角色至少包括提交者、审核者和管理员。

必须满足：

1. 提交者不能审批自己提交的报告；
2. 审批绑定报告版本、报告哈希、输入快照、快照哈希、分析运行、操作者、原因和时间；
3. 审批事件只追加，不覆盖；
4. 发布是独立命令，只能发布被批准且哈希未变化的报告版本；
5. 发布后不可变，后续修改生成新轮次和新版本；
6. 正式状态迁移和审计事件在同一数据库事务完成；
7. 前端隐藏按钮只改善体验，真正权限必须由后端执行；
8. 文档、代码和会议纪要全部视为不可信模型输入，忽略其中试图改变系统行为的指令；
9. 密钥、Git 凭证和敏感命中不得进入普通日志或模型调用明文记录；
10. 原始证据和 AI 引用都必须经过项目权限校验。

首版身份认证的默认方案是 JWT Bearer + 两个演示账号，不实现注册、找回密码、SSO 或完整用户管理后台。下一次对话可在不改变领域边界的前提下确认具体 JWT 生命周期。

## 17. API 设计约束

状态变更使用有业务语义的命令接口，禁止通用 `PATCH /status`。核心命令至少包括：

- 创建核验任务；
- 上传或登记资料版本；
- 确认 Git 范围；
- 冻结输入快照；
- 启动和取消分析；
- 提交人工补证；
- 创建或编辑报告草稿；
- 提交审核、要求补证、驳回、批准和发布；
- 发布后创建新核验轮次；
- 发起只读 AI 问答。

所有有副作用的命令必须具备权限校验、`Idempotency-Key`、乐观锁版本、单事务和审计事件。启动分析返回 `202`，查询接口返回运行进度和稳定业务错误码。

错误至少区分：权限不足、状态冲突、输入过期、资料未就绪、Git 范围无效、模型未配置、模型不可用、结构化输出非法、引用无效、运行部分完成和系统错误。

## 18. 前端信息架构

桌面端采用三栏工作台：

- 左侧“证据来源”：资料版本、处理状态、Git 范围、测试或构建证据；
- 中央“交付核验”：Claim、资料证据、代码证据、核验状态和覆盖范围；
- 右侧标签：“核验详情 / AI 问答 / 交付记录”。

代码证据采用三级展示：后台自动分析、页面精简结论、点击后打开只读高亮 Diff。Diff 必须展示文件、Commit、Hunk、行号精度、关联验收条件和解释；无法定位时明确显示文件级或不可定位。

页面必须同时区分：

- 资料处理状态；
- 分析运行状态；
- 单条核验状态；
- 报告审批状态。

不能用一个“通过”标签掩盖节点失败、未分析范围或证据不足。首版使用轮询更新分析进度，不引入 WebSocket/SSE，除非下一次设计能证明必要性。

## 19. 可观测性、测试与评测

运行日志至少关联 `project_id/task_id/run_id/node_id/model_call_id/correlation_id`，记录节点耗时、失败类型、重试和 Token。人工审计日志与运行日志分开。

首版使用确定性 `FakeModelAdapter` 和固定样例保证离线可演示；Gemini 是可选真实适配器。不得让网络、配额或 API Key 成为演示闭环的唯一前提。

最小评测集至少包含：

- 完全支持；
- 部分支持；
- 证据冲突；
- 无证据；
- 非法 Evidence ID；
- 无精确代码行；
- 模型不可用；
- 结构化输出非法；
- 节点中断恢复；
- 输入快照过期；
- 越权检索；
- 文档中的提示注入。

硬性验收指标：

- 已发布 ReportItem 的引用可解析率为 100%；
- 越权证据泄露为 0；
- 纯模型推断直接进入 `CONFIRMED` 的数量为 0；
- 提交者审批自己的报告必须被拒绝；
- 节点失败不能显示为完整分析成功；
- 全新 Compose 环境可以从迁移开始走到发布样例报告。

首版不引入 Phoenix 等独立观测平台，使用数据库运行事件、结构化日志和评测夹具即可。

## 20. 明确推迟的能力

首版不设计或不实现：

- 微服务、服务网格、Kubernetes；
- Kafka、Temporal、Redis/Celery；
- Neo4j 或独立向量数据库；
- LangChain 全家桶、通用 Agent 或自由多 Agent；
- 模型训练、微调和私有模型平台；
- 在线 IDE、代码执行、自动修复和自动提交；
- 完整 SAST/DAST 或依赖漏洞平台；
- Webhook、PR Bot、多平台消息通知和 SVN；
- 多仓库联合分析；
- OCR、复杂表格识别和全格式解析平台；
- 企业级多租户、计费、SSO 和完整组织管理；
- 实时多人协作、通知中心、BI 大屏和移动端专项适配。

这些能力不得进入首版依赖、核心表结构或首月计划。

## 21. 下一次对话必须完成的设计制品

下一次对话只允许创建或更新架构文档，不编写业务代码、安装依赖、启动容器或执行迁移。必须产出两份主文档：

### `docs/architecture/DevProof-v1.md`

至少包含：

1. 产品边界和质量目标；
2. 系统上下文图、容器图、模块依赖图；
3. 推荐仓库目录树和每个目录职责；
4. 后端分层及依赖规则；
5. 核心领域模型、字段级数据字典和 ER 图；
6. 四套状态机、合法迁移及守卫条件；
7. 统一证据协议和引用校验；
8. 不可变快照、运行清单和报告版本规则；
9. API 资源、核心请求响应、分页和错误模型；
10. PostgreSQL Job、租约、心跳、幂等和恢复；
11. LangGraph typed state、节点、条件边和失败语义；
12. 文档、Git、检索和模型网关设计；
13. AI 问答读取模型和引用约束；
14. 认证、RBAC、审批和发布不变量；
15. 前端三栏数据流与服务端状态映射；
16. 安全、提示注入、敏感信息和只读仓库边界；
17. 审计、运行可观测性和错误分类；
18. Compose 拓扑、卷、环境变量和健康检查；
19. 测试、评测、故障场景和端到端验收；
20. ADR 决策表、默认值、风险和推迟项。

### `docs/architecture/implementation-plan-v1.md`

至少包含：

- 一个月按周拆分的目标；
- 每周可演示结果；
- 最小垂直切片顺序；
- 每个切片涉及的前端、API、数据和测试；
- 每个切片的完成定义；
- 中文 Git 提交名称；
- 推送前验证清单；
- 后续对话可以直接领取的第一个实现任务。

## 22. 下一次对话强制执行顺序

1. 只读检查目录、Git 远程、分支、工作区、已有文件和 `AGENTS.md`。
2. 输出仓库基线、设计范围和采用的默认假设。
3. 自顶向下完成系统上下文、进程、模块、领域模型、状态机、证据协议、API、异步任务、LangGraph、基础设施、前端、安全、部署和评测设计。
4. 每个 P0 决策写明最终选择、理由、放弃方案、影响和扩展点，不得留下 `TBD`。
5. 沿完整业务路径做端到端一致性走查。
6. 对照本文第 23 节逐项验收。
7. 最终只汇报设计文档、核心决策、验收结果、推迟项和第一个实现切片；不得顺手开始编码。

## 23. 架构设计完成验收清单

### 范围

- [ ] Git 被建模为多源证据之一，而不是整个产品中心。
- [ ] 没有引入第 20 节排除的重型能力。
- [ ] 一个需求到一份正式记录的闭环完整。
- [ ] 首月存在可交付、可演示的最小垂直切片。

### 数据与追溯

- [ ] 正式报告可追溯到唯一不可变 InputSnapshot。
- [ ] 资料版本、Git SHA、工作流、Prompt、模型和 Schema 均可追溯。
- [ ] Claim、EvidenceItem、ClaimEvidenceLink、VerificationResult 职责清晰。
- [ ] 支持、反驳、上下文、冲突、证据不足和推断都能表达。
- [ ] CitationResolver 能拒绝不存在、越权或不属于当前快照的 Evidence ID。
- [ ] 无精确位置时不会虚构页码或代码行号。
- [ ] AnalysisCoverage 能区分“未发现”“未分析”和“分析失败”。

### 状态与恢复

- [ ] 资料、分析运行、核验轮次和报告版本状态完全分离。
- [ ] LangGraph checkpoint 不承担正式审批状态。
- [ ] Job 具有幂等、租约、心跳、超时、取消和有限重试。
- [ ] 输入变化不会覆盖旧分析和旧报告。
- [ ] 部分失败有明确状态、覆盖范围和前端表现。

### AI 与权限

- [ ] 图只用于一次核验编排，节点只交换结构化协议。
- [ ] 领域层不依赖 LangGraph/LangChain/Gemini 类型。
- [ ] 交付一致性判断发生在 Claim 形成之后。
- [ ] 模型不可用和非法输出不会产生伪结论。
- [ ] AI 问答只读并带权限过滤、事实状态和引用。
- [ ] 提交者不能审批自己的报告。
- [ ] 审批绑定报告哈希和快照哈希，发布后不可变。

### 运行与验证

- [ ] Compose 组件、卷、端口、迁移和健康检查明确。
- [ ] 密钥只通过环境变量或 Secret 注入。
- [ ] 业务、解析、Git、模型和系统错误有稳定分类。
- [ ] 评测覆盖确认、部分支持、冲突、证据不足和失败恢复。
- [ ] 自动化测试覆盖状态机、越权、引用、幂等和恢复。
- [ ] 有从全新环境到发布样例报告的完整验收路径。
- [ ] 后续每个实现切片都有中文提交名称。

任一 P0 项未通过，不得宣布完整架构设计已完成。

## 24. 停止规则

下一次对话仅在以下情况停止并询问用户：

- 实际 Git 远程不是 `yyy2045/one.git`；
- 目录出现与本方案冲突的其他项目或不明未提交修改；
- 需要删除、覆盖或迁移用户已有内容；
- 仓库级约束与本文发生不可兼容冲突；
- 必须获得账号、密钥或外部系统权限才能完成设计。

以下情况不得成为停止理由：仓库为空、Gemini 未配置、Docker 未启动、UI 库未选择、日志库可替换或非 P0 扩展项尚未实现。应采用本文默认值、记录假设并继续完成设计。

## 25. 后续实现顺序参考

下一次对话需要把它细化成一个月计划，本轮只固定主顺序：

1. `搭建前后端与数据库运行骨架`
2. `建立任务与输入快照领域模型`
3. `实现证据协议与引用校验`
4. `实现资料接入与检索基础流程`
5. `实现Git范围冻结与差异证据采集`
6. `实现核验工作流与失败恢复`
7. `实现报告审批与版本发布`
8. `实现三栏交付核验工作台`
9. `实现只读问答与证据引用`
10. `补充评测样例与部署文档`

每一批都必须形成最小可验证闭环，不一次性推送大量尚未连通的目录壳。

## 26. 可直接复制到下一次对话的提示词

```text
继续 AI-CodeReview 项目。请先完整阅读：
D:\秋招项目\AI应用开发项目\one\docs\specs\2026-08-01-ai-codereview-architecture-design-brief.md

本轮我明确授权你在只读检查仓库后创建或更新架构文档。唯一目标是完成 AI-CodeReview v1 的完整架构设计；不要编写业务代码、安装依赖、启动容器、执行数据库迁移或顺手搭建项目骨架。除非发现真实仓库冲突或需要覆盖已有内容，否则不需要再次等待我确认范围。

请使用实际项目根目录：D:\秋招项目\AI应用开发项目\one
远程仓库：https://github.com/yyy2045/one.git
项目名称：AI-CodeReview
副标题：面向研发交付的多源证据核验与交付记录系统
zhao-zg/AI-CODEREVIEW 是误粘贴链接，必须完全忽略。

严格执行约束文档中的固定技术边界、领域不变量、LangGraph 边界、证据协议、状态分离、安全规则、范围排除项和停止规则。先检查目录、Git、远程、工作区、已有文件与 AGENTS.md，再产出：
1. docs/architecture/DevProof-v1.md
2. docs/architecture/implementation-plan-v1.md

完整设计必须关闭所有 P0 决策，不得以 TBD 或提问清单结束。完成后沿“任务创建→输入快照→分析运行→证据核验→报告草稿→审批→发布→新版本”做端到端一致性走查，并逐项填写约束文档中的架构验收清单。

最终只汇报仓库基线、生成的设计文档、核心决策、验收结果、明确推迟项和第一个最小实现切片。不要在同一轮开始编码。后续实现必须按最小闭环提交和推送，所有 Git 提交说明使用中文。
```
