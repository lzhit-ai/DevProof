# AI-CodeReview 双人协作开发功能清单与承接上下文

> 更新日期：2026-08-26
> 基线：`main@8321185`；文档更新时工作树干净。
> 判断口径：明确区分“代码已实现”“已部署/迁移”“已做定向验证”“真实外部服务已验收”。完成度是当前目标闭环程度，不是测试通过率。

## 1. 产品边界与当前可操作主流程

产品定位：辅助开发团队基于真实 Pull Request、项目知识库和冻结证据审查一次代码交付，并形成可回放的人工批准记录。项目知识库是独立的、面向项目资料理解与追溯的能力；交付核验只是从其中选择并冻结资料版本的下游消费者。

当前用户主流程：

`创建项目并登记 GitHub/Git 仓库 -> 同步 GitHub Pull Request -> 从 PR 创建审查任务 -> 上传/选择知识资料 -> DeepSeek 提取并人工确认交付主张 -> 冻结同源 PR Diff -> 创建正式快照 -> 启动固定双核 -> 查看交付结论、代码 Finding 与证据 -> 完成人工裁决 -> 保存/提交报告 -> 不同成员审批 -> 管理员固化记录`。

非目标：项目整体完成度、安全认证、CI 成功率、任意命令执行、写 Git/PR、替用户自动批准交付。

## 2. 8 月 24—26 日变更总览

| 状态 | 变更 |
| --- | --- |
| 已提交 | 多格式知识库、只读 Git 仓库列表/冻结制品、PR 驱动的代码交付、交付主张确认、固定代码审查/反证核心、Notebook 真实数据流、项目创建接入、工作台导航重构。 |
| 08-26，已提交 `f67f59e` | `032_human_verification_decisions` 迁移；人工裁决 API/报告门禁；草稿报告正文回看 API 与 Notebook 展示；审批页正文和冻结引用展示。 |
| 已部署到本地 Docker | 08-26 已重建 API 并运行迁移 032；当前 API 健康。前端使用 compose bind mount，刷新即可加载当前源码。 |
| 验证证据 | 最近运行：后端编译、报告回归测试（2 passed）、前端 `npm run build`、API OpenAPI 路由检查；8-25 曾做公开 GitHub + DeepSeek 的人工 E2E。仍非完整自动 E2E。 |
| 08-26，已确认产品方向 | 知识库不再以“验收资料上传列表”为终态，后续按 NotebookLM 的来源、选择、引用问答和知识产物体验演进；不接入或依赖 NotebookLM 本体。用户自主 Agent 编排后移，不进入近期交付核验主线。 |

## 3. 功能拆解与进度清单

| 模块/组件 | 已实现部分 | 当前进度 | 后续开发方向与待办（按具体缺口） | AI 承接提示（数据流/约束） |
| --- | --- | --- | --- | --- |
| 项目、登录与上下文 | JWT 登录；项目创建时可登记 GitHub 连接和只读 Git URL；`project-context.ts` 传 `X-Project-Id`；工作台全页项目选择与无项目引导。 | 75% | P0：`/auth/me`、真实当前用户/项目角色投影、成员列表/邀请/移除 UI；项目切换取消在途请求；移除固定演示用户文案。 | 后端 `ProjectMember` 是最终权限边界；前端隐藏按钮不能代替 RBAC。创建项目后的两人审批路径目前仍依赖已有成员数据。 |
| GitHub 连接与同步 | 公开仓库可无 Token；私有仓库使用环境变量引用；同步 Issue/PR/Milestone，写 `ExternalResource` 与 revision；设置页显示连接/同步状态。 | 78% | P0：同步历史、分页继续、限流 reset 时间/重试动作；连接测试、禁用/恢复；私有仓库真实 PAT 验收。 | GitHub 连接用于同步业务对象；`GitRepository` 是独立的只读代码仓库登记，二者不要混为一张表或一条流程。 |
| 代码交付项 | `DeliveryItem` 只投影 `PULL_REQUEST`；任务中心过滤 PR；从 PR 创建 `VerificationTask` 与首个 `VerificationCycle`；Issue 只作背景。 | 88% | P1：PR 更新后提示“已有新 revision，当前轮次仍绑定旧版”；关闭/重开/合并状态的 UI 策略；PR/Issue 关联的可读展示。 | `VerificationTask.delivery_item_id` 已强制是 PR；不可恢复“任何 Issue 可直接创建代码审查”的旧路径。 |
| 项目知识库：导入、版本与来源 | `.txt/.md/.csv/.json/.yaml/.xml/.html/.pdf/.doc/.docx/.xls/.xlsx/.ppt/.pptx/.odt/.ods/.odp` 与常见图片；原文件和抽取文本存 artifact；异步解析、OCR 门槛、chunk、向量失败时 lexical 降级；版本、状态、原文/快照引用 UI。 | 82%（资料可靠性）；35%（Notebook 知识体验） | P0：用用户目录真实样本做格式矩阵、损坏文件/超页/OCR 低置信测试；显示可操作失败原因与重试；大文件流式上传/进度。P1：以“项目总览 Notebook + 可选主题 Notebook”组织来源；来源启停/多选范围；带精确引用的资料问答；保存笔记、摘录和知识产物（需求摘要、FAQ、验收清单、待澄清项）；重复文件提示、版本对比、批量上传队列。暂不做音视频、Web 自动检索、公开分享、音视频/幻灯片生成。 | `SourceRevision` 是版本，不覆盖旧内容。`READY` 即便 embedding 不可用也可用于正式快照；不可伪造向量。知识库问答只能基于用户选中的来源并给出原文定位；它不能创建正式交付结论。核验只能选择并冻结具体资料版本，不能读取未来变动的 Notebook 内容。 |
| 交付主张候选与确认 | DeepSeek 根据 PR 描述/资料生成候选 `DeliveryClaimDraft`；用户选择、编辑、确认；正式快照强制至少一个 CONFIRMED。 | 78% | P0：候选提取的幂等/版本策略和“再次提取”差异提示；主张来源 UI 展开；人工新建主张的校验。 | 当前模型候选是辅助输入，主张进入正式快照前必须人工确认；不要把模型候选直接当交付结论。 |
| 只读 Git 冻结与制品回放 | 仓库登记/列表；同源 PR 约束；TWO_DOT/THREE_DOT、路径范围、空 Diff 拒绝；完整 Diff + code-change bundle 持久化；`GET /git-snapshots/{id}/diff` 回放。 | 90% | P1：冻结进度/大小上限与取消；历史制品清理策略（需先定义保留期）；SSH 私钥/企业 GitLab 等凭据接入方案。 | 详见 `2026-08-25-delivery-code-review-core-v2.md`。分析阶段只读本地 artifact，禁止重新查询远端 Git。 |
| 正式输入快照 | `InputSnapshot` 固定 PR revision、已确认 Claim、READY 资料、Git 制品 hash、可选外部/人工证据；明细绑定表和 EvidenceItem 均已创建。 | 86% | P0：快照 manifest 下载/详情 UI；缺失 artifact 的修复说明；主张/资料/PR revision 更新后的新轮次引导。 | 任何输入变化都应创建新 cycle/snapshot/run，不能修改旧正式快照。Preparation snapshot 与 Formal snapshot 不可混用。 |
| 运行编排与真实模型 | PostgreSQL Job + Worker；运行、事件、编排快照、模型调用记录；固定双核；每 3 秒轮询；DeepSeek 唯一 P0 生成模型；无 Key/失败真实展示。 | 80% | P0：运行取消/重试的页面闭环与 worker fencing；模型 JSON schema 失败的可读恢复；重启后 Job 恢复演练。P1：运行列表/历史筛选。 | API 只入队，Worker 执行。模型失败写 `ModelCall/AnalysisCoverage/Manifest degradation`，不得切 Fake/Gemini。 |
| 代码审查与反证 | 从冻结 hunk 建 CODE Evidence；DeepSeek 生成校验后的 `CodeReviewFinding`；再对 Finding 反证复核；Coverage 汇总范围/跳过原因；Notebook IDE 风格 Diff 与 Finding 展示。 | 87% | P0：更多真实公开/私有 diff 样本的 Finding 回归；Finding 跳转到 hunk；结论与 Finding 的联动解释。P1：Finding 人工处置状态和修复后新轮次关联。 | Finding 不等于交付结论。Challenge 只可 `SUPPORTED/UNSUPPORTED/NEEDS_HUMAN`，不可生成新 Finding 或改原始 Finding。 |
| 交付结论与人工裁决 | 系统 `VerificationResult`；`HumanVerificationDecision` 追加记录、允许动作矩阵、裁决后前端显示有效状态、报告提交门禁。 | 85% | P0：为裁决动作写后端回归；增加裁决历史/撤销语义；统一报告、Notebook、交付记录对有效状态的投影。 | 系统原始结论不可覆盖；人工裁决通过 `supersedes_decision_id` 链追加。仅终态运行、报告未提交可裁决。 |
| 报告草稿与提交 | 自动/手动报告草稿、乐观版本锁、报告项快照、冻结引用、提交说明、提交前裁决门禁；report content API/Notebook 预览。 | 88% | P0：报告 item 处置项编辑 UI；报告内容 API 回归；明确代码 Finding 是否纳入报告 schema（当前只包含主张结果与引用）。 | 报告正文必须读 `ReportItem.result_snapshot`，不能根据当前 live result 重算。`content_hash` 覆盖结果、人工裁决、说明和处置。 |
| 审批与正式记录 | 提交者不能自审；REVIEWER/ADMIN 批准/驳回/要求补证；补证复制新 draft；ADMIN 发布 `PublishedRecord`；审批页先显示冻结报告正文与引用。 | 86% | P0：不同账户真实双人审批 E2E；正式记录详情回放报告正文/引用/审批操作；审批状态变更通知。 | 审批哈希是完整性校验，不是审批对象。正文读取失败时审批按钮必须禁用。发布后不可回写。 |
| 交付记录与回放 | 正式记录列表/详情、报告和快照关联的基础投影已存在。 | 65% | P0：把 report-content 投影接入记录详情；显示证据、Diff、审批理由和 artifact 可用性；历史 V1 明确 `replay_limited`。 | 不可用当前数据“补算”历史内容；缺 artifact 要显式标记不可完整回放。 |
| Agent 功能块 | 固定核心 + `SHARED` 外围 Agent block、工具白名单、运行编排快照有后端/页面基础；但当前产品不应向普通用户暴露自由编排。 | 50%（技术基础，非近期产品能力） | P3：后置到交付核验、知识库、CI 证据和项目视图稳定之后。届时只评估管理员可配置的受控外围能力块、版本与审计；当前应隐藏/隔离 `/agent-blocks` 入口，不继续扩展用户创建、排序或 Prompt 编排。 | 核验三段核心、审批、发布不可删除/替换/绕过。禁止任意 HTTP、代码执行、扫描器接口。任何恢复计划必须先定义角色、工具白名单、输入/输出 schema、运行快照与审计边界。 |
| 项目态势、安全与质量 | 有项目态势、安全基线、摘要草稿等页面/服务基础。 | 35% | P2：先重新定义与“交付核验”关系；未完成数据/真实扫描前不要展示完成率、安全通过结论。 | 当前 P0 不包含安全基线、全项目态势或 CI 工件。避免把它们混入交付结论。 |
| 前端体验与可观测性 | 左侧导航简化；项目空态创建引导；页面滚动规则；Notebook 三栏、运行记录弹层、报告/人工裁决 tabs；当前审批页内容化。 | 70% | P0：逐页检查无项目、无 PR、无 READY 资料、空 Diff、模型不可用、限流；删除无 handler 按钮；统一加载/错误/重试。P1：响应式和键盘可达性。 | 用户应从“代码交付”开始，而不是先猜资料库。普通页面偏线性布局，Notebook 仅作为任务钻取。 |
| 测试、迁移与交付 | Alembic 001—032 已提交；7 个后端测试文件；前端 build 已验证。 | 60% | P0：迁移 032 回归；Git/快照/人工裁决/报告正文 API 测试；知识库格式矩阵；最小 browser->API->DB->artifact E2E。P1：Vue 组件测试、Playwright 主链。 | 每项更改先执行目标测试，避免以容器健康或构建成功代替主链验收；真实 Key 只在本地忽略环境使用。 |

## 4. 优先级实施队列

| 优先级 | 必须完成的切片 | 验收标准 |
| --- | --- | --- |
| P0-1：稳定已提交的人工裁决与报告回看 | 补 migration 032、人工裁决、报告正文 API 的回归测试，并在新数据库验证部署。 | 新库迁移到 032 后，提交者/审核者可分别裁决、看草稿、看审批正文；hash 与正文一致。 |
| P0-2：双人身份/成员闭环 | `/auth/me`、成员管理、创建项目后邀请 reviewer、前端角色门禁。 | 不能自审；第二账户可看到同项目待审批并完成批准/补证。 |
| P0-3：知识库可靠性 | 用真实文件目录建立格式矩阵、失败/重试与上传进度。 | 每种宣称支持格式有成功/失败样本、原件/抽取文本/状态可查看，失败不变成 READY。 |
| P0-4：完整可回放正式记录 | 记录详情复用报告正文、引用、Diff、审批链；制品缺失显式失败。 | 发布后在“正式记录”可回放报告和证据，不依赖 live run/当前 GitHub。 |
| P0-5：最小真实 E2E | 公开 PR -> 资料 -> Claim -> Diff -> run -> 报告 -> 异账号审批 -> 发布。 | 每个前置失败有真实错误和下一步；保留一次成功和一次模型不可用的证据。 |
| P1：运行与协作效率 | 取消/重试、同步继续、PR revision 提醒、Finding 人工处置、新轮次关联。 | 用户能恢复失败/变化输入，不会误把旧快照当新 PR。 |
| P1：Notebook 化项目知识库 | 项目总览 Notebook、来源选择、带引用问答、笔记与知识产物；资料阅读与原文定位完善。 | 用户可基于选中资料理解项目，任何回答能回到来源；核验仍只消费冻结资料版本。 |
| P1：体验与质量 | Vue 组件测试、Playwright、可访问性、响应式、状态反馈统一。 | 关键按钮都有 handler/API/回读；无横向溢出和无项目死页面。 |
| P2：非 P0 工作台能力 | 项目态势、安全基线、指标/通知。 | 仅在数据来源和产品语义明确后实现；不得声明安全通过或项目完成。 |
| P3：受控 Agent 扩展 | 管理员可配置的外围能力块、版本、审计和模板；不开放普通用户自由编排。 | 必须在核心核验、知识库、CI 证据和权限模型稳定后另立设计并验收。 |

## 5. 全局代码规范与约束

1. 架构方向固定为 `FastAPI route -> application service -> domain/port -> infrastructure adapter`。route 只做 DTO、依赖、事务和错误映射；业务规则不可写入 Vue 或 route。
2. PostgreSQL 是状态事实源；artifact storage 保存原件和大制品；Worker 只消费持久 Job。LangGraph 运行状态不是报告/审批/发布事实源。
3. 新迁移只能追加，历史快照、报告、批准和正式记录不得改写。所有写接口使用 `Idempotency-Key`，并在服务层校验角色、归属、状态、版本。
4. Git 只读；禁止新增任意 shell/构建/测试/扫描/任意 HTTP 执行接口。模型只调用受控 adapter，P0 代码审查只允许 DeepSeek。
5. 错误必须保留 machine code，前端按 code/state 处理，不能从中文 message 猜状态；页面的错误态给实际下一步但不伪造成功。
6. Vue 3 使用 `<script setup lang="ts">`；共享项目/API 状态在 feature context，页面只留页面态。普通页使用轻量线性信息布局，Notebook 为任务钻取页；不保留没有真实 handler/API 的按钮。
7. 修改前区分 `HEAD`、已暂存、未暂存、未跟踪。当前工作树是用户资产，禁止 `git reset --hard`、`git checkout --` 或覆盖式清理。

## 6. 接手操作清单

1. 阅读本文件和 `2026-08-25-delivery-code-review-core-v2.md`，随后检查 `git status --short` 与 `git diff`。
2. 先确认数据库 migration 版本和 Docker API/worker 镜像是否包含当前源码，再测试页面；不要把浏览器缓存当作唯一解释。
3. 处理 P0-1 时仅提交本次人工作裁决/报告回看相关文件，避免把用户无关改动混入提交。
4. 每完成一个优先级切片，更新本表的状态、验证命令和未验证外部条件。
