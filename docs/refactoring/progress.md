# 实施记录

## 2026-10-21

- 已重新读取批准的重构计划并核对 Git；保留原有未提交修改。
- 已检查路由、业务服务、核验图、三个 Worker、Alembic 入口、账号协议和默认启动填充。
- 开始 P1：先隔离现有流程与旧业务适配，不切换正式业务写入方。
- 验证策略：仅源码/语法/依赖检查；运行与真实模型验证仍待后续阶段。

### 首批代码交付

- 新增步骤/状态协议和旧业务装配入口，将 Session、模型创建、Git/制品访问及正式裁决留在明确的过渡适配器中。
- 抽离两个代码审查输入构建算法及三个值对象；原服务继续提供兼容入口。
- 新增任务领取结果、心跳、结果、失败、事件、工具调用的 Python 模型及 6 个 JSON Schema；补充可重复生成脚本。
- 从实际源码捕获 105 个 API 路径/方法/处理器/响应模型，保留全部旧路由。
- 解除默认演示账号创建，README 和启动输出指向真实注册。
- Spring Boot/MyBatis 候选按官方资料锁定 4.1.1/4.0.0，Java 使用本机 21；尚无 Java 构建结果。

### 静态验证结果

- 10 个变更 Python 文件语法编译通过；5 个独立契约/流程模块可在不加载应用配置的情况下导入。
- 对照 HEAD 的 AST：11 个业务步骤 + 取消/事件两个辅助函数一致；上下文路由、23 个图操作、状态 Schema 和初始状态一致。
- 两个输入算法的函数体一致；两个持久化校验函数完整 AST 一致。
- 6 个导出 Schema 与 Python 模型一致，JSON Schema 元结构检查通过；没有构造或调用业务样本。
- start.ps1 PowerShell 解析通过；git diff --check 通过。
- LangGraph 导入出现既有依赖的 PendingDeprecationWarning，不影响导入结果，本次未升级依赖。

未运行自动化测试、服务、迁移或真实模型调用。静态一致性不能替代实际业务运行验证；P1 运行验收及后续 P2–P8 仍未完成。

## 持续目标：架构初步完善

### Java 服务与发布正文

- business-server 已建立 Spring Boot 4.1.1 / JDK 21 / MyBatis 4.0.0 服务；真实实现旧 PBKDF2 密码校验、HS256 JWT、当前用户、项目资源鉴权及报告/正式记录读取。
- 新增 039 迁移及 PublishedReportBody：发布事务从当时真实条目与引用物化固定正文，独立 hash，数据库拒绝更新/删除；不对历史正文猜测回填。
- Java 的 Cache-Aside 先授权再查正文版本元数据，校验缓存 hash/版本，Redis 故障回源；动态用户名、项目状态等不进入固定正文。

### Java 任务中心与 Python 执行

- 新增 040 迁移：独立规划快照/运行、通用任务/尝试/事件；规划关联不借用核验周期外键。
- Java 内部 API 实现事务领取、Worker 身份凭据、租约/代次、心跳、取消、事件去重、限次重试与幂等结果接受；正式结果由注册的场景处理器验证并和终态同事务落库。
- agent-service 为独立安装包，无业务 ORM/数据库凭据。已有真实 HTTP 模型适配、通用工具循环、上下文/轮数/工具/父子共享预算、注册 Agent 委派、任务范围工具网关、心跳和结果重放。
- Worker 当前只声明支持 PLAN_DRAFT/PLAN_REFINE；尚无 Java 规划任务生产者与结果/工具处理器，所以当前不能宣称跨服务执行闭环已通过。
- 已将结果协议明确为 candidatesJson 的原始 UTF-8 SHA-256，避免跨语言重新编码漂移；分配契约增加服务器发放的租约时长。6 份 Schema 已重新生成。

### 开发拓扑

- 新增 business-server/agent-service Dockerfile、开发叠加 Compose、网关配置；保留用户原有生产文件。
- start.ps1 -Refactor 会生成本地 Worker 服务凭据配置（业务数据不填充），组合叠加拓扑；Vue Vite 代理可指向网关。
- 当前仅登录/当前用户/报告读取/任务中心切 Java，其余仍由旧服务处理；这是明确的迁移状态。

### 当前验证证据

- Maven 使用项目内 .build/maven 缓存，Java package 成功（跳过自动化测试），生成 business-server/target/business-server-0.1.0.jar。
- uv sync 安装独立 Agent 依赖并生成 uv.lock；独立模块导入、全部 wire Schema 与两个 Agent 输出 Schema 元校验通过。
- Python 源码语法、PowerShell 启动脚本解析和 git diff --check 通过。
- Vue 的 vue-tsc + Vite 生产构建通过。
- Compose 叠加配置 config --quiet 通过；校验用的真实随机服务凭据仅在进程内生成，不写入旧 .env，不生成业务数据。
- 使用 infra/.env 中已有真实配置启动 Java（未打印凭据）：实际进程启动成功，GET /api/v1/health/live 返回 200；数据库未运行时 /ready 真实返回 503 DATABASE_UNAVAILABLE。临时 Java 进程随后已停止。
- 未运行自动化测试；未调用真实模型；未对运行数据库执行迁移或写入业务数据；数据库权限、缓存、租约、任务接收和规划闭环仍未获得运行证明。
- 已启动现有 Docker Desktop 以准备本地联调；Docker version/ps 查询会话 40299 仍无返回，需后续检查真实进程/引擎状态，不凭超时重复启动。

### 下轮实施入口

- 优先补足真实规划生产者和工具/结果消费者，让新执行架构承载完整业务，再继续迁移旧核验正式规则。
- 独立仓库快照应不依赖 VerificationCycle；冻结真实 SHA 与有界文件材料，由 Java 提供任务范围内的读取/搜索工具。
- 规划内容必须包含可检验验收项、带版本/可用条件的产物契约、依赖、仓库引用、显式假设及风险。确认绑定内容摘要/版本，已确认内容不原地覆盖。
- 创建任务时需冻结真实模型非敏感配置，并与 Worker 配置核对，不能仅用固定 modelConfigRef 就声称模型配置已冻结。
- Java USER 10001 对现有旧制品卷未获得写入所有权；新增仓库缓存使用独立可写卷，不对已有制品做递归 chown。

## P6 实际实现与当前证据

- 新增 041 迁移：独立 repository_snapshots、Idea/修订、澄清问题、计划版本，保留确认后的正文不可变及历史版本。
- Java 从已登记 GitHub 仓库只读抓取，固定 SHA、有界读取文本并保存实际覆盖范围。只允许配置中的凭据引用；缓存使用独立可写卷。
- PlanningService 以同一事务保存规划输入/运行和 AgentTask；实际问题持久化等待回答，回答后创建新的细化运行。任务创建具备请求幂等键。
- 注册 read_snapshot/search_snapshot/read_file 工具；范围绑定任务冻结输入与仓库快照。候选结果经 Java 检查字段、代码路径/SHA/行号、验收、产物契约、依赖引用和环，再保存草案。
- 计划编辑采用版本检查；确认绑定内容 hash 和版本及 REVIEWER/ADMIN 权限；新需求修订和新计划版本保留既有基线。支持工作项/依赖变化与下游影响对比。
- 新建 Vue 需求规划页与结构化计划编辑器、真实状态/事件轮询、澄清表单和版本操作；沿用既有工作台样式。权限来自实际后端查询。
- 提示词及输出 Schema 从实际 Python Agent 注册定义导出到 contracts/agent-registry-v1.json。Java 冻结实际提示词全文/hash及模型非敏感参数；Worker 不匹配时拒绝执行。
- Java package、Vue vue-tsc + Vite build、Python/协议/实际提示词导出一致性检查通过；新 UI 的一次机械检测无发现。没有运行自动化测试或模型调用。
- 包含全部新业务组件的 Java 进程实际启动成功；liveness 200、数据库不可用时 readiness 503。该证据不能替代数据库/真实模型链路验收。
- Docker 查询会话 40299 已终止，确认 Linux 引擎管道不存在；WSL 的 docker-desktop 发行版为 Stopped，Desktop 日志出现启动错误对话框。已通过异步问题请求用户确认报错/启动引擎，未重置数据或改变 Windows 功能。
- 上一轮中断属于实际 progress，代码仍在当前工作树；本轮继续 P7/P4，不把目标缩为已完成部分。

## P7 实际实现与空库联调（2026-10-21）

- 新增 042 迁移：不可变 cycle_plan_selections、可编辑阶段的当前选择指针、input_snapshot_plans 和 AnalysisRun 的成对计划基线字段。数据库约束保证引用范围；正式输入固定后不可切换选择，运行只能使用输入中固定的基线。
- Java 新增计划版本选项、明确选择/清除及核验溯源接口。只允许人工确认过的当前或历史版本，同项目、真实 CONFIRMED Claim、验收原文匹配；乐观检查当前选择，重复相同内容幂等。
- 旧正式输入冻结与主张确认增加 Cycle 锁，与 Java 的选择事务串行。冻结时复核计划/选择 hash、仓库身份、Claim ID/key/正文和完整验收条件；可选基线进入输入 hash，未绑定的旧路径保持原 hash 构造。
- 旧运行配置/manifest 包含冻结计划引用；模型输入保留验收条件、核验方式、所需证据，并明确其是要求。计划资料不变成 Evidence ID。报告读取包含来源，新绑定报告发布正文使用 v2 并固定基线。
- Vue 核验页支持选择确认版、选择验收项、加入实际交付内容、保存前关联、查看冻结基线及实际结果/报告。计划变化影响继续使用 P6 的版本比较；没有自动选择最新计划。
- 处理失去响应后的重试：保留服务端 Claim 身份和本地来源，重用相同人工主张 key；重新应用计划不会因重复自然键创建失败。合法验收正文的输入上限与规划的 6000 字符范围对齐。
- Java package、Vue vue-tsc/Vite build、142 个 Python 文件 AST 解析、旧业务桥接导入及 72 张 ORM 表依赖解析通过。新组件一次机械检测无发现；未运行自动化测试或浏览器视觉验收。
- 之前的 Docker 错误已由实时查询证实解除，Linux Engine 29.5.3 可用；该引擎原无容器、镜像或数据卷。通过已有 infra/.env 启动项目 PostgreSQL，目录查询确认 PostgreSQL 16.15、public 表数 0、未初始化迁移表，再运行 Alembic 001→042 成功。
- 数据库实际 pgvector 0.8.7；约束全部已验证，新计划/运行的约束触发器实际存在。账号、项目、Idea、规划运行、AgentTask、核验任务、报告查询均为 0，没有填充业务数据。
- Java 真实启动连接新库，readiness 返回 200 及 schemaVersion=042_plan_verification_bindings；独立 Python BusinessAPI 使用实际进程凭据成功认证领取，返回空队列。临时 Java 进程已停止；PostgreSQL 容器保留供继续开发。
- readiness 现在检查明确迁移版本，结构未就绪不会只凭 SELECT 1 返回成功。离线 SQL 生成仅产生构建产物，未将其当作数据库运行证据。
- 尚未验证：旧数据升级、实际用户权限/账号兼容、Redis 固定正文、真实 Idea→模型→确认计划→PR→核验→审批发布。P4 正式写入/规则与 P8 剩余迁移仍未完成，目标保持 active。

## P4 报告与人工裁决写入交接（2026-10-21）

- Java 新增 ReportLifecycle、ReportWriteMapper、ReportCommandsController、ReportCanonical：手动草稿、编辑/乐观版本、提交、独立审核人批准/驳回/补证新版本、发布固定正文、交付状态回写与审计。人工裁决只追加并刷新 DRAFT，正式系统结果保持原记录。
- 发布复核 profile、FORMAL 快照/hash、同报告/hash/快照/run 的批准记录及每条正式引用的项目/快照/类型/定位精度；PUBLISHED 轮次下所有报告版本停止修改。计划基线固定进 v2 发布正文。
- Java CommandStore 使用原有 idempotency_records，保留 principal/method/path/key 和原始请求字节 hash；当前授权先检查，业务写入和成功响应同事务落库，重复响应丢失不会形成第二次审批或记录。
- 新增 043：business_write_owners 是部署配置；默认保持 PYTHON。Python/Java 在业务事务持有共享所有权锁，交接取排他锁。数据库触发器检查实际写入方，保护已发布报告/记录和追加式裁决/审批；旧服务绕过网关也不能继续写报告。
- 自动草稿由旧 Worker 在运行完成同一事务保存 report_generation_jobs 和真实 QUEUED 事件。Java 定时消费使用 SKIP LOCKED、嵌套保存点、限次存储重试，草稿/终态事件同事务；失败保留错误和既有运行降级。报告失败引起的运行状态/manifest 更新现由 Java 队列执行，运行其余生命周期仍待 P4 后续统一迁移。
- Notebook 在实际 REPORT_DRAFT QUEUED/RUNNING 事件存在时继续读取，避免分析结束后遗漏异步报告；无计时模拟进度。
- start.ps1 -Refactor 先迁移、等待 Java readiness，再以独立 BUSINESS_OWNERSHIP_TOKEN 调管理 CLI 激活 JAVA 所有权。正常 Agent Worker 不接收管理 token；普通旧拓扑启动会先验证仍为 PYTHON。用户原生产文件未修改。
- 本机真实空库 042→043 迁移成功，迁移后所有权仍为 PYTHON、报告队列数 0。Java 真实启动 readiness 200/043；实际管理 CLI 成功激活 JAVA，旧 Python require_python_reports 对真实当前配置返回 BUSINESS_OWNER_MISMATCH。独立客户端成功认证领取空队列。临时 Java 已停止，未创建账号/项目/运行/报告或审批样本。
- Java 与 Vue 构建、156 个 Python 文件解析、PowerShell 脚本解析、Compose config --quiet 通过。报告 v1 JSON 明确紧凑/按键排序/UTF-8/null/数组顺序/非 ASCII 与斜杠不转义/控制字符小写转义，以及 UTC 微秒时间格式；历史 hash 不因所有权交接重算。
- 尚未验证：真实报告/人工裁决/审批发布流程、历史数据 hash 兼容、竞争与重试场景、Redis 发布正文。没有运行自动化测试、合成业务样本或真实模型调用。P4 正式核验输入/证据/规则和 P8 迁移仍在继续，目标保持 active。

## P4 输入冻结与确定性规则实现（2026-10-21）

- 新增 Java verification 模块：InputSnapshotLifecycle/Mapper/Controller，准备及正式输入冻结、项目/角色/轮次锁、重复选择校验、已挂载资料可见性、当前索引优先与稳定历史分块回退、分块 hash 复核、PR 来源与仓库/Git 制品复核、确认主张及指定计划基线复核、补证读取/物化与审计。
- 新快照使用 verification-input-v2/policy v2；完整规范化正文与快照/hash 同事务保存。正文包含实际脱敏摘录、来源定位和分块/index 版本、外部退出码、人工来源、PR 原文、Git 制品 hash 和计划/主张映射。旧 hash 与历史正文不批量重算或推测回填。新增业务 Schema，元结构校验通过。
- 044 新增 input_snapshot_bodies、正文与原快照的复合外键和正文不可变触发器；新增 verification-inputs 所有权配置，默认 PYTHON。输入及绑定表增加写入方守卫。旧冻结服务也先持有同一所有权共享锁，为后续切换准备。
- ControlledArtifacts 仅读取已登记的受控卷文件，真实路径约束覆盖符号链接，读取有界并检查实际 SHA-256 和 UTF-8。SafeExcerpt 保留旧脱敏规则，截断按 Unicode 字符计数；计划/裁决文本修剪兼容既有 Python 空白语义。
- VerificationRules 为无 I/O 的 Java 规则实现：相同 token/停用词和冲突优先级、确定性与人工命中、模型合法范围、相同关系不覆盖先前事实、风险生成和最终状态。模型可对正式测试/构建/人工证据提关系；只有精确 Diff 的模型支持可得 SUPPORTED。模型关系置信度和人工确认标志由程序固定。
- 当前规则类尚未接入 Java 核验结果消费者；Python 核验 Worker 仍处理正式运行。未把未使用的规则类或成功构建当作正式裁决已切换的证据。
- Java 多次离线 package 成功；修正 Mapper 读取/写入正文的同名重载，避免 MyBatis statement 冲突。Python 源码解析、业务 Schema 元校验、git diff --check 通过。没有运行自动化测试或构造业务样本。
- 本机真实库 043→044 迁移成功；reports=JAVA、verification-inputs=PYTHON，输入/正文/证据/分析运行查询仍为 0。包含新全部组件的 Java 实际启动 readiness 200/044，旧输入写入方实际检查通过；临时 Java 已停止。
- 冻结 POST 网关仍指向旧服务，未激活输入所有权；新增已授权快照正文读取路由。后续完成核验 producer/manifest、任务范围工具、Python 分阶段候选分析、Java 接受/对账/终态事务及所有权交接后才切流。
- 剩余业务验证与旧数据兼容仍待真实输入。P4/P8 未完成，目标保持 active。

## P4 核验任务与候选接受接通（2026-10-21）

- Java 新增 VerificationExecution/Controller：正式快照与轮次权限、幂等响应、冻结编排版本、Claim/真实 Diff 证据准备、模型/提示词/执行预算清单、AgentTask 建单。未切换网关，创建入口仍由 verification 所有权保护。
- VerificationResultConsumer 校验快照/计划/证据范围，接受真实审查发现及原发现 Hunk 的复核，调用 VerificationRules，保存链接/结果/风险/覆盖、运行和轮次终态及报告请求；这些变更与任务结果接受在同一事务。自定义关联不参与正式裁决。
- AgentTaskObserver 在任务实际领取、重试、过期、失败和取消时投影核验状态；实际事件只在去重插入成功时镜像。模型调用记录来自实际响应/错误事件，保存耗时、usage 和 Attempt 引用；解析失败更新对应调用状态。
- 独立 Python 新增 LangGraph 核验图：读取冻结输入、审查、复核、证据关联、至多一次上下文补充、注册自定义能力、候选封装。复用原纯输入构建，模型前核对冻结模型/编排/自定义提示词；共享执行预算、租约取消及精确 candidatesJson 摘要继续有效。新增 verification-result-v1 Schema 并从实际注册表导出。
- 本轮仍未绑定 Java read_context_candidate/query_registered_tool 处理器。调用时将返回真实工具不可用错误，不能据此宣布正式核验已交付；后续先完成受控本地 Git 上下文与 HTTP 临时材料、旧写入口守卫、管理交接，再切流。
- Java 离线 package、Python 导入、8 个 Schema 元校验、164 个源码/迁移文件解析通过；Git 按现有 CRLF 规则检查通过。实际空库 044→045 迁移成功；迁移前用户/项目/运行/报告均为 0，所有权仍 reports=JAVA、verification-inputs=PYTHON、verification=PYTHON。
- 包含新生产者、消费者和 Observer 的 Java 实际启动 readiness 200/045，真实认证领取规划与核验空队列返回 200；临时 Java 已停止。没有创建业务样本、运行自动化测试或调用真实模型。空库启动和构建不证明业务闭环，目标保持 active。

## P4 工具与正式写入权交接（2026-10-21）

- 上下文工具只接受冻结候选/主张及 SHA，从 Java/旧本地 Git 缓存读取实际 blob，分析阶段不 fetch。独立 Python 复用原 Tree-sitter 提取，Java 再核对路径/行范围/原文，保存一轮 CONTEXT_ONLY 制品。重试读取实际已登记制品。
- RegisteredHttpTool 执行登记且启用的自定义能力工具：HTTPS/443/主机白名单、授权的环境密钥引用、无重定向、服务端请求参数及冻结的时间/响应上限。实际响应字节/hash 保存为临时材料，可沿原人工导入流程进入后续快照；工具结果不能自动变为 Evidence。
- 新 JavaArtifacts、独立 java-artifacts 卷和只读兼容挂载；原 Git 进程实现提取为共享的有界 GitProcess。工具落库前重新检查当前租约/代次/权限，过期执行者不能登记材料。
- 旧启动/取消/编排入口和 Worker 加入核验所有权守卫；管理交接先检查旧活动运行，再按一致锁顺序复核并原子切换 verification-inputs/verification。网关正式冻结、启动及取消指向 Java，普通 Agent Worker 不持有交接凭据。
- 本机实际管理 CLI 已交接 reports/verification-inputs/verification 为 JAVA；旧输入与核验 guard 均实际返回 BUSINESS_OWNER_MISMATCH。Java readiness 200/045、真实认证空队列领取、Maven 构建、Python 导入及 Compose config 通过。临时 Java 已停止；没有业务样本或模型调用。

## P8 注册迁移开始（2026-10-21）

- Java 注册保持旧 PBKDF2 310000/16 字节盐/带填充 URL-safe Base64 格式、姓名及邮箱规范化和唯一邮箱约束；不重写已有密码。注册与登录/当前用户走 Java，旧注册入口及 users 数据库触发器检查 identity 写入方。
- 实际空库 045→046 迁移成功，Java readiness 200/046；实际 CLI 激活 identity=JAVA，旧注册 guard 返回 BUSINESS_OWNER_MISMATCH。identity/reports/verification-inputs/verification 当前均 JAVA；用户、项目、运行和模型调用仍均为 0，临时 Java 已停止。
- Java 构建通过，真实用户注册/密码互通/业务权限尚未验收，未创建演示账号或执行自动化测试。继续迁移项目/成员/任务管理、来源/入库/GitHub 同步、检索/索引及剩余聚合，再完成 Flyway 和旧进程退役。整体目标仍 active。

## P8 项目与核验任务管理（2026-10-21）

- 新增 Java 项目列表/详情、创建、成员添加和软删除。创建项目的管理员成员、系统编排、GitHub 连接/Git 登记/真实同步请求、知识库挂载同事务；同步消费暂仍由旧 Worker 承担。知识库挂载核对实际所有/共享项目权限；删除核对名称/管理员并检查分析、规划、同步、入库和索引活动状态。
- 新增 Java 核验任务列表/创建、下一轮创建和交付 PR 绑定。保持原字段和真实 PR 范围，行锁保护周期递增；已有发布记录不可更换交付，已有 Git 范围继续校验仓库来源。指定/默认模板在创建事务验证，正式分析仍冻结自己的配置副本。
- 047 新增 projects/task-management 部署所有权及 projects/project_members/verification_tasks/verification_cycles 写入守卫。旧项目、成员、建单、新轮次和 PR 绑定入口均先检查所有权；网关只切换已迁移路径，交付主张等其余接口仍由旧服务处理。
- 实际空库 046→047 迁移通过，Java readiness 200/047；管理 CLI 实际原子激活 projects/task-management=JAVA，旧两个守卫实际返回 BUSINESS_OWNER_MISMATCH。本机六项所有权均 JAVA，用户/项目/任务/轮次/同步记录查询仍均为 0，临时 Java 已停止。
- Java package、167 个 Python 源码/迁移解析、PowerShell 脚本解析通过。没有创建业务样本、执行自动化测试或真实模型调用；业务写入/删除/PR 流程和旧数据兼容仍待真实输入。下一步继续 GitHub 来源 API/同步消费、资料入库/检索、编排配置及外围模块，目标保持 active。

## P8 GitHub 来源与同步迁移（2026-10-21）

- Java GitHubSources/Controller 接管连接注册/引用更新、同步排队/查询、真实 PR 交付列表及资料关联。权限、来源归属、READY 资料、原始字节幂等及审计在业务事务验证；连接凭据只暴露是否登记引用。
- GitHubSourceClient 固定官方 HTTPS API、受控凭据引用、无重定向、有界 UTF-8 JSON，保留 Issues/PR/Milestone 独立分页、50 页限制、受控后继路径、游标和部分完成。Issues 端点的 PR 摘要仍排除，PR 使用独立实际响应。
- GitHubSyncStore/Runtime 将短领取/续租/提交事务与网络调用分离，使用尝试号/Worker/租约校验过期执行者。实际故障记录、限次重试、到期终态和空队列均来自数据库状态；无真实发起人的历史请求明确失败，不创建代替账号。
- GitHubResourceWriter 归一化原提供方字段，使用与旧源 hash 相同的排序/紧凑/UTF-8 JSON 规则，保留未变化修订；PR 规划状态与核验状态继续分开。资源修订、真实 PR 投影、主来源关联、同步结果与审计同事务保存；历史 hash 不重算。
- 048 新增 github-sources 写入守卫和 source_sync_runs.executor_owner。旧连接/同步/资料关联写入口受守卫保护，旧 Worker 领取/续租/完成在所有权交接后停止。Java 项目初始化和来源命令均创建 Java 所有的同步请求。
- 实际空库 047→048 迁移成功，Java readiness 200/048；真实管理 CLI 激活 github-sources=JAVA。读取实际领取 SQL 返回空队列；旧 source guard 返回 BUSINESS_OWNER_MISMATCH，旧同步 _claim_one 实际返回 None。七项写入方均 JAVA，用户/项目/同步/资源/修订/交付行数均为 0，临时 Java 已停止。
- Java package、168 个 Python 源码/迁移及 PowerShell 解析通过。没有构造业务样本、执行自动化测试、调用真实 GitHub/模型或推送。实际分页/同步/重试/角色及历史兼容待真实输入验收；继续资料解析/入库/检索、编排配置和外围业务，目标保持 active。


## P8 独立资料计算与知识库交接（2026-10-21）

- 上一目标轮只核对并回答实现状态，属于 no progress；本轮完成代码、实际迁移、服务启动及交接，属于 progress。完整目标保持 active。
- 独立 Agent 服务增加内部 FastAPI 解析/嵌入 API，和现有拉取 Worker 同进程运行；仅内部端口、独立 COMPUTE_SERVICE_TOKEN、配置 hash 与原始字节 hash、有界并发/输入/输出/执行时限，不接收业务数据库凭据，不管理 SourceRevision 或入库状态。
- 本地 Markdown/结构化解析算法从真实旧实现提取，AST 比较一致；PDF/Office/图片继续使用实际 MinerU API。MinerU 网络/下载/解压大小受控，嵌入返回实际数值并核对维度及有限性；仅 MODEL_UNAVAILABLE/MODEL_NOT_CONFIGURED 返回真实分块的词法降级，向量仍 null。未返回或估计 OCR 置信度。
- Java ComputeClient 实现配置、签名探测、抽取和批量嵌入边界，核对配置/输入/规范化正文/分块 hash、真实行或 Unicode 字符偏移、维度和索引版本；请求、整个响应时间和响应大小均有界。内部诊断使用 Worker 身份，Python 可用性与 Java/报告 readiness 分开。
- 缺少生成模型凭据不再阻止计算 API 启动；Worker 仍真实领取，实际生成任务在执行前明确 MODEL_NOT_CONFIGURED，无虚构模型调用。Compose 与 start.ps1 接入独立计算凭据和非业务配置，尚未把资料入库队列宣称为已交接。
- 049 修复真实容量问题：默认 knowledge-extraction-v1|embedding:dashscope:text-embedding-v4:d768 为 66 字符，旧分块、项目索引和重建目标字段仅 64。三处扩为 512，ORM 同步；不截断、不重算既有版本/hash，降级前检查实际数据能否放回原字段。
- 知识库列表/创建/挂载/卸载迁 Java，保持当前用户所属有效项目的所有或已挂载知识库可见性；项目锁、当前授权、原始字节幂等及审计同事务。050 增加 knowledge-bases 配置及 knowledge_bases/project_knowledge_bases 写入守卫；旧三个命令及普通旧启动检查同一所有权，Java 项目初始化挂载同步接入。
- 本机真实库 048→049→050 迁移成功，三处索引字段实际为 512，两处知识库触发器存在。独立 Java 启动 readiness 200/050，在 Python 未启动时也保持业务 readiness；真实管理 CLI 激活 knowledge-bases=JAVA，旧 Python guard 实际返回 BUSINESS_OWNER_MISMATCH。八项业务写入方均 JAVA；用户、项目、知识库、挂载、资料和模型调用均 0。
- 实际 Java→Python 内部配置请求 200，跨语言 canonical hash 一致。真实仓库 README（当时 7856 字节）经 HTTP 检查和抽取 200，实际 12 个分块，缺嵌入凭据明确 UNAVAILABLE/MODEL_NOT_CONFIGURED；全部向量为 null，正文 hash 复核一致，没有保存业务样本或调用模型。临时 Java/Python 进程均已停止。
- Java 离线 package、Python 源码/迁移解析、五份计算 Schema 导出与全部 Schema 元校验、PowerShell 解析、Compose config --quiet 通过；实现参考 FastAPI 官方 lifespan 文档 https://fastapi.tiangolo.com/advanced/events/。没有运行自动化测试、付费调用、生产部署、提交或推送。
- 下一步：Java 资料上传/内容/下载/删除、SourceIngestionJob 租约队列、结果接受和索引持久化；随后迁移索引重建与检索。真实 MinerU/嵌入、业务权限、跨项目挂载和历史数据兼容仍待真实输入验收，P8 与整体目标未完成。


## P8 资料生命周期、入库与派生索引（2026-10-21）

- 上一轮已完成独立计算接口、容量迁移与知识库交接，属于 progress。本轮继续真实资料链路，整体目标保持 active。
- Java SourcesController/SourceStore 接管上传、版本序号、知识库范围、列表、正文/下载、分块与删除。上传使用文件字节 hash 和完整表单字段作为幂等身份，不受 multipart 边界改变影响；当前权限在读取文件、重放与提交时复核。兼容旧上传重放时逐项核对实际资料内容 hash/角色/名称/文件名/知识库/OCR，不重写历史 request_hash。历史数据兼容尚待实际记录验收。
- 文件签名通过独立计算接口核对；长网络调用在业务事务外，创建版本、真实制品登记、入库请求和审计同事务。新版本登记规范化正文 hash；共享挂载资料可按权限读取，删除限所属项目、有正式快照/其他引用则拒绝，内容寻址文件保留，避免先删文件再遇外键回滚导致历史制品损坏。
- SourceIngestionStore/Runtime 实现 SKIP LOCKED、Worker/尝试号/租约校验、心跳、到期限次失败和真实错误重试。领取只锁队列行；提交按项目、资料、任务顺序加锁并复核当前权限。旧待处理任务可在旧执行排空后由 Java 接管，实际冻结当时计算配置；已冻结任务不自动采用新配置。
- Java 接受抽取结果后校验原文/配置/正文/分块 hash、定位与向量维度，原子保存真实分块、规范化制品、索引信息、READY/任务终态和审计。仅真实可用嵌入建立向量索引，缺配置/服务故障保留 null 向量分块；不从推断生成 OCR 置信度。新模型版本入库不会自动切换项目已有活动索引。
- IndexBuildStore/Runtime 固定 READY 资料范围和计算配置，以实际规范化原文重做旧 Markdown 分块；不重新调用 MinerU。已有目标分块逐项核对后复用，只对缺失分块计算真实嵌入。全部资料结果、当前资料范围、租约和权限通过后，同事务追加派生分块并切换活动索引；失败不修改旧索引。保留已被快照引用的历史分块 ID。两条队列共享配置的计算容量，上传签名检查有独立有界执行槽。
- 索引重建 POST 改为实际排队的 HTTP 202/build_run_id/status，GET rebuild-runs 查询真实终态和实际新增分块计数；已核对当前 Vue 没有调用该重建端点，README 同步记录异步契约。没有计时模拟进度。
- 051 新增 knowledge-sources 部署所有权、两类队列执行方/冻结计算配置、索引重建租约和固定输入、规范化正文 hash，以及五张业务表的写入守卫和资料/配置不可变规则。默认 PYTHON，交接检查旧入库和重建执行排空；旧服务写入口和 Worker 的领取/心跳/提交全部检查同一所有权。网关和 start.ps1 已接入，原生产配置保持不变。
- 本机真实 050→051 迁移成功，8 个新触发器实际存在，实际 pgvector 列维度 768。Java 启动 readiness 200/051，真实管理 CLI 激活 knowledge-sources=JAVA，九项所有权均 JAVA；旧 source guard 实际返回 BUSINESS_OWNER_MISMATCH，旧 _claim_one 实际返回 None。Java 资料/索引空队列调度未出现错误。
- 真实仓库 README（当时 8512 字节）通过 Java ComputeClient→Python HTTP 进行签名探测、抽取和规范化原文重新分块，均成功；实际抽取 12 块，重建分块 12 块，Java hash/定位校验通过。未配置嵌入凭据时实际 UNAVAILABLE/MODEL_NOT_CONFIGURED，向量全为 null。没有创建或保存业务样本，用户、项目、资料、入库任务、分块、索引、重建记录和模型调用实际均为 0。
- Java 离线 package、177 个 Python 文件解析、六份实际计算 Schema 导出与全部 Schema 元校验、PowerShell 解析、Compose config --quiet、Git CRLF 规则下的差异空白检查通过。没有运行自动化测试、调用真实 MinerU/嵌入模型、部署生产、提交或推送；临时原生服务验证后停止。
- 尚未验证：真实用户上传/共享权限/删除、入库重试/过期竞争、实际向量持久化及索引切换、旧数据和历史上传幂等兼容。继续迁移检索、编排配置、Git 与交付补证等剩余接口，再完成 Schema/Flyway 和旧后端退役；不把构建或空库交接作为整体完成证据。


## P8 冻结资料检索与受控工具（2026-10-21）

- 上一轮资料/入库/索引实施与真实交接属于 progress；本轮完成 Java 检索 API、受控工具、构建与真实数据库读取，目标继续 active。
- SnapshotSearchController/Service/Store 接管冻结资料检索；授权和排名读取分别在嵌入调用前后的短事务执行，外部 HTTP 不占业务事务。检索源来自快照资料绑定，返回现有 Evidence ID、固定脱敏摘录和定位，不创建证据或正式结论。
- PostgresHybridRetriever 迁移 PostgreSQL simple/websearch_to_tsquery/ts_rank_cd、pgvector 余弦距离、limit*12 原始窗口、两路各 limit*3 去重、无候选时字面子串回退。保留(source_revision_id,chunk_index)去重、向量替换候选 ID 且保留词法位置、插入次序和按六位公开分数稳定排序。FTS/vector SQL 没有增设额外 tie-break。字面扫描使用数据库游标，避免一次加载全部分块和向量。
- RetrievalRanking 保留 RRF_K=60，权重 0.75/0.15/0.10，角色匹配、EXACT/APPROXIMATE/UNAVAILABLE 与 OCR 缺值不降权及排名原因。六位舍入和 OCR 两位显示使用实际二进制浮点值的 half-even；源角色 casefold 使用当前 Python Unicode 15.0.0 的真实 1530 项映射，导出脚本及构建/容器资源已接入。没有使用合成业务输入进行对照运行。
- 明确修正范围缺口：旧逻辑仅凭资料+分块序号将新索引命中映射到旧 Evidence ID。新 SQL 要求候选存储 hash 与该快照文档证据 hash 相同，Java 再复核实际文本 hash；最终返回时再次核对证据 hash。内容一致的派生索引仍可复用冻结证据，内容改变的同序号分块不能回指旧证据。排序公式没有随范围修正更换。
- 活动索引与配置不符、缺凭据、计算不可用或查询期间索引变化时，保留真实词法检索，响应增加 retrieval.mode/vectorStatus/errorCode 明确实际降级。快照没有资料或获授权文档证据时直接真实空态，跳过模型调用。
- 新 search_frozen_documents 注册工具只接受 query/limit/preferred_source_roles，不能接受模型指定项目、快照、来源或 Evidence ID。身份由 AgentTask 当前创建者推导，查询前后复核当前 lease/fence/取消/权限和任务冻结输入，只使用任务 allowedEvidenceIds。任务固定非敏感嵌入配置，Worker 和 Java 使用实际导出的 evidence-link-agent v2 注册与提示词；工具纳入现有共享工具/回合/时间预算。
- 网关搜索路径迁到 Java；旧 Python search_snapshot 入口在 knowledge-sources 交接后拒绝。没有 Schema 改动，数据库 head 仍 051，九项写入方仍 Java。非敏感模型配置注入 Java，服务凭据继续仅保留在内部计算/模型适配器。
- 复核旧索引策略后修正 SourceIndexWriter：已有活动索引时上传不同版本只记录 SOURCE_INDEX_VERSION_REQUIRES_REBUILD，不额外登记历史索引描述；实际重建才登记/切换。与既有源行为保持一致，未改写或删除历史记录。
- Java 离线 package 成功，177 个 Python 文件解析、全部 Schema 元校验、实际 Agent 注册表一致性与 Compose config --quiet 通过。真实 Java 启动 readiness 200/051，打包 Unicode 资源实际存在；用实际数据库来源/Evidence ID 集合及仓库 README 标题执行 JDBC FTS 和字面扫描，实际源/文档证据/结果均为 0。用户、项目、分块、证据、AgentTask 和模型调用仍为 0；临时 Java 已停止。
- 没有执行自动化测试、合成业务样本、模型调用、生产部署、提交或推送。实际词法/向量命中、权重顺序、重建后引用、角色撤销/取消竞争和历史兼容仍待真实数据验收；不能以空范围查询推断完整检索或模型链路通过。
- 下一步继续编排配置、Git/交付主张/补证、剩余查询和外围接口，然后核对 Schema/Flyway、部署与旧后端退役。整体目标未完成。


## P8 编排配置、能力/工具与补证材料（2026-10-22）

- 上一轮冻结检索、受控工具与真实数据库空范围读取属于 progress；本轮完成编排和补证代码、Schema 迁移及真实所有权交接，目标保持 active。
- OrchestrationManagement/Queries/Controller 接管工具注册、自定义能力、追加版本、最新版本读取、停用、模板创建/列表、任务绑定及历史运行编排读取，保持原有字段和路径。命令当前角色检查、项目配置锁、原始字节幂等、业务写入和审计同事务。HTTP 工具的 ADMIN 角色在幂等重放前检查。
- 保留自定义 SHARED 边界、固定主干必选/不可停用、系统 Prompt/工具授权不可编辑、能力停用和历史版本不变。新增注册身份核对，不能用自定义能力占用系统 key，也不能同时编排同一能力多个版本导致按 key 冻结的 Prompt 冲突。新模板与运行预检在付费执行前拒绝不合法配置。
- ToolEndpointPolicy 与实际 RegisteredHttpTool 共用 HTTPS/443、无用户信息/查询串/片段、服务端主机名单及密钥引用名单；注册不读取密钥值，不进行外部调用。只有执行已授权工具时才解析服务端凭据。空密钥引用按未配置处理，既有工具/能力/版本记录不重写。
- 052 新增 orchestration 写入权及六张配置表的守卫、能力版本和运行编排不可变规则。新 analysis_run_orchestration_snapshots.raw_body 保存实际冻结 JSON 原始字节，数据库校验 JSONB 投影与 UTF-8 SHA-256，Worker 收到同一原始正文。既有 raw_body=NULL 不补造；已知序列化方式必须匹配既有 hash 才用于执行，否则明确不可回放。历史只读接口继续保留原结构/原摘要并标注原文是否已保存。
- EvidenceMaterials/Controller 接管人工补证、TEST/BUILD 外部材料、工具执行列表、显式导入人工材料与正式引用解析。轮次锁和当前角色限制可补证状态，外部提交 SHA/退出码来自用户实际输入，制品和 hash/提交者/审计同事务保存，不运行上传内容或生成退出码。
- 工具导入仅允许成功/部分完成运行及可补证轮次，复核工具结果项目、运行、输入和实际制品 hash；每个实际工具结果只导入一次，保存 AGENT_TOOL_IMPORT 来源。导入只创建人工材料，不创建 EvidenceItem；后续新正式输入显式选择。引用解析拒绝跨项目/快照和未导入冻结的 TOOL/HTTP_QUERY 临时项。
- 053 新增 evidence-materials 写入方及 manual_evidence/external_evidence 两表守卫，交接后材料不可原地更新。旧三处材料生产和九处编排变更入口均检查同一所有权；网关、启动脚本、独立部署 CLI 已接入。
- 首次迁移实际因本机 Docker 未启动而连接失败，原 Maven 句柄已消失，确认后重建。通过只读引擎/进程/容器查询确认，再后台启动已有 Docker Desktop 和原 infra-postgres-1，沿用原卷，未重置环境或删除数据。终止状态确认后重新迁移，实际 051→052→053 成功，10 个新触发器和原始正文校验约束实际存在。
- Java 真实启动 readiness 200/053，实际管理 CLI 激活 orchestration/evidence-materials=JAVA；当前十一项所有权全为 JAVA，旧两个守卫实际返回 BUSINESS_OWNER_MISMATCH。实际用户、项目、工具、能力/版本、模板/绑定/运行编排、人工/外部材料及模型调用均为 0；真实注册表 JSON 的 PostgreSQL UTF-8 SHA 与实际字节摘要一致。临时 Java 已停止，PostgreSQL 保留。
- Java 离线 package、179 个 Python 源码/迁移解析、全部 Schema 元校验、PowerShell 解析、Compose config --quiet、Git CRLF 空白检查通过。没有运行自动化测试、创建业务样本、调用模型/外部工具、生产部署、提交或推送。
- 待真实业务输入验收：项目默认配置、HTTP 工具/角色、能力版本与模板/停用、浮点等历史配置回放、补证并发/导入和后续冻结、旧数据与密码兼容。继续 Git、交付主张及关联、剩余运行/快照查询和项目健康/安全/质量业务，再做 Flyway、部署和旧后端退役。整体重构未完成。


## 2026-10-22：Git 仓库与交付快照交接（054）

- Java 新增 GitInputs/GitComputation/Controller：仓库登记/列表、轮次范围冻结及 Diff 读取。保留原 URL 去空白后的身份 hash 和已保存历史制品；登记仅存环境凭据引用，真实密钥不入库。PR 绑定复核同一项目与 GitHub 来源仓库。
- 采集前先检查当前角色/轮次/仓库和幂等重放，在无数据库事务期间调用窄的内部只读计算 API；接受时重新锁定轮次/任务并复核当前角色、配置和交付绑定。实际 Diff 与原始 bundle 字节 hash 校验后，制品登记、GitSnapshot、审计及幂等结果同一事务保存。正式快照读取校验项目/种类/范围/hash，不根据旧分支重建历史。
- 独立 Python GitCapture 只接受 Java 指定的注册仓库与范围，固定 Git 命令、进程环境、超时与输出上限；不 checkout 或运行仓库脚本。拉取后将分支/标签/提交表达式解析为实际完整 SHA，支持两点/三点及 include/exclude；沿用原 Diff/覆盖和符号算法。三点比较的上下文使用与 Diff 一致的实际 merge-base。
- Java 验证计算配置/请求摘要、SHA/有效基线、Diff 原字节、bundle 原文、覆盖范围、实际 patch 和上下文摘要。采集配置独立于资料入库配置，并冻结语法引擎版本与预算。缓存沿用规划的 project/repository/repository.git，与 Java FileChannel 共用 capture.lock 的系统记录锁；Python 进程内也串行持锁，取消/超时前释放真实子进程。
- 实际仓库 81d328adc497..eeea29677fb1 的两点/三点 Diff 均为 7234 字节，摘要与直接 Git 输出一致。真实代码提交 8aef21c42549..258299c79e12 的选定两文件产生 8 个 hunk。初次符号数为 0，排查为锁定语法包默认用户缓存不可写；调整为准备阶段安装五种固定语法，实际提取 12 段符号上下文且摘要均匹配。运行时不下载解析代码，缺语法明确记录 PARSER_UNAVAILABLE。
- 054 实际迁移成功，git_repositories/git_snapshots 两个新触发器存在；新增 git-inputs 写入权已通过真实管理 CLI 激活。Java readiness 200/054、Python Worker RUNNING、真实鉴权的 Git 配置接口成功，旧入口守卫实际返回 BUSINESS_OWNER_MISMATCH；十二项写入权均 JAVA。真实用户、项目、Git 仓库/快照、AgentTask 与模型调用仍为 0，临时本机服务已停止，原 PostgreSQL 保留。
- 网关、启动脚本、独立管理 CLI、Agent Git/SSH 运行用户与共享缓存挂载已接入。最终 Java 离线 package、187 个 Python 源码/迁移解析、16 个 Schema 元校验、PowerShell 解析、Compose 配置和 Git 空白检查通过。最终 Agent 镜像实际构建成功（bc18de35cc40），临时无网络容器实际使用 UID 10001/devproof，Git 2.39.5 与五种语法全部可加载；语法版本实际为 tree-sitter-language-pack 1.22.1 / tree-sitter 0.25.1。临时容器已退出删除。没有创建业务样本、执行自动化测试、调用模型、推送或生产部署。
- 待验收：真实项目/账号/远程仓库的冻结事务、角色撤销与同键重放、SSH/私仓权限、跨进程缓存锁以及历史制品读取。下一步继续交付主张及关联、剩余业务查询/外围模块、Flyway 与旧后端退役，整体目标仍 active。


## 2026-10-22：交付关联与规则候选交接（055）

- Java DeliveryAssociations/Store/Controller 接管五个原接口：关联列表/人工确认、候选目标列表、用户选定目标的规则候选及 GitHub 平台发现。仅允许同项目、同来源连接的 PR；Git 目标须属于绑定当前事项的核验任务，并匹配来源仓库。任务绑定、Git 冻结和关联使用同一 RepositoryIdentity，按原 Python 的 URL 结构与 Unicode casefold 进行身份比较。
- 原“候选 Agent”实际是 token-overlap-v1。移植为 Java 确定性规则，保留最多 20 个显式目标、去重、当前已保存版本、词元/汉字二元组、Unicode 码点截断、排序、置信度、既有关联跳过规则与来源字段，不调用模型。真实 README/旧服务/NotebookWorkspacePage 文件与旧函数的词元结果一致；没有构造业务样本。
- 角色与幂等重放在业务事务中复核，事项行锁串行化关联保存。候选输入清单/hash、最终计数及实际目标引用冻结后保存；已确认关联不会被重新提议或覆盖。人工/平台只将候选提升为确认，保留原候选运行与创建来源。
- GitHub 时间线请求移到业务事务之外，使用已有受控 HTTPS 客户端与分页/字节/时间预算。接受时重新检查当前权限、事项的 PRIMARY Issue 和连接配置；缺少真实 Issue 来源时明确拒绝。只接受来源 PR API URL 属于同一仓库的交叉引用，记录未同步/排除事件计数与分页截断，不能用同号 PR 代替跨仓库目标。
- 保存实际返回时间线的结构化制品、hash、Issue 版本和变更关联 IDs，并与关联/审计/幂等结果同事务提交；该制品不自动成为正式 EvidenceItem。发现响应按原声明改为 changed_count/skipped_count，增加实际 page_count/truncated/excluded_event_count/input_hash。
- 055 新增 delivery-associations 写入权及 delivery_change_links/agent_change_proposal_runs 两表守卫。候选运行不可修改，确认后的关联和既有身份/候选来源不可改写；没有回填或重写旧记录。旧三个变更入口已检查同一所有权。
- 实际 054→055 迁移成功，两个触发器存在，迁移前后业务记录数量一致且为 0。Java readiness 200/055、Python Worker RUNNING、实际管理 CLI 激活 delivery-associations=JAVA、旧守卫返回 BUSINESS_OWNER_MISMATCH。十三项写入权均 JAVA，用户/项目/事项/关联/候选运行/AgentTask/模型调用均为 0；临时本机服务已停止，保留原 PostgreSQL。
- Java 离线 package、188 个 Python 源码/迁移解析及 Compose 静态配置通过。包含新管理命令的 Agent 镜像实际构建成功（d6281bd9e20d）。未运行测试套件、创建业务样本、调用模型/GitHub 业务 API、提交/推送或部署生产。
- 待真实业务验收：PR/Git 关联及角色竞争、候选版本/来源、当前权限撤销后的接受、平台实际事件/分页与跨仓库排除、历史候选确认和制品回放。继续交付主张生成/确认、剩余运行/快照读取和项目健康/安全/质量、Flyway、最终拓扑及旧后端退役。整体目标仍 active。


## 2026-10-22：交付主张的异步生成与确认交接（056）

- Java DeliveryClaims/Store/Controller 接管主张列表、人工确认、候选任务生产及本轮提取运行列表。保留当前可编辑周期、正式输入前的修改边界、现有 MODEL/HUMAN key/哈希、人工确认者及来源清单；幂等响应与变更同事务。相同模型文本重提时按原 key 复用实际草稿身份，修复旧流程重插相同 key 的冲突，未重写历史记录。
- 新 delivery_claim_proposal_runs 冻结实际 PR 版本、可选的已挂载 READY 资料、原文 UTF-8 hash 与来源清单。资料摘录保留原 4000 Unicode 码点、最多 20 份和真实文本/hash；不是预置样本。SQL 校验原始 JSON 的摘要与 sourceManifest 投影，输入/来源/身份不可修改。
- AgentTask 新增独立 claim_proposal_run_id 和 DELIVERY_CLAIM_PROPOSE；三类业务外键恰有一个且任务种类匹配，未借用规划/核验运行。扩展并导出 assignment/result/tool 等契约、主张输入/结果 Schema、实际注册 Agent 与工具/提示词。新任务复用事务领取、租约/代次/取消/重试/结果接受，按冻结输入重试，不宣称图断点恢复。
- 独立 delivery-claim-proposer 仅提取简体中文候选。执行器在首个模型调用前主动读取 read_claim_proposal_input，验证 Java 保存的原始输入文本/hash、Schema 与项目/业务引用，再提供真实材料；代码复核修正了初版仅把引用交给模型、依赖其主动读取的缺口。读取计入共享工具预算。Agent 不获仓库或正式 Evidence ID，只能重读本任务输入；不生成确认或正式核验结果。
- Java 读取/接受时锁定实际 AgentTask，检查当前 lease/fence/取消、用户角色、运行/输入hash、当前周期/PR 绑定、资料当前挂载/就绪与内容摘要。模型结果按字段/数量/文本边界接受，候选/审计/运行成功/任务终态同事务。正式输入已冻结或用户已确认后，旧候选不能覆盖；模型调用事件仅保存真实 Worker 报告的尝试/用量/时长及结果，不制造调用记录。
- 提议 API 改为 HTTP 202 与实际任务引用。Vue 页面已同步使用真实 QUEUED/RUNNING/终态，支持取消和刷新恢复本轮运行，项目/任务切换与卸载后停止旧状态回写；人工 PUT 仍返回实际主张列表，生成成功不自动确认。
- 056 实际迁移成功：新运行表、两个写入守卫、原文校验和 AgentTask 三外键约束存在。主张写入权通过真实管理 CLI 交接，旧守卫实际返回 BUSINESS_OWNER_MISMATCH。Java 最终 readiness 200/056、独立 Python Worker RUNNING；十四项写入权均 JAVA，主张/提取运行/AgentTask/模型调用仍为 0。临时本机服务已停止，原 PostgreSQL 保留；历史库与真实业务流程未验证。
- Java 离线 package、Vue TypeScript/Vite 构建、191 个 Python 源码/迁移解析、18 个 Schema 元校验、打包注册表一致性、PowerShell 解析及 Compose 静态配置通过。镜像初次因 Docker Hub 认证 EOF 失败，确认终态后重试成功；最终镜像 1628778957f3 含原文预读工作流、四类任务协议和新 CLI。无网络临时容器读取的 Agent 提示词 hash 与源码/JAR 一致，18 份 Schema 元校验通过；临时容器已退出删除。
- 未运行测试套件、造业务数据/模型响应、调用模型/GitHub 业务 API、提交/推送或生产部署。待真实输入验收：提取语义、人工编辑/确认、角色/挂载撤销与取消/租约竞争、重复结果/同键重放、相同候选重提、历史兼容和跨服务完整流程。
- 下一步继续剩余运行/快照/问答等读取、项目健康/安全/质量等外围业务、Flyway 交接、最终部署拓扑与旧 Python 业务后端/Worker 退役。整体目标仍 active，不能以本轮构建和空队列检查代替真实业务验收。


## 2026-10-22：运行读取与异步证据问答交接（057）

- Java 接管运行详情、任务最新运行、运行事件、核验结果和代码审查五个读取接口。查询按真实运行/项目/冻结快照约束，结果引用只读取实际引用的证据，排除临时 HTTP/TOOL 材料；人工裁决选项与正式写入共享 HumanDecisionPolicy。13 个实际 SELECT 通过 PostgreSQL JDBC describe 元数据检查，没有绑定虚构业务 ID 或执行样本查询；共享策略与旧 Python 配置摘要一致。
- 新 evidence_question_runs 固定实际问题、快照摘要和授权证据，EVIDENCE_QUESTION 为第五种任务，关联第四类独立业务运行。Java 处理授权、租约、结果接受、只读参考结果和审计；独立 evidence-question-agent 保留原五种事实支持状态，执行器在调用模型前强制读取并校验原始输入/hash/Schema。主张提取复用相同预读取组件，原提示词摘要保持不变。
- 问答创建返回 202 与实际任务/结果引用，列表和详情只向发起者及当前管理员开放；普通项目成员可提问并取消自己的问答。所返回 citations 表示全部输入证据，并显式标记 SUPPLIED_EVIDENCE/informational_only；不暗示逐项支持，不修改正式核验、主张或报告。未增加无现有调用方的问答页面。
- 本机 056→057 迁移成功，问答运行及专用模型审计两个守卫触发器存在。Java readiness 200/057、独立 Worker RUNNING、实际管理 CLI 激活 evidence-questions=JAVA，旧 Python 守卫返回 BUSINESS_OWNER_MISMATCH。十五项写入权均 JAVA；用户、项目、AgentTask、模型调用、问答运行均为 0，迁移及验证前后数量未变。临时本机服务已停止，原 PostgreSQL 保留。
- Java 离线 package、199 个 Python 源码/迁移/契约导出脚本 AST 和 20 个 Schema 元校验通过。Agent 镜像实际构建成功（7dba10932c18）；无网络临时容器加载五种任务/问答工作流及 20 个安装 Schema。问答提示词摘要为 4d9a6ee53e7f，主张仍为 81fca37a3192，与源码导出及 JAR 注册表一致。未运行测试套件、创建业务样本或调用模型。
- 真实问答、权限撤销、重试/取消、结果接受及历史运行兼容尚待实际业务数据验收。继续项目态势/总结、安全基线/质量及外围投影、Flyway、最终部署拓扑与旧后端退役；整体目标保持 active。


## 2026-10-22：项目态势与个人总结交接（058）

- Java ProjectStatus/Store/Controller 接管原七个接口：态势创建/列表/详情、总结草稿创建/列表、个人确认发布与记录列表。保留真实事项及其最新外部版本、里程碑筛选、确认关联/文档/正式记录、未归属活动、历史风险和同步时效；没有模型调用或固定业务数据。创建快照使用 REPEATABLE_READ，保存当次输入清单、摘要、范围、数据缺口与数据库实际时点。
- 保留 DAILY/WEEKLY/ITERATION 的原规则总结和 PERSONAL_CONFIRMED 个人确认。Java 对命令在当前项目权限下做幂等，发布先锁真实草稿；记录、草稿终态、审计、幂等响应同事务。新快照的核验覆盖率分子修正为同一未取消事项范围，避免原实现将取消事项计入分子；其他事实统计保留原口径。新摘要采用与 Python 一致的 UTC 微秒表示，既有快照、正文和 hash 未回填或重写。
- 058 给三个原表安装写入权与不可变守卫：态势/总结记录不可改写，草稿只允许保留身份及正文的 DRAFT→PUBLISHED。旧 Python 三个写入口增加同一所有权锁。网关、默认重构启动和独立管理 CLI 已接入；原前端所需草稿状态/时间字段由 Java 明确返回。
- 本机 057→058 实际迁移成功，三个触发器存在；13 个原 SQL SELECT 通过实际 PostgreSQL JDBC describe 元数据检查，未绑定业务样本或执行虚构查询。Java readiness 200/058、Python Worker RUNNING、实际管理 CLI 激活 project-status=JAVA，旧守卫返回 BUSINESS_OWNER_MISMATCH。十六项写入权均 JAVA；用户/项目/AgentTask/模型调用/态势快照/总结草稿/记录均为 0且验证前后未变。临时本机服务已停止，原 PostgreSQL 保留。
- Java 离线 package、200 个 Python 源码/迁移/契约脚本 AST、20 个 Schema 元校验、PowerShell 语法、Compose 静态解析与 Git 空白检查通过。Compose 解析所需内部凭据仅注入当前检查进程；没有改写本地环境文件。最终 Agent 镜像为 7b19958124cf，无网络临时容器确认已安装项目态势管理命令。未运行自动化测试、创建业务样本、调用模型、提交/推送或生产部署。
- 真实事项统计、总结确认/并发重放、历史 hash 和权限撤销仍待实际业务数据验收。下一步继续安全基线、扫描/质量趋势及外围投影，然后完成 Flyway 单一迁移入口与最终拓扑、旧后端退出；整体目标保持 active。


## 2026-10-22：安全基线、质量趋势与外围投影交接（059）

- Java SecurityBaselines/Store/Controller 接管扫描工件导入/列表、风险列表/处置、工件解释、质量趋势、基线创建/列表、人工确认/记录列表十个接口；PeripheralRuns/Store/Controller 接管外围投影创建/列表两个接口。复用原有确定性规则与输入结构，不增加模型或扫描调用。导入精确保存用户提供的 UTF-8 原文字节与摘要，实际文件及登记与业务引用关联；不将用户声明的扫描字段当作平台执行扫描的证明。
- 基线选择限定项目、仓库及目标完整 SHA，复核实际工件字节/hash，按一致事务视图固定工件清单、扫描器/规则/覆盖和风险状态。风险处置只由 REVIEWER/ADMIN 写入 OPEN/ACCEPTED_RISK/REMEDIATION_CLAIMED；基线确认锁定真实快照，保存独立的人工确认记录。幂等、审计及正式变更同事务，确认重放保留原记录和理由，不覆盖历史。
- 质量趋势保留同仓库/类型/扫描器名称及版本/规则版本的分组口径，批量读取所选工件的实际风险。三种外围运行严格只接收其专用已有输入；质量投影要求至少两份同组的明确选择工件，按真实时间排序并固定当次数据。运行成功仅表示确定性投影已保存，不表示执行扫描、模型回答、交付裁决、安全通过或发布。UTC 微秒格式提取为共享 UtcTime，原项目态势表现不变，历史 hash 未重写。
- 059 新增 security-baselines、peripheral-profiles 两项写入权和五个原表守卫。扫描输入、基线、确认记录、外围投影不可变；风险更新只能改变人工状态/理由/操作者/时间。旧 Python 四个安全写入口及外围创建入口均检查同一所有权。网关、启动脚本和独立管理 CLI 已接入。
- 本机 058→059 实际迁移成功，五个触发器存在；12 条实际 SELECT 通过 PostgreSQL JDBC describe 元数据检查，无虚构业务参数或业务样本查询。Java readiness 200/059、Python Worker RUNNING、实际管理 CLI 激活两项 JAVA 所有权，两个旧守卫均返回 BUSINESS_OWNER_MISMATCH。十八项写入权均 JAVA；用户、项目、AgentTask、模型调用、态势/总结和五类安全/外围记录共十二张表均为 0，验证前后未变；问答运行也为 0。临时本机服务已停止，保留原 PostgreSQL。
- Java 离线 package、201 个 Python 源码/迁移/契约脚本 AST、20 个 Schema 元校验、PowerShell 语法、Compose 静态解析和 Git 空白检查通过。最终 Agent 镜像实际构建成功（7ab7d61336ad），无网络临时容器确认两项管理命令已安装。源码路由盘点：旧 FastAPI 的 105 个方法/路径均能在 Java 找到参数名归一后的对应映射（Java 共 155 个方法/路径）；这是静态覆盖证据，尚不是 HTTP 行为或历史兼容验收。
- 未运行自动化测试、创建业务样本、调用模型/扫描器、提交/推送或生产部署。真实工件导入/角色撤销/基线确认/历史制品、竞争重放与前端业务仍待实际数据验收。下一步完成 Flyway 单一 Schema 入口、默认开发拓扑和路由/凭据收敛，再停止旧业务进程；整体目标保持 active。


## 2026-10-22：Flyway 交接与默认开发拓扑收敛（060）

- 增加独立 Java `db migrate|handoff-alembic|validate` 入口，复用 Spring Boot 管理的 Flyway 12.4.0 及 PostgreSQL 模块。普通应用关闭自动迁移，只检查 Flyway 版本、Schema 所有权及完整十八项 JAVA 写入权。迁移器不启动 Spring 业务组件，不接收 JWT、模型或 Worker 凭据；不提供 clean，自动 baseline 关闭。Java 与旧 Alembic 共用数据库迁移锁；存在 Flyway 历史或交接标记时，旧在线迁移入口拒绝运行。
- V59 结构基线来自实际已到 059 的 PostgreSQL 16.15/pgvector 0.8.7，只含 DDL 和必要写入方元数据；新库不创建用户、项目或演示业务。比较覆盖实际 90 张表的 1711 项列、约束、索引、触发器、函数和扩展定义，忽略数据、ACL 和对象所有者。旧库须显式 handoff，结构不匹配或旧执行未结束会拒绝；交接前锁定并复核全部写入方，再显式 baseline59→SQL60，保留 Alembic 历史表。
- 本机原库实际交接及 Flyway validate 成功，原90张表记录数前后相同，历史为59/BASELINE、60/SQL。新空库首轮检查揭示两处历史删列的物理序号空位、45处 CHECK 和3处部分索引的等价数组转换表达式；逐项核对后只接受原 Alembic 与 pg_dump 恢复两个完整摘要，不忽略整类约束。当前 V2 比较显式使用完整文本对象名，避免 PostgreSQL name 类型截断；原V60的审计摘要/查询保留，未改写已应用的V60或业务hash。
- 隔离的真实空 PostgreSQL 实例完成 SQL59→SQL60 初始化、validate 与重复 migrate，历史无重复项；两种路径都确认十八项JAVA写入方。临时实例已停止删除，没有持久业务样本。旧 Alembic upgrade 真实返回“Business schema is owned by Flyway”。Java 本机 readiness200/60、独立 Python RUNNING 通过，临时本机进程已停止。
- 默认 start.ps1 切为独立开发 Compose，先停止本项目旧 API/Worker，再执行 Java 迁移并启动 PostgreSQL/Redis/Java/Agent/网关/Vue；`-Refactor` 保留兼容，旧库交接显式使用 `-HandoffAlembic`。网关所有业务路由进入Java，保留长Git/平台发现请求的超时；内部API仍不暴露。Python无业务库/JWT/管理凭据，旧制品卷只读、新Java制品和Git缓存独立可写。旧源码、原开发历史配置及用户生产文件保留。
- 已实际执行新的 `start.ps1 -Rebuild`，Java、Agent、前端镜像构建和Java迁移完成，六个开发服务成功启动。原PostgreSQL容器因本机端口绑定收敛被重建，但实际仍挂载 `infra_postgres-data`，未删除或重置卷。前端HTTP200，网关及前端代理的 readiness均200/schema60，未登录auth/me为401、外部internal路径为404；Agent健康为RUNNING，Redis PONG。真实Agent容器的业务凭据列表为空；验证时供应商凭据在当前进程覆空，实际生成凭据未配置。
- Java离线package、Vue vue-tsc/Vite build、201个Python源码/迁移/契约脚本AST、20个Schema元校验、PowerShell解析/真实执行、Compose解析及Git空白检查通过。Docker首次基础层下载短读已终止后重试成功。新开发服务保留运行，用户可在 http://localhost:5173 查看；当前用户/项目/AgentTask/模型调用仍均为0，Flyway历史仍只有59/60，没有触发模型、扫描器或业务样本。
- README已更新默认入口、API端口、显式Schema交接与生产配置状态。用户现有生产文件仍是旧Python拓扑，未执行或宣称已迁移生产；生产目标配置、真实用户/Idea/仓库/资料的规划→核验→审批发布、实际委派/取消/缓存，以及历史记录兼容仍待完成或验收。未运行自动化测试、提交/推送或生产部署，整体目标保持 active。


## 2026-10-22：生产目标配置、事件有界读取与真实输入准备（061）

- 新增叠加于开发拓扑的 `infra/docker-compose.devproof.prod.yml`、独立生产 Nginx 模板与空凭据示例；复用原静态前端 Dockerfile。合并后只有静态前端公开80/443，数据库不映射宿主端口，开发网关及源码挂载退出生产拓扑，Agent无业务库/JWT/管理凭据；项目名与原生产卷命名空间保持一致。原四个用户生产文件逐一摘要对照未变。
- 实际构建静态前端镜像，在本机临时端口使用显式信任的localhost证书验证 HTTPS、实际编译资源、History路径、Java readiness代理、未登录401、internal404和HTTP301；Nginx配置检查通过。临时前端容器已停止移除，未运行生产数据库或部署生产环境。资源上限只是初始配置，没有容量验收。
- Java旧运行事件查询改为默认最新200条、1—200可选页大小及同运行before游标，页内按时间正序，响应保留items并增加has_more/next_cursor。V61增加(run_id,created_at,id)索引。十五条实际SELECT通过JDBC describe元数据检查；实际60→61迁移/校验、独立新空库SQL59→60→61/校验/重复迁移通过，业务记录未因此增加。默认Java镜像已更新；Docker DNS解析使网关可在Java容器更换后刷新地址，实际网关/Vite代理readiness均200/schema61。
- 用户随后明确授权准备真实输入并执行一次可能付费的真实规划，提供自行注册所需账号信息。实际注册成功后，/auth/me返回503；诊断使用该真实账号定位到MyBatis将单UUID参数当作Bean读取id，根因为缺少UUID TypeHandler。增加PostgreSQL UUID处理器并通过现有MyBatis包扫描统一注册；Java离线package及Docker构建通过，本机服务更新后真实login和auth/me均200。没有运行自动化测试或改动业务权限规则。
- 已通过正常Java API为用户建立DevProof实际项目、ADMIN成员、指定仓库登记和实际Idea“DevProof 需求规划与交付核验架构重构”。Idea来自用户指定的计划书，明确区分冻结代码与本机未提交实现；准备材料在忽略目录`.build/real-planning-input.json`，其中保留原计划书SHA256和真实目标，不保存密码或令牌。
- 当前实际记录：users/projects/git_repositories/ideas/idea_revisions各1，repository_snapshots/planning_runs/agent_tasks/model_calls均0。主机及实际Java容器对DevProof远程执行git ls-remote均成功但没有refs，当前没有可抓取提交，不能形成带仓库依据的规划输入。用户邮箱已补齐，可用仓库地址/提交仍待补充；没有用空快照、替代仓库或固定回答补位，也尚未调用模型。已有授权继续有效，无需重复请求模型费用授权。
- 为避免配置未启用的后台Worker领取实际规划，准备期间暂时停止原Agent容器；确认无任务后已恢复同一容器，保留其原生成凭据未启用的配置。实际规划届时只执行一次，不启用无限后台模型消费。人工计划确认、其他模型任务、自动化测试、提交/推送和生产部署尚未执行；整体目标保持active。第15节十二项完成定义已逐项记入task_plan，真实任务/委派/取消/核验/审批/缓存及历史兼容仍待验收。


## 2026-10-22：Flaskr 真实规划、委派与草案验收（062）

- 用户授权自行选择验收仓库后，选取Pallets官方Flask仓库，固定实际提交 `d086db856be187255b8ec61ef409357393020f32`。通过正常Java API创建“Flaskr 规划验收”项目、仓库和“Flaskr 博客文章列表分页”需求，冻结142个文本文件/630390字节；博客查询、模板、schema及相关原验证入口均在快照内。仓库代码仅被读取，没有执行或修改。
- 使用已配置的DeepSeek生成模型，通过实际Java任务领取、续租、受控工具、共享Runtime和结果接受链路执行同一需求。三次真实执行的历史均保留：第一次12轮后BUDGET_EXHAUSTED；第二次父子Agent均完成但候选被Java以PLANNING_RESULT_INVALID拒绝；第三次SUCCEEDED并生成DRAFT。前两次均未产生正式计划，第二次原始候选未保留，不能确定具体拒绝字段。没有将失败改写为成功或人工修正模型候选后冒充原输出。
- 首次实际执行暴露出文件读取边界不透明、子Agent耗尽父级共享轮数的问题。Java read_file保留每次最多200行，起始行须在文件内，末行超出EOF时返回实际末行与总行数，错误明确有效范围；Python工具描述同步。Runtime每轮传入真实剩余模型/工具/子Agent/时间预算，在根Agent最后一轮及子Agent需要为父级保留一轮时停止提供工具，要求结构化收尾；余下不足两轮时拒绝新委派。工具失败事件记录真实errorCode。注册表已重新从代码导出，同步Java镜像资源。
- 第三次原始候选摘要与实际resultHash一致，Java接受正文与模型原始候选逐对象相同。生成3个工作项、14条验收、3条产物依赖和13处完整SHA/路径/行号引用。当前实际任务和PlanningRun均SUCCEEDED，PlanVersion为DRAFT。第三次子输出出现MODEL_SCHEMA_INVALID，主Agent处理错误后使用自己已读取的材料完成有效草案；因此不将这次运行描述为全部子Agent均成功。第二次完整父子Agent完成事件另有真实记录。
- 三轮各有12次MODEL_TURN_COMPLETED，实际用量分别为107934、140076、129296个provider-reported total_tokens；这些是调用事件统计，不能解释为账单金额。每轮委派事件中的childInstanceId与子事件agentInstanceId、parentAgentInstanceId相符；真实取消仍未执行。
- 已在浏览器用实际账号登录并读取真实项目，需求规划页面显示待确认版本、三个可编辑工作项、验收及依赖和确认入口。截图保存于忽略目录`.build/real-flaskr-plan.png`。用户明确选择“保持草案，稍后审阅”，因此未执行确认，也未推进依赖确认计划的核验绑定。
- `contracts/real-samples/flaskr-planning-2026-10-22.json`保存实际公开仓库与冻结摘要、真实需求、HTTP读取投影、模型原始接受候选、三次运行状态/用量和委派/失败事件。保存前核对结果摘要与正文一致，并排除账号联系方式及部署凭据；它是实际执行记录，不被启动流程导入业务库。
- Java离线package、两处Python AST、Docker Java/Agent镜像构建及Git空白检查通过，未运行自动化测试或构造测试业务数据。独立单次执行器已退出，常驻Agent已更新为修复镜像并保留原生成凭据未启用配置，实际密钥仍在本地受忽略环境文件中。最终Java注册表资源同步更新，Schema仍61。没有继续触发模型、确认计划、提交/推送或生产部署；真实核验/审批发布/缓存降级/取消/历史兼容仍未完成，整体目标保持active。
