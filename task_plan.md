# Task Plan: 可信边界补强

## 2026-09-01 PR 交付核验 LangGraph 编排设计

### Goal

基于当前 PR 交付核验业务流程，设计一套面试可解释、工程可落地的 LangGraph 固定证据主链；输入仅包含 PR、人工确认的交付主张、可选知识库资料和冻结 Diff，不依赖 CI，并将人工介入收敛到关键冲突与最终审批。

### Phases

1. 重新核对现有项目、LangGraph 主链和报告审批边界。`complete`
2. 与用户确认用途、输入范围、固定主链和人工介入边界。`complete`
3. 比较编排方案并确认“固定主链 + 可选外围 Agent”。`complete`
4. 完成架构、节点、State、路由、失败、审计和测试设计。`complete`
5. 写入规格文档并执行占位、矛盾、歧义与范围自检。`complete`
6. 提交独立中文设计提交并等待用户复核。`complete`

### Fixed Decisions

- LangGraph 只负责自动核验，不使用 interrupt 承载人工审批。
- 核心输入为 PR、确认主张、可选知识库资料和冻结 Diff，不依赖 CI/测试平台。
- 固定核验主链不可被普通用户改写；外围 Agent 只能输出建议。
- 普通部分支持、证据不足和低中风险 Finding 不触发逐项人工裁决。
- 只有关键冲突、高风险业务歧义和最终正式审批需要人工责任确认。
- `SUPPORTED` 仅表示当前冻结代码证据支持，不代表运行、测试、上线或生产验证通过。

### Error Log

- 首次合并补丁因误判 `progress.md` 首行标题为“项目进度”而失败；实际标题为“进度记录”。该补丁未产生部分写入，已改为按文件精确锚点分步写入。

## 2026-08-12 可信边界补强

### Goal

修复已发布报告回退、重复正式快照输入和跨仓库交付归属缺口；补齐 GitHub 大仓库/私有仓库只读接入、资料检索索引迁移、自动化回归与运行观测，不突破固定双核、冻结 Git Diff 和人工审批边界。

### Phases

1. 方案文档、自检与用户复核。`complete`
2. 锁定已发布核验周期并覆盖状态机回归。`complete`
3. 收紧正式快照与事项—Git 仓库归属。`complete`
4. 完善 GitHub Cursor 同步与私有只读凭据通道。`complete`
5. 实现活动索引重建及模型迁移检索语义。`complete`
6. 补齐自动化回归、运行观测、功能与进度文档。`complete`

### Fixed Decisions

- 先实现 GitHub Fine-grained PAT 的环境变量引用通道；GitHub App 留作后续团队化扩展。
- 默认严格同仓库关联，不新增跨仓库豁免。
- 向量迁移以新建派生索引版本实现，绝不改写既有资料版本、快照或发布记录。
- 每个完成切片单独中文提交，不推送。

# Task Plan: AI-CodeReview 架构约束文档
## 2026-08-12 百炼真实 Embedding 切换

### Goal

将资料向量化从本地 FakeEmbedding 切换为百炼 `text-embedding-v4`（固定 768 维），保持生成模型与 Embedding 模型独立，并保留真实供应商适配扩展位。

### Phases

1. 核对当前向量列、检索链路、模型端口和百炼 OpenAI 兼容地址。`complete`
2. 新增百炼 Embedding 适配与真实运行配置，禁止运行配置选择 FakeEmbedding。`complete`
3. 更新示例配置、功能文档和进度记录，做静态验证并中文提交。`complete`
4. 由用户本机 Worker 执行最小真实 Embedding 调用，确认供应商、模型和维度。`complete`

## 2026-08-12 Gemini 临时全链路验收

### Goal

仅在本地被 Git 忽略的运行配置中使用 Gemini API Key，修正 Gemini Embedding 的固定 768 维请求，并用隔离验收资料验证资料入库与语义检索。验收完成后恢复本地默认 Embedding 配置为百炼；提交不得包含 Gemini Key。

### Phases

1. 使 Gemini 适配器显式请求 768 维，并确认容器 SDK 支持该配置。`complete`
2. 以临时 Gemini 配置写入隔离验收资料，检查 READY、分块、向量与索引版本。`complete`
3. 以语义改写问题走实际检索器，确认命中资料且存在 `vectorRank`。`complete`
4. 恢复本地百炼默认配置，更新验收记录、静态检查并提交不含 Key 的代码与文档。`complete`

### Error log

- 规划文件在当前终端显示为乱码，无法用标题作补丁锚点；已改用首个空行定位，未改动既有历史内容。
- `docker compose up -d --build api worker` 在命令执行窗口 64 秒后超时；下一步先检查镜像与容器状态，再采用恢复启动或分步构建，避免重复同一条超时命令。
- 后台 `docker compose build api worker` 已退出，但 Compose 查询镜像时返回缺失的 SHA；现有容器仍健康运行。下一步改为直接读取 Dockerfile 并以带输出的单镜像构建定位原因，不重跑无输出的后台构建。
- 百炼最小 Embedding 实调用在 Worker 内收到 `SSL: UNEXPECTED_EOF_WHILE_READING`，适配器已如预期转换为 `MODEL_UNAVAILABLE`；不立即重试相同请求，改为分别检查宿主机与容器到用户专属 Host 的 TLS/DNS 连通性。
- 后台构建实际已产出新镜像；使用 `docker compose up -d --no-build --force-recreate api worker` 后，两个容器均已换成新配置，API 健康检查通过。百炼 Host 的 TLS 链路是唯一未验收项，等待外部网络条件恢复。
- 用户切换网络后，宿主机与 Worker 的 TLS 检查均通过；随后项目真实适配器返回 `dashscope / text-embedding-v4 / 768`。此前 TLS 异常已解除，真实资料上传与检索全链路仍不在本次最小调用验收范围内。
- Gemini 原生 API 已由当前执行通道真实调用成功。首次请求把维度字段放在错误层级，服务端返回默认 3072 维；改为顶层 `outputDimensionality=768` 后返回 768 维。后续项目适配器必须使用 SDK 对应的 `EmbedContentConfig(outputDimensionality=768)`，不重复错误请求格式。
- 首次完整验收因本地数据库仅停在 014 迁移而在创建任务时回滚；升级时又发现 `alembic_version.version_num` 的 32 字符上限无法写入 017 的修订标识。已在 015 迁移中先扩为 64，并已成功升级本地开发库至 023；未重写既有业务数据。
- 将上传、冻结和检索放进同一个未提交 SQLAlchemy 会话时，关闭自动刷新的会话使快照看不到刚加入的分块，验收事务已回滚。后续按真实 API 的三个独立提交边界执行，不重复该组合方式。
- 按真实的三次请求提交边界重新验收后通过：资料为 `READY`，产生 3 个固定 768 维 Gemini 向量和 3 条快照 `DOCUMENT` 证据；语义改写问题返回 3 条结果且包含 `vectorRank`。验收使用隔离的本地任务、资料与快照记录；随后运行配置已恢复为百炼。

## 2026-08-12 双核编排运行修复

### Goal

修复固定双核在创建分析运行时错误判定“编排已变更”的问题；保持需求/验收核心、冻结 Git Diff、确定性裁决和人工确认边界不变，并以真实 Worker 运行核验。

### Phases

1. 定位预检哈希与冻结编排快照哈希的字段差异。`complete`
2. 统一两处哈希输入，不改变编排节点和历史数据。`complete`
3. 使用隔离资料与公开只读 Git Diff 启动 Worker，核验 Claim、代码证据、裁决和报告草稿。`complete`
4. 更新功能文档、进度记录、静态检查并中文提交。`complete`

## 2026-08-12 第一性原则全链路复核

### Goal

不以“页面可见、代码存在或单点成功”代替可用性。按输入授权与冻结、资料与向量、Git Diff、双核编排、确定性裁决、报告/审批/发布、项目态势与安全质量外围运行逐段验证；每项只记录实际通过、实际失败或尚未覆盖的范围。

### Phases

1. 建立链路清单、确认运行配置、数据库版本和已有验收记录。`complete`
2. 复核资料入库、Embedding 索引隔离、快照检索和证据冻结。`complete`
3. 复核 Git 只读冻结、模板锁定、双核运行、裁决分支和报告草稿。`complete`
4. 复核提交、审批、发布、正式记录与项目事项状态回写边界。`complete`
5. 复核外围 Profile、授权/私有仓库缺口和前端/API 可达性；汇总通过、失败和未覆盖项。`complete`

## 2026-08-11 目标执行异常

| 情况 | 处理 |
| --- | --- |
| Windows PowerShell 下对不存在的 `models.py` 与未展开的 `*.py`/`router*` 路径执行 `rg` | 已用 `rg --files` 确认实际模型文件，并把后续 glob 交给 `rg --glob` 处理；没有修改任何业务文件。 |
| 用 PowerShell 的中文文本定位计划段落受当前输出编码影响失败 | 改为以 `apply_patch` 的稳定标题定位；不改变计划内容与执行范围。 |
| 在仓库根目录运行 `npm run build` 找不到 `package.json` | 前端包实际位于 `frontend`；后续改在该目录执行构建，不重复根目录命令。 |
| 误用了第 021 个迁移的简写文件名 | 已按实际 `021_agent_tool_execution_evidence_boundary.py` 文件名读取；不会重试不存在的路径。 |
| 在 `frontend` 子目录执行后端 `.venv` 路径 | 前端构建已完成；后端 `compileall` 改回仓库根目录执行。 |

> 历史计划已于 2026-07-31 完成。以下为 2026-08-10 的当前规划任务。

> 2026-08-10：用户已授权按该方案开始开发。不运行测试套件、不推送远端；每个完成的功能切片单独以中文提交。

## 2026-08-10 当前实现：区分交付核验运行范围

### Goal

实现 `AssessmentProfile` 的交付核验切片：历史数据保持交付核验语义，Git Diff 只在交付核验中强制，模板和 Worker 为后续外围 workflow 预留 Profile 分发边界。

### Phases

当前执行状态：第 3 项安全解释与质量趋势、第 4 项非交付运行配置及第 5 项文档、静态验证与全范围审计均已完成。

1. 审计模型、DTO、快照、分析入口、模板和 Worker。`complete`
2. 增加迁移、枚举/模型和 API 契约。`complete`
3. 收敛快照、分析、编排和 Worker 行为。`complete`
4. 更新功能文档，进行静态检查并提交。`complete`

## 2026-08-10 当前实现：外部来源与研发事项镜像

### Goal

为 GitHub 项目建立只读来源连接、版本镜像、同步记录和研发事项投影；复用既有资料版本作为文档来源，不创建本系统手工任务作为事实替代。

### Phases

1. 审计仓库平台、现有 Git/资料模型与安全请求边界。`complete`
2. 增加来源连接、资源版本、同步记录和交付项迁移/模型。`complete`
3. 实现 GitHub 只读同步、事项投影和 API。`complete`
4. 更新功能文档，进行静态检查并提交。`complete`

## 2026-08-10 当前实现：研发事项与交付变更关联

### Goal

让交付核验任务、GitHub PR 资源和冻结 Git Diff 均可与一个研发事项建立有来源、有状态的关系；平台关系和人工确认可正式计入，Agent 推断只保留候选。

### Phases

1. 审计任务、Git 快照和 GitHub 来源同步入口。`complete`
2. 增加任务归属和事项变更关联迁移/模型。`complete`
3. 实现平台发现、人工确认与关联查询 API。`complete`
4. 更新功能文档，进行静态检查并提交。`complete`

## 2026-08-10 当前实现：项目态势与研发总结

### Goal

以来源同步的研发事项、已确认变更、正式交付记录、历史风险和待归属 Git 活动生成不可变项目态势快照，并基于该快照生成可由个人确认的日报、周报或迭代总结记录；不把活动数量改写成完成结论。

### Phases

1. 审计事项状态、正式交付记录、风险和来源同步之间的可追溯关系。`complete`
2. 增加项目态势快照、总结草稿和个人确认记录迁移/模型。`complete`
3. 实现态势汇总、总结草稿/记录及 API，并让已发布交付记录回写事项核验状态。`complete`
4. 更新功能文档，进行静态检查并提交。`complete`

## 2026-08-10 当前实现：安全与质量基线

### Goal

导入指定仓库 SHA 的扫描/CI 结果、扫描器和规则版本、覆盖范围与结构化风险，冻结为安全基线并经审核者或管理员确认；不执行全仓 AI 读码、不声明项目绝对安全。

### Phases

1. 审计现有 Git、外部证据、风险和人工审批边界。`complete`
2. 增加扫描输入、风险、基线快照和基线记录迁移/模型。`complete`
3. 实现导入、风险处置、基线固化与 API。`complete`
4. 更新功能文档，进行静态检查并提交。`complete`

## 2026-08-10 当前实现：真实项目工作台与导航

### Goal

让开发者从真实项目上下文进入研发事项、交付核验、项目态势、安全基线、审批与正式记录；移除演示 fixtures 和手工 UUID 入口，但不把 PR 关联、计划状态或活动数量伪装成交付完成。

### Phases

1. 增加项目、核验任务、报告与正式记录的项目级只读查询投影。`complete`
2. 建立全局项目上下文，将知识库、Agent 功能块和工作台页面接入真实项目选择。`complete`
3. 完成事项创建核验、态势/安全页面、审批/正式记录详情与真实 Notebook 空状态。`complete`
4. 收紧自定义 Agent 只能作为外围共享能力，删除所有工作台演示数据。`complete`
5. 更新功能文档，进行静态检查并提交。`complete`

## 2026-08-11 当前实现：临时工具结果与正式证据边界

### Goal

将外围 Agent 的运行期 `HTTP_QUERY` 结果从正式 `EvidenceItem` 与报告引用链中移出。工具输出可被 Agent 作为受限审查线索使用，但只有提交人或管理员显式导入为人工补证、选择进入新的正式输入快照后，才可被 Citation Resolver 作为正式证据解析。

### Phases

1. 审计工具运行、模型候选证据、Citation Resolver 和报告草稿链路。`complete`
2. 新增不可直接引用的 `AgentToolExecution`，并禁止其参与核验结果与报告引用。`complete`
3. 提供临时结果读取、显式导入补证 API 和 Notebook 最小入口。`complete`
4. 更新功能文档，进行静态检查并提交。`complete`

## 2026-08-11 目标：未开发功能收口

### Goal

在不突破固定双核、冻结 Git Diff、只读证据与人工确认边界的前提下，完成功能文档中仍标记为“尚未实现”的产品能力。明确不做的任意命令执行、自动构建/测试/发布、无边界全仓读码和任意网络写操作不纳入本目标；真实 DeepSeek 联调需要用户自行配置 API Key，也不以缺少 Key 阻塞本地功能开发。

### Phases

1. 自定义 Agent 生命周期：版本编辑、停用、任务模板绑定的服务端与真实工作台入口。`complete`
2. 事项—变更候选：Agent 在受控输入下仅提出候选，用户确认后才成为正式关联。`complete`
3. 安全解释与质量趋势：只基于已导入、SHA/规则/覆盖可追溯的事实产生解释和时间序列。`complete`
4. 非交付运行配置：为项目态势、安全基线、质量趋势提供专用输入、运行、API 和界面，不复用交付核验双核。`complete`
5. 对每个独立功能切片更新功能文档、静态验证、中文提交；最后进行全范围审计。`complete`

## 2026-08-10 当前任务：总体方向的开发方案

### Goal

以 `docs/lzh/2026-08-10-project-verification-overall-direction.md` 为目标，核对当前实现，明确已完成、需修改、需开发和明确不做的功能，并形成分阶段实施方案；本任务不改业务代码。

### Current Phase

Phase 4 - complete

### Phases

1. **现状审计**：读取总体方向文档、现有架构文档、近期提交和核心代码入口，确认当前真实能力。`complete`
2. **差距归类**：按“保留、修改、开发、明确不做”归类，并识别迁移与兼容约束。`complete`
3. **实施编排**：形成按依赖排序的功能切片、验收条件、中文提交边界和文档更新规则。`complete`
4. **计划自检与交付**：检查是否将项目管理、交付核验、安全治理混淆，并输出可执行计划。`complete`

### Fixed Decisions

- 双核仅作为交付核验主干；外围总结与安全能力不强制运行双核。
- Git Diff 仅在交付核验中锁定为必需输入，不再是全部运行类型的全局前置条件。
- 研发事项/交付项是外部来源同步的结构化对象，不是 Agent，也不以本系统手工内容作为主要事实来源。
- 不修改业务代码、不运行测试、不推送远端，除非用户后续明确授权实施。

## 当前实现中的异常与处理

| 情况 | 处理 |
| --- | --- |
| 首次搜索 DTO 时假定存在 `backend/app/api/schemas/` 目录，实际为单文件 `backend/app/api/schemas.py` | 已改用文件发现并读取正确路径；未修改任何代码 |
| 系统 Python 缺少 `alembic`，无法执行离线迁移 SQL 校验 | 改用仓库 `.venv` 的 Python 解释器；不安装或修改依赖 |
| 仓库 `.venv` 的 Alembic 离线模式仍需加载 `Settings`，当前 shell 未提供 `JWT_SECRET` | 仅为该离线命令注入临时占位 JWT 值；不写入 `.env`，不连接数据库 |
| 事项关联模型补丁按预期锚点未命中，因新增外部来源模型位于文件中段而非任务模型附近 | 先按实际类定义定位后拆分补丁；不覆盖任何现有代码 |
| 从仓库根目录执行 Alembic 配置时，配置内相对的 `script_location=migrations` 无法解析 | 改在 `backend` 目录执行同一离线 SQL 校验；不连接数据库 |

## Goal

生成一份可直接交给下一次 Codex 对话的架构设计约束文档，使下一次对话能完成 AI-CodeReview v1 的完整架构设计，不提前进入业务实现或扩展重型能力。

## Current Phase

Phase 4 - complete

## Phases

### Phase 1: 仓库与需求发现

- [x] 检查仓库、分支和远程状态
- [x] 汇总产品、技术与范围约束
- [x] 将发现写入 `findings.md`
- **Status:** complete

### Phase 2: 方案设计

- [x] 固定模块化单体和独立 Worker 路线
- [x] 固定数据主链、状态机和 LangGraph 边界
- [x] 设计下一次对话的执行协议与验收标准
- **Status:** complete

### Phase 3: 文档生成与自检

- [x] 编写架构设计约束文档
- [x] 扫描占位符、矛盾、歧义和范围漂移
- [x] 检查路径、代码块、空白字符和 UTF-8 内容
- **Status:** complete

### Phase 4: 交付

- [x] 检查 Git 暂存内容
- [x] 使用中文提交说明提交
- [x] 推送到 `origin/main`
- **Status:** complete

## Key Questions

1. 下一次对话的目标是否被限制为“完整架构设计”？是。
2. 是否存在需要兼容的既有代码？否，仓库起始时为空。
3. 是否允许下一次对话提前搭建项目骨架？否，只允许生成架构设计文档与实现规划。

## Decisions Made

| Decision | Rationale |
|---|---|
| 项目根目录使用 `D:\秋招项目\AI应用开发项目\one` | 该目录是实际 Git 仓库并已绑定目标远程 |
| 采用模块化单体、独立 Worker 与 PostgreSQL Job | 满足恢复能力并控制一个月作品集复杂度 |
| 以单份约束文档控制下一次对话 | 集中保存固定决策、默认值、验收清单和复制提示词 |
| 下一次对话产出两份主架构文档 | 分离完整架构与一个月实现计划，避免业务实现提前发生 |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `git log` 返回当前 `main` 无提交 | 1 | 确认为空仓库，按新仓库处理 |
| 默认 `rg` 引擎不支持负向前瞻 | 1 | 改用 `rg --pcre2` |
| Windows 中把 `*.md` 直接拼入绝对路径失败 | 1 | 改为在仓库根目录使用 `rg --glob '*.md'` |
| 首次完成检查显示 `0/0 phases` | 1 | 按技能模板补充标准 Phase 与 Status 结构 |

## Notes

- 本任务只产出文档，没有编写、安装或运行项目业务代码。
- 后续实现必须按最小闭环提交并使用中文 Git 提交说明。
# 2026-08-24 双人协作开发功能清单审查

## Goal

基于当前工作树、现有文档、前后端接口与测试，产出可供另一位开发者及其 AI 无缝承接的高颗粒度标准化上下文文档；严格区分代码存在、界面接入、自动化测试、运行验证与外部联调。

## Phases

1. 盘点仓库状态、文档与技术架构。`complete`
2. 逐模块核对后端模型、服务、路由与 Worker。`complete`
3. 逐页面核对前端路由、接口、交互与状态门禁。`complete`
4. 核对测试覆盖、运行配置、未提交变更与外部条件。`complete`
5. 形成功能拆解、完成度、TODO、Context Injection、协作顺序与全局约束文档。`complete`

## Audit Rules

- 不把文档声明、代码存在、页面按钮、构建通过或历史运行记录等同于当前完整可用。
- 当前工作树存在用户未提交变更；审查须同时覆盖 HEAD 与工作树，不回退、不覆盖、不提交。
- 本轮默认只读审查；除规划记录与最终上下文文档外，不修改业务代码，不主动运行广泛测试。

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| Docker 状态查询无法连接 `docker_engine`，且用户 Docker 配置不可读 | 1 | 将当前运行态标记为“未验证/服务未运行或不可访问”，不把历史容器状态当作本轮证据。 |
| PowerShell 将 `rg` 双引号正则中的 `|` 解析成管道，路径扫描失败 | 1 | 不重复该命令；改用单引号模式或 `Select-String` 获取定位。 |

# 2026-08-25 GitHub 开源代码审查项目采纳调研

## Goal

筛选一个与当前 AI-CodeReview 的只读 Git Diff、证据约束和人工审查方向最接近的完整开源项目，基于其当前源码与官方文档分析可采纳机制、适配方式和不应照搬的边界。

## Phases

1. 搜索并比较仍维护的开源代码审查项目。`complete`
2. 选定目标仓库并核对实际代码结构、审查主链与扩展机制。`complete`
3. 映射到当前项目，输出可采纳项、改造落点与明确排除项。`complete`

## Research Rules

- 优先官方 GitHub 仓库、官方文档和当前源码，不以第三方宣传文章作为实现证据。
- 区分通用 PR 审查产品与当前“Issue 验收目标—冻结 Diff—证据结论—人工审批”产品边界。
- 本轮只调研，不修改业务代码，不引入依赖，不执行外部项目代码。

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| 一次 `rg` 搜索中的双引号模式被 PowerShell 拆分，产生无关“找不到文件”提示 | 1 | 其他精确模式已返回所需定位；未重复失败命令，改用单引号/分项搜索结论。 |
| 完成检查脚本汇总了同一历史文件中的旧任务，显示 `4/18 phases complete` | 1 | 当前调研章节实际为 3/3 complete；保留历史任务状态，不为通过检查篡改旧记录。 |

# 2026-08-25 交付代码审查核心增强

## Goal

参考 PR-Agent 的规范化 Diff、代码上下文、Token Coverage、结构化 Finding 和定位校验机制，把现有锁定的 `delivery-git-diff` 升级为受证据约束的交付代码审查核心；不新增第三核心，不允许模型直接裁决、回写 Git 或执行仓库代码。

## Design Phases

1. 核对当前双核、Git 输入、模型契约、持久化和未提交改动。`complete`
2. 逐项确认本次实现范围、迁移边界和成功标准。`complete`
3. 提出候选实现方式并确认推荐方案。`complete`
4. 分节确认架构、数据流、错误处理和测试设计。`complete`
5. 写入设计规格、自审并等待用户确认。`complete`（规格已由用户确认）
6. 设计确认后制定详细实施计划。`complete`
7. 实施、定向验证并更新承接文档。`complete`（完整运行态验证受 Docker 与本地依赖阻断，已记录）

## Fixed Boundaries

- 保持 `requirement-claim-core`、交付代码核心、`evidence-reconciliation` 三个锁定主干节点；交付代码能力属于现有双核的 DELIVERY 一侧。
- DeepSeek 只生成 Finding/Link 草稿；最终 VerificationResult 继续由确定性裁决生成。
- 不 checkout、不执行构建/测试/Hook、不写 Git、不回写 GitHub 评论或代码。
- 当前工作树有用户未提交变更，实施不得 reset、checkout 或覆盖无关修改。

## 已确认实施计划

1. 追加 028 迁移，增加 `ArtifactObject`、`CodeReviewFinding`、GitSnapshot 制品/范围字段与 Coverage 明细，不改写历史快照。
2. 把 Git 读取升级为“冻结时采集 bytes + 规范化 Bundle”，并从制品而非远端重读中构建代码证据。
3. 新增 Diff Parser、上下文预算、代码审查模型 schema 与服务端 Finding 定位校验；DeepSeek 失败只写受控降级状态。
4. 将 v2 节点接入既有 `delivery-git-diff`，维持确定性链接/裁决和现有报告流程。
5. 新增 GitSnapshot Diff、AnalysisRun CodeReview 的只读投影，Notebook 显示真实 Diff、Finding、Coverage 和失败原因。
6. 编写并运行定向后端测试、后端静态编译、Alembic 离线 SQL、前端构建；用本地临时 Git 仓库验证不执行仓库代码的采集链。

## 2026-08-25 错误记录

| 错误 | 尝试 | 处理 |
| --- | --- | --- |
| 设计规格使用 Markdown 硬换行，被 `git diff --check` 标记为尾随空白 | 1 | 已移除硬换行；后续规格元数据使用普通换行。将修订既有的本地设计提交。 |
| 代码审查模型契约的组合补丁未命中 `generation_model.py` 的长行上下文 | 1 | 未重复该补丁；改为按类和方法的精确定位拆分修改。 |
| Git/分析 API 的组合补丁未命中当前 `schemas.py` 中的定位上下文 | 1 | 未重复该补丁；改为按服务、schema、路由分别补丁，避免影响用户同时修改的 API 文件。 |
| 项目虚拟环境未安装 `pytest`，无法直接执行新增测试文件 | 1 | 不安装新依赖；改用同一虚拟环境以 `runpy` 直接运行纯函数测试，并保留 pytest 测试文件供现有 CI/测试环境执行。 |
| 错误记录补丁缺少结束标记 | 1 | 已改用完整补丁；未影响工作树。 |
| 后端路由导入检查被现有多格式知识库依赖 `bs4` 缺失阻断 | 1 | 不安装或修改环境；已完成 Python 编译、迁移离线 SQL、纯函数测试和前端构建。完整 API 启动验证保留给依赖已安装的容器/CI。 |
| 新增预算测试导入 ORM 时未传入仅用于测试进程的 `JWT_SECRET` | 1 | 不重复无配置导入；以进程内占位 `JWT_SECRET` 重跑，无任何配置文件改动。 |
| 预算测试的 120 字符小于单个结构化 Hunk 的序列化大小 | 1 | 将测试预算调整为 300，仍不足以装入上下文，用于准确验证 Hunk 优先于上下文。 |
| 承接文档首次新增补丁使用了错误的结束标记 | 1 | 已用完整补丁创建文件；未影响工作树。 |
| Docker Desktop Linux Engine 管道不存在，`docker compose ps` 无法读取当前运行态 | 1 | 未重启 Docker 或服务；完整公开仓库/真实 DeepSeek E2E 保留为运行环境恢复后的验证项。 |
| 进度日志中的长中文行未被精确补丁定位 | 2 | 改为稳定章节标题定位插入最终验证记录；未重试相同长行匹配。 |
| API 路径校验先后误读了嵌套路由包装与声明路由器已带 prefix 的路径 | 3 | 已检查实际声明路径；最终按完整 `/analysis-runs/{run_id}/code-review` 与 `/git-snapshots/{snapshot_id}/diff` 校验，不再假设未带 prefix 的子路径。 |
| 真实 Git 范围测试发现 Git 默认转义非 ASCII 路径，Parser 因而未识别 Diff 文件头 | 1 | 受控 Git 命令增加 `core.quotePath=false`，保留 UTF-8 路径后重跑完整测试。 |
| 真实 Git Diff 文件头仍携带分隔制表符，规范化路径被保留了尾随 tab | 1 | Parser 对 Diff 文件头路径移除该格式分隔符；保持文件名中的普通空格不变。 |
| Diff 的 `---`/`+++` 文件头同样携带格式分隔 tab，覆盖了首个 Diff 文件头的解析结果 | 1 | 对旧/新文件头统一移除格式分隔 tab；使用真实临时 Git 仓库回归验证。 |

# 2026-08-25 标准交付核验：实施计划

## Goal

在既有交付代码审查 v2 之上，固化唯一的“标准核验”内置流程：代码 Finding、Finding 反证复核和可解释 Coverage 按固定顺序运行；普通用户不接触 Agent 编排，最终 `VerificationResult`、报告审批和正式记录的可信边界保持不变。

## Fixed Decisions

- 只实现标准核验；不增加快速/深度模式、Agent 画布、用户 Prompt/节点配置或任意工具权限。
- 反证复核是 DeepSeek 的受 schema 约束草稿步骤，不能创建 Finding、改严重度、改 Claim 或写最终核验结论。
- Coverage 只由代码汇总真实范围和失败原因，不输出完成率、全量审查或无风险语义。
- 主链继续只读冻结制品；不 checkout、不执行仓库代码、不写 Git/GitHub，也不回退 Fake/Gemini。
- 当前工作树已有用户未提交变更；每个切片只改必要文件，独立中文提交时只暂存本切片文件。

## Phases

1. **反证契约与迁移**：追加 029 迁移，新增 `CodeReviewFindingChallenge`；定义 verdict 枚举、模型 DTO、Generation Port 和配置预算，保持 028 与历史运行兼容。`complete`
2. **反证服务与模型适配**：在独立服务中校验 Finding/Hunk/Claim/运行归属、生成稳定指纹并持久化；DeepSeek 实现 JSON Schema 调用，其他 Provider 显式受控失败。`complete`
3. **固定图与 Coverage**：在 `review_code` 后接入 `challenge_code_findings`、`summarize_code_coverage`，写 ModelCall、Manifest 降级和标准 Coverage；不修改 `link_deterministic`/`reconcile` 的裁决算法。`complete`
4. **只读投影与 Notebook**：扩展 CodeReview API 返回反证和汇总 Coverage；Notebook 展示标准核验标识、Hunk、四种复核状态、失败原因与下一步。`complete`
5. **定向验证与承接**：补单元/API/组件状态测试，运行后端编译、Alembic 离线 SQL、定向 pytest 和前端构建；Docker 恢复后以真实公开仓库和有效 DeepSeek Key 做 E2E，并更新 handoff/progress。`in_progress`

## Detailed Implementation Order

### Phase 1 — 反证契约与迁移

1. 确认当前最新迁移 revision，新增 `029_standard_verification_challenge.py`，只向前追加表/索引，不改写 028 或历史 Finding。
2. 建立 `CodeReviewFindingChallenge` ORM：`analysis_run_id`、`finding_id`、`verdict`、`reason`、`evidence_ids`、`model_call_id`、`schema_version`、`created_at`；唯一键确保同一 run/finding 不重复成功记录。
3. 在 Domain 层增加 `SUPPORTED`、`UNSUPPORTED`、`NEEDS_HUMAN` 复核枚举及 Pydantic proposal/batch/request/result；禁止新 Finding 或 Severity 字段进入挑战响应。
4. 在 Settings 增加每运行最大复核数、输入字符预算和超时配置，默认保守值；预算耗尽成为可见 Coverage reason code。

### Phase 2 — 反证服务与模型适配

1. 新建 `code_review_challenge_service`，按当前 AnalysisRun 查询既有 Finding、`GIT_DIFF_HUNK` Evidence 和 Claim；验证 ID 均属于同一 Run/Snapshot，拒绝跨运行引用。
2. 生成 `(run, finding, evidence, verdict schema)` 稳定 fingerprint；以幂等写入保留原始 Finding，绝不覆盖或删除。
3. 给 Generation Port 增加 `challenge_code_findings`；DeepSeek Prompt 仅含必要制品和任务约束，要求返回 verdict/reason/evidence IDs。
4. Fake/Gemini/未配置 Provider 统一抛出 `MODEL_NOT_CONFIGURED`，由上层写失败状态；JSON Schema、定位或归属无效时拒绝 proposal 并保留受限错误摘要。

### Phase 3 — 固定图与 Coverage

1. 在 `verification_graph` 的既有 `review_code` 之后插入 `challenge_code_findings`，随后插入 `summarize_code_coverage`，再进入现有 `link_deterministic`。
2. 没有 Finding 时跳过模型调用并写 `FINDING_CHALLENGE/NOT_APPLICABLE`；模型不可用、无效输出、超时、制品缺失均写 ModelCall、Manifest degradation 和 `PARTIAL/FAILED` Coverage。
3. `summarize_code_coverage` 从冻结 Bundle、代码审查 Coverage、Challenge 记录计算文件/Hunk、预算截断、二进制跳过、Finding 与 verdict 数量；不得询问模型。
4. 确认新增节点不读取远端 Git、不写入 `VerificationResult`，取消/重试/幂等语义沿用 AnalysisRun 的既有控制。

### Phase 4 — API 与 Notebook

1. 扩展 `GET /analysis-runs/{runId}/code-review` 的 schema/service，返回每条 Finding 的 challenge（或 `NOT_STARTED`）、关联 Hunk locator、根级 Coverage 和 degradation；不返回 Prompt、思维链或凭据。
2. 在 `NotebookWorkspacePage` 继续复用现有真实请求和轮询，在 `SourceEvidencePane`/结果面板加入“标准核验”标签和复核状态映射。
3. 固定四种文案：证据支持、当前证据不足、需人工确认、复核未完成；每种失败都显示下一步，不使用成功色假装全量覆盖。
4. 不新增菜单、页面或 Agent 编辑器；报告流程仅消费既有确定性结果，Finding/Challenge 作为可追溯审查上下文展示。

### Phase 5 — 验证、文档与提交

1. 后端：挑战契约、持久化幂等、跨运行拒绝、三种 verdict、无 Finding、DeepSeek 异常/JSON 无效、Coverage 汇总、`VerificationResult` 不被影响。
2. API/前端：CodeReview 只读投影、四种复核状态、预算/模型失败说明；运行 `vue-tsc`/Vite 构建。
3. 运行 Python 编译、Alembic `upgrade head --sql`、定向与全量 pytest（在当前已安装依赖环境）；不执行被审查仓库内容。
4. 记录 Docker/DB/DeepSeek 外部 E2E 结果。Docker 不可用时只标记未覆盖，不重启服务；环境恢复并有用户本地有效 Key 后再做真实调用。
5. 每个完成切片更新 `docs/handoff`、`progress.md`、`task_plan.md`，以中文提交且不推送；绝不把与用户现有多格式知识库/UI 改动混入提交。

## Acceptance Matrix

| 场景 | 必须结果 |
| --- | --- |
| 有效 Finding 且 Hunk/Claim 可定位 | 保存不可变 Challenge，Notebook 可回放 verdict 与理由 |
| 当前证据无法证明触发 | `UNSUPPORTED`，保留原 Finding，不能影响最终结论 |
| 缺运行态/外部配置 | `NEEDS_HUMAN`，报告中仅作为人工处置上下文 |
| 无 Finding | 不调用复核模型，Coverage 为 `NOT_APPLICABLE` |
| 模型 Key 缺失/限流/JSON 无效 | 明确降级与下一步，无占位结论/回退模型 |
| 二进制/预算截断/上下文失败 | Coverage 列出真实未覆盖范围与原因码 |
| 重新运行 | 新 AnalysisRun 产生新挑战记录，历史记录不可回写 |
| 既有裁决与报告 | Challenge 不直接改写 `VerificationResult` 或审批状态 |

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| 组合补丁未命中 `findings.md` 的历史尾部锚点 | 1 | 未重复同一组合补丁；先单独写入主计划，再用实际尾部定位同步发现与进度。 |
| 在 `frontend` 工作目录调用根目录 `.venv`，后端编译与 pytest 找不到解释器 | 1 | 前端构建已通过；后端验证改回仓库根目录执行，避免重复相同路径错误。 |
| 后端 Settings 要求 `JWT_SECRET` 至少 32 字符，临时校验值过短导致 pytest/Alembic 收集失败 | 1 | 不写入配置文件；后续仅为当前进程注入满足长度的占位值后重跑。 |
| 前端构建命令后仍在 `frontend` 目录执行后端 API/Alembic 校验，根目录虚拟环境与 `backend` 配置路径不可见 | 2 | 前端构建已通过；不在子目录重试后端校验，后续只从仓库根目录执行后端命令。 |
| API 路由校验直接读取 `app.routes` 中包装路由的 `.path`，遇到 `_IncludedRouter` 属性错误 | 1 | 改用 `getattr(route, 'path', None)` 过滤包装对象；不影响应用导入或路由实现。 |
| `app.routes` 仅暴露聚合包装路由，无法直接断言嵌套 `/api/v1` 子路径 | 1 | 不再用顶层路由做字符串断言；改校验声明 `run_router` 的 `/{run_id}/code-review` 路径，并保留应用导入检查。 |
| 声明路由器本身已带 `/analysis-runs` prefix，校验时误把路径当作未带 prefix 的子路径 | 1 | 先读取声明路径再做最终精确断言；不改路由实现。 |
## 2026-08-25 标准核验真实 E2E 结果

- 阶段 5（运行环境 E2E）已完成：Docker 恢复后对当前源码挂载的 API/Worker 完成一次隔离项目运行，并已恢复原 Compose Worker。
- 实际链路：Markdown 资料 `READY` → 公开只读 Git Diff 冻结（1 文件、1 Hunk）→ 正式快照 → `standard-verification-v1` → DeepSeek 代码审查 → 反证步骤/覆盖汇总 → 确定性裁决 → 自动报告草稿。
- 运行 `1a022c32-3235-4fe7-b5a9-eb71fd0bee23` 为 `SUCCEEDED`；`CODE_REVIEW` ModelCall 成功（4,191 ms），但只读 README Diff 未产生 Finding，因此反证步骤正确写为 `NOT_APPLICABLE / NO_CODE_REVIEW_FINDINGS`，不应被描述为“Finding 已反证”。
- 数据库已从 027 升级到 029。首次直接重建 API/Worker 曾在 Docker Hub 鉴权请求处收到 EOF；恢复网络后构建成功，正式 Compose API/Worker 已以当前镜像重建。E2E 使用的临时源码挂载容器已清理，当前 `localhost:8000` 已验证 readiness 与 `code-review` 只读投影。
- 非零 Finding 的真实反证分支也已完成：公开教育用途仓库 `atiradonet/weak-go-app` 的单文件冻结 Diff 产生 2 条 Finding，并持久化 1 条 `NEEDS_HUMAN` 与 1 条 `UNSUPPORTED` Challenge。`FINDING_CHALLENGE` 和 `STANDARD_VERIFICATION` Coverage 均为 `ANALYZED`，证明模型 Finding 不是最终结论，且可被冻结证据否定或限制为需人工确认。

## 2026-08-26 交付主张确认闭环

### Goal

将“PR 标题即唯一结论”的当前实现替换为：DeepSeek 先从只读 PR 元数据提取候选交付主张，提交人确认、编辑或补充后，与 Git Diff 和可选资料一起冻结；后续固定双核按每条已确认主张输出核验结果。代码 Finding 与交付是否实现保持分离。

### Phases

1. `complete`：新增可编辑但可冻结的轮次级交付主张、只读 API、DeepSeek 候选提取和审计事件；模型不可用时返回真实失败，不回退 Fake。
2. `complete`：已确认主张摘要写入正式快照哈希与清单；启动运行时拒绝没有已确认主张的快照；工作流从快照主张创建运行内 Claim。
3. `complete`：Notebook 准备页加入“确认交付内容”第一步，支持候选主张确认、编辑、删除和新增；冻结和运行按钮按状态门禁。
4. `complete`：交付结论改为“总体交付状态 + 逐项主张”，将 P0 Finding 摘要与交付结论语义分离。
5. `complete`：已完成迁移离线 SQL、定向后端回归、前端构建与机械 UI 检查；未执行被审查仓库内容或调用真实模型。

### Fixed Decisions

- 候选提取只读取同步的 PR 标题、正文、关联链接和用户在本轮选择的资料摘要；不会读取未冻结 Git 代码，不会执行仓库内容。
- 模型只产出候选主张，任何候选必须由提交人明确确认后才可进入正式快照；用户可手动补充主张，但不能在正式快照后改写。
- 每次正式快照复制已确认主张为不可变清单，运行内 `Claim` 从该清单派生；旧运行、报告和记录保持原样可回放。
- 无已确认主张、模型提取失败、主张为空或快照不完整均给出下一步动作，不生成“已交付”或“无风险”假结论。
