# 现状复核

## Git 与运行环境

- 基线 HEAD `eeea296`；origin 已按用户要求改为 `https://github.com/lzhit-ai/DevProof.git`。
- 原有修改：`.gitignore`；未跟踪：backend/.dockerignore、frontend/.dockerignore、frontend/Dockerfile.prod、frontend/nginx.prod.conf、infra/.env.prod.example、infra/docker-compose.prod.yml。保留。
- 根目录及项目下未发现 AGENTS.md；执行用户消息中的“不发送可选 commentary”约束。
- 本机已安装 Java 21.0.11、Maven 3.9.16、Python 3.12。2026-10-21 核对官方资料后，P2 基线锁定 Spring Boot 4.1.1 + MyBatis Starter 4.0.0 + Java 21；尚未执行 Java 构建。
- 未读取凭据或业务数据库；现有数据来源、运行状态及模型可用性尚未验证。

## P0 调查时的写入所有权（后续交接见下表）

| 聚合 | 当前入口/写入方 | 目标交接 |
| --- | --- | --- |
| 用户、项目、成员 | api/routes/auth.py、project_service.py | Java |
| 核验任务、冻结输入 | task_service.py、snapshot_service.py、delivery_claim_service.py、git_service.py | Java |
| 分析运行、队列、租约 | analysis_service.py、worker/main.py | Java 内部任务 API |
| Claim/Evidence、分析候选及正式规则 | infrastructure/legacy_verification.py、code_review_service.py | 先端口隔离；正式规则迁 Java |
| 人工决定、报告、审批、发布 | analysis_service.py、report_service.py | Java |
| 来源解析、资料入库 | source_service.py、worker/source_ingestion.py | Java 管业务；Python 计算工具 |
| GitHub 同步 | external_source_service.py、worker/github_sync.py | Java |
| 检索、索引、知识库 | retrieval_service.py、retrieval_index_service.py、source_service.py | Java 保留 FTS/pgvector/RRF 语义 |
| 编排注册、外围能力与工具 | orchestration_service.py、agent_tool_execution_service.py | Java 管配置；Python 执行 |
| 其他业务聚合 | project_status/security_baseline/peripheral_profile/delivery_association 服务 | P8 逐项交接 |
| 命令幂等记录 | infrastructure/idempotency.py 中独立 SessionLocal 事务 | Java API 交接时迁移；不能遗漏中间件写入 |

## 兼容与业务约束

- 对外入口统一 `/api/v1`，router.py 注册 32 个路由器；前端全部继续使用旧 API，本阶段无流量切换。精确路由清单见 api_baseline.json（从 AST 提取，不加载设置或连接数据库）。
- JWT HS256；密码 `pbkdf2_sha256$310000$<urlsafe-base64-salt>$<digest>`。
- 当前 AnalysisJob/RunEvent 绑定 AnalysisRun，不能用于尚无核验周期的规划任务。
- Worker 主循环串行处理分析、资料入库和 GitHub 同步；三者均有写入，不能只迁分析 Worker 就声明完成。
- 核验图存在一次上下文补充循环，保留 `CONTEXT_ONLY`、冻结 SHA、引用范围、观察事件及正式规则。
- PostgreSQL Schema 唯一迁移入口为 backend/migrations + Alembic，最新 revision `038_project_soft_delete`。Java 暂不运行 DDL。
- report_service.py 的正式记录展示同时组装固定正文及动态字段，P2 缓存前必须单独处理。

## 真实性路径

- start.ps1 默认调用 seed_demo_users；本阶段解除该默认行为，真实用户走现有注册接口。
- seed_demo_data.py 为手动命令，未发现默认 Compose/API 启动调用。保留文件和已有数据。
- API lifespan 无自动迁移/填充。模型使用真实 HTTP 返回，失败使用 DomainError；未发现运行时假成功模型路径。
- CSS 的 demo-user 类名用于展示已登录用户，不代表写死业务记录，本阶段不重命名。

## 未执行

数据库迁移、数据库内容检查、服务启动、自动化测试、真实模型/工具调用、生产操作及推送。

## 技术版本来源

- [Spring Boot 系统要求](https://docs.spring.io/spring-boot/system-requirements.html)：4.1.1 支持 Java 17–26、Maven 3.6.3+。
- [MyBatis Starter 兼容表](https://mybatis.org/spring-boot-starter/mybatis-spring-boot-autoconfigure/)：Starter 4.0 对应 Spring Boot 4.0+、Java 17+，文档依赖示例版本 4.0.0。

## P1 实施结果

- Worker → application/services/verification_workflow_service.py → legacy_verification.py 创建步骤 → workflows/verification_graph.py 编排。
- 编排、状态契约和代码审查输入构建仅依赖标准库/Pydantic/LangGraph，不导入业务 ORM、应用服务或 settings。
- 旧适配器保留全部 11 个业务节点、取消与节点观察逻辑；仍为正式规则和数据库写入方，不宣称已迁入 Java。
- code_review_service.py 保留原调用签名与持久化校验，输入先物化为值对象后交给纯构建函数。
- Java/Worker 契约使用 agent-task-v1；规划/核验运行分开，包含尝试、代次、范围、授权 manifest、预算、事件与工具调用。P3 仍需实现服务端租约、鉴权、幂等和各场景候选校验。
- start.ps1 不再调用 seed_demo_users，不更改已有用户或业务记录。

## 当前交接状态（2026-10-21）

| 聚合 | 当前写入方 | 切换依据 |
| --- | --- | --- |
| Idea/规划输入/问题/计划版本、计划选择 | Java | 新增聚合，只有 Java 写入；Python Agent 经工具读取及提交候选 |
| AgentTask/Attempt/Event | Java | 内部授权接口；Python 无业务数据库凭据 |
| 报告版本/条目、人工决定、审批、发布与固定正文 | 由数据库 reports 所有权指定；本机已激活 JAVA | 043 配置行和数据库写入方触发器；旧 Python 写入口检查同一共享锁；网关命令路由切 Java |
| 自动报告请求 | Java 核验消费者生产，Java 队列消费 | 与结果接受/运行终态同事务入队，真实 QUEUED/FAILED/SUCCEEDED 事件 |
| AnalysisRun/Manifest、Claim/代码证据/运行对账 | JAVA，本机已实际交接 | verification 配置、旧入口守卫、数据库触发器及新任务消费者；Python 只提交候选 |
| 核验输入/绑定 | JAVA，本机已实际交接 | verification-inputs 配置和写入方守卫；新 v2 正文表保留规范化原始字节 |
| 用户注册 | JAVA，本机已实际交接 | 046 identity 配置及 users 写入守卫，Java 保留旧密码格式，旧注册入口拒绝写入 |
| 项目/成员、核验任务/轮次/交付归属绑定 | JAVA，本机已实际交接 | 047 的 projects/task-management 配置及触发器、旧业务入口守卫、Java 命令与网关路由 |
| GitHub 来源、同步、资源修订、交付事实和资料关联 | JAVA，本机已实际交接 | 048 的 github-sources 守卫、Java 来源 API/有界 HTTP/租约队列/事务化修订与 PR 投影；旧同步领取停止 |
| 知识库及项目挂载关系 | JAVA，本机已实际交接 | 050 knowledge-bases 配置与两表写入守卫，旧创建/挂载/卸载入口拒绝，Java 保留跨项目可见性规则 |
| 资料版本/入库任务、分块及派生索引 | JAVA，本机已实际交接 | 051 的 knowledge-sources 配置及五表守卫，Java 持有队列/版本/接受/索引切换；Python 只返回实际计算产物 |
| 冻结资料检索 | Java | FTS/simple、pgvector、RRF 和元信息排名保留；只接受与快照文档证据 hash 一致的候选，受控工具绑定服务端任务授权 |
| 编排、能力/工具及模板/任务绑定 | JAVA，本机已实际交接 | 052 六表写入守卫、不可变能力版本和原始冻结配置、Java 命令和读取接口 |
| 人工/外部补证、临时工具结果导入 | JAVA，本机已实际交接 | 053 两表写入守卫、轮次锁/当前权限/制品 hash 复核和显式导入；正式证据仍由后续输入冻结创建 |
| Git 仓库/交付快照 | JAVA，本机已实际交接 | 054 双表守卫；Java 管角色/范围/幂等/保存，独立 Python 只返回实际 Git/Diff/符号制品 |
| 交付关联、规则候选及平台发现 | JAVA，本机已实际交接 | 055 双表写入守卫，目标/来源范围检查、固定 token-overlap-v1、人工确认及真实时间线制品 |
| 交付主张生成/确认 | JAVA，本机已实际交接 | 056 独立冻结输入、AgentTask 提取、受控原文读取、候选接受及人工确认 |
| 剩余查询/外围聚合 | 主要仍由 Python 承担 | P8 继续实施，旧后端仍保留 |

当前库是本机空库初始化后的 056，identity/projects/task-management/reports/verification-inputs/verification/github-sources/knowledge-bases/knowledge-sources/orchestration/evidence-materials/git-inputs/delivery-associations/delivery-claims 均 JAVA。实际用户、项目、知识库、资料和模型调用仍为 0；历史数据、密码互通、实际 GitHub/模型和完整业务闭环尚待真实输入验收。

资料计算通道已独立：Python 仅声明解析/MinerU/嵌入与服务身份配置，不导入业务 ORM；Java 客户端验证原文/配置摘要、规范化文本、分块/字符或行定位、向量维度和实际索引身份。资料生命周期及索引已由 Java 队列与业务事务接管，网关切换到 Java；旧入库 Worker 在交接后实际停止领取。当前用户、项目和资料为零，不能据此声称真实上传/入库/重建已验收。发现默认索引版本实际长 66，而原三处字段只允许 64；049 已扩容至 512，保留全部既有值与 hash。

Git 采集计算与资料解析使用独立配置摘要，新增语法引擎版本和预算不会改变已有资料入库任务的配置身份。原 Diff/覆盖/Tree-sitter 算法保留；三点比较的文件上下文使用实际 merge-base，和 Diff 的有效基线一致。实际依赖 tree-sitter-language-pack 1.22.1 默认会尝试在用户缓存下载语法，本机最初缓存不可写，因此实际符号数为 0；已改为构建/环境准备时安装五种固定语法、运行时只读缓存，缺失时记录 PARSER_UNAVAILABLE。真实提交 8aef21c42549..258299c79e12 的两个 Python 文件实际产生 8 个 hunk、12 段符号上下文，摘要校验一致。


交付关联候选的实际旧实现是确定性的 token-overlap-v1，而不是生成模型。Java 保留小写后前 30000 个 Unicode 码点、ASCII 标识符/CJK 二元组、排序/截断、重合计数和原置信度公式；现有 API 字段及 AGENT 来源值继续兼容，但不据此宣称新增模型协作。实际 README、旧关联服务和 NotebookWorkspacePage 源码的词元结果与旧函数分别一致（验证当时 1317/501/822 个）。

GitHub 发现原实现只取时间线中的 PR 编号，可能把跨仓库引用映射到同号的本仓库 PR。新实现按来源 PR 的 API URL 验证同一 repository_slug，仅将已同步目标关联；保存返回时间线的实际结构化制品与摘要、分页/截断和排除计数。依据 GitHub 的 [Issue event types](https://docs.github.com/en/rest/using-the-rest-api/issue-event-types) 对 cross-referenced/source 的定义，source 可能是外部 Issue 或 PR，因此服务端必须独立核对其仓库身份；关联不修改交付完成状态。旧发现接口响应模型声明 snake_case、服务却返回 camelCase 的不一致也已修正。

关联操作用事项行锁串行保存，连接信息读取不额外升级行锁，避免与 GitHub 同步先锁连接/资源再更新事项的顺序形成等待环。实际库没有用户或关联数据；当前证据只覆盖源码/构建、真实文件规则一致性、迁移/启动与写入权交接，没有验证真实关联或历史数据升级。


主张生成原为旧 API 同步调用模型并在同一事务写入候选。现在使用独立 delivery_claim_proposal_runs 和 AgentTask 的 DELIVERY_CLAIM_PROPOSE：不借用 PlanningRun/AnalysisRun。数据库要求三类业务外键恰有一个，任务种类与引用类型一致；新运行保存原始 input_json、UTF-8 hash、来源清单和当前周期。只有 Java 更新主张与运行；Python 不接触业务数据库。

Worker 在首个模型调用之前主动读取授权原文，校验原始字节摘要、输入 Schema 和项目/业务引用，再将实际 input 放入模型上下文；不依赖模型主动调用读取工具才能看到材料。模型只获主张提取所需的重读能力，没有仓库/正式 Evidence ID/计划引用。Java 接受时重新检查用户角色、当前轮次/PR 绑定、资料仍就绪且已挂载、未冻结正式输入/未确认主张；输出仍为候选，不自动确认或生成正式核验结论。

提议接口现在返回 HTTP 202 和真实 run_id/agent_task_id/poll_url。NotebookWorkspacePage 已同步支持真实任务状态、取消和刷新恢复跟踪，跨任务/项目/卸载后的旧回调不会覆盖当前页面。GET 与人工 PUT 主张列表保持既有响应形状；MODEL/HUMAN key 和哈希计算保留，同样模型内容再次提议时复用现有 key，避免原重复插入的唯一约束冲突。


- 057：运行读取已迁 Java；问答原实现为同步 Python 模型调用且无现有前端调用，现迁为独立任务并保留五种回答状态。问答 citations 是全部输入证据，显式声明 SUPPLIED_EVIDENCE；与正式核验的模型证据关系及人工裁决分别保存。十五项写入权本机均为 JAVA，真实模型和业务验收仍缺实际输入。


- 058：项目态势/总结原实现为确定性事实投影与个人确认，不是模型或交付裁决。已迁 Java 并交接三表写入权；创建使用一致事务视图。原覆盖率将取消事项纳入分子却不纳入分母，新快照已统一为未取消事项范围；历史记录不重算。剩余旧业务入口为安全基线/质量和外围运行投影，之后再交接 Flyway 与部署。


- 059：安全/质量和三种外围投影均为原有确定性业务，已由 Java 接管十二个接口与五表写入权。核验固定 SHA/工件字节/版本/覆盖及人工处置状态，不将投影成功等同于安全结论。源码盘点的旧 105 个方法/路径均有 Java 对应；现阶段旧 API/Worker 仍在过渡 Compose 中，不能将路由齐备解释为已退役。下一步交接 Flyway 和默认拓扑，历史/真实输入闭环仍待验收。


- 060：独立 Java db migrate/handoff-alembic/validate 已成为 Schema 入口，正常应用启动只检查版本。原库通过实际 1711 项定义比对后显式 baseline59→SQL60，原90表记录数未变；新空库真实执行SQL59→SQL60、校验及重跑通过。当前比较使用完整文本对象名，并接受已逐项核对的原 Alembic 与 pg_dump 恢复两个完整摘要；原V60审计摘要与查询档案保留。旧 Alembic 在线入口已实际拒绝迁移。
- 默认 start.ps1 使用独立开发 Compose，网关全部业务进入 Java，Agent 无业务库/JWT/管理凭据，迁移器仅接收数据库配置。原 PostgreSQL 卷身份保留，旧源码和用户生产配置未修改。新的 start.ps1 -Rebuild 已实际启动六个开发服务，前端/网关/代理就绪均200，Agent RUNNING、Redis PONG；实际Agent无业务凭据。生产拓扑与真实业务/历史兼容尚待交接或验收。


- 061：生产目标覆盖配置与独立Nginx模板已实现；实际合并配置、静态镜像及本机localhost TLS/资源/History/Java代理通过，原生产文件摘要未变，没有部署生产。事件读取新增有界游标和V61索引，原库升级及真实空库初始化/校验/重跑均通过，当前Schema61。
- 首个用户授权真实账号揭示MyBatis单UUID参数缺少TypeHandler的实际缺陷：注册和按邮箱登录正常，按id读取在发SQL前出现ReflectionException。统一注册UUID处理器后，实际登录、账号读取、项目/仓库/Idea创建及规划权限读取均通过；仅构建和空库readiness不能替代这些真实请求。
- 用户已授权一次真实规划模型调用；实际账号、DevProof项目和计划书对应Idea已登记。指定远程DevProof当前无refs（主机和Java容器均实际读取确认），未生成仓库快照/规划任务，模型调用数仍0；需要真实可抓取提交后才能继续。未授权提交或推送，不将本机未提交实现冒充远程SHA上的代码。


- 062：真实验收使用Pallets/Flask提交d086db856be187255b8ec61ef409357393020f32及其教程博客，固定142个文本文件/630390字节。真实模型执行三次，同一需求分别出现预算耗尽、Java拒绝、接受为DRAFT；所有历史均保留。最终3个工作项、14条验收、3条依赖、13处完整代码引用已在浏览器实际显示；用户选择保留草案。
- Runtime共享预算需要向模型反馈并为父Agent保留收尾轮数；仅在下次调用时抛出预算耗尽会使实际委派无法回到父级。文件读取应明确200行上限、实际EOF和总行数，避免模型猜测行范围反复失败。对应修复及真实运行均已执行。结构或引用错误仍由Java拒绝；模型完成不代表候选被正式接受。
- 用量统计应以相应任务的实际MODEL_TURN_COMPLETED事件为范围；本轮三次total_tokens分别107934/140076/129296，不是账单金额或全部调用成功率。第三轮子Agent输出Schema失败而主Agent成功，第二轮父子完成而Java拒绝，需分别说明。
- 实际执行记录已保存于contracts/real-samples/flaskr-planning-2026-10-22.json，包含公开来源、真实输入、API读取投影、实际接受候选和运行历史；账号联系方式与凭据未纳入。人工计划确认、下游绑定及其他完成门槛仍需各自真实证据，不据此宣称全部重构验收通过。
