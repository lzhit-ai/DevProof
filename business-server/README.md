# DevProof Java 业务服务

JDK 21、Spring Boot 4.1.1、MyBatis 4.0.0。正式 Schema 继续由 backend/migrations 的唯一 Alembic 入口演化，本服务不自动建表或迁移。

已实现：注册及旧 PBKDF2/JWT 登录兼容、项目/成员与核验任务/轮次管理、GitHub 来源/同步/PR 修订和资料关联、仓库感知规划和计划核验绑定、核验输入/代码证据/候选接受/正式裁决、报告与审批发布、固定发布正文 Redis Cache-Aside、内部任务中心。Python Worker 经内部任务与受控工具 API 执行规划和分阶段核验，正式结果由 Java 校验后提交。资料/检索、编排配置及外围聚合继续迁移。

本地构建（不运行测试）：

```powershell
mvn '-Dmaven.test.skip=true' package
```

配置：`JAVA_DATABASE_URL`（JDBC URL）、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`JWT_SECRET`。Worker 凭据通过 `AGENT_WORKER_CREDENTIALS` 的 JSON 对象注入，键为 Worker 身份，值为独立服务密钥；不要使用用户 JWT。
缓存读取前检查项目权限，只有已物化的发布正文进入 Redis；历史正文不回填猜测，沿用不缓存的查询。Redis 不可用则回源 PostgreSQL。

写入方保存在 `business_write_owners`，新增配置默认 PYTHON。`start.ps1 -Refactor -Rebuild` 完成迁移和 Java 就绪检查后，使用独立 `BUSINESS_OWNERSHIP_TOKEN` 依次交接报告、核验/输入、注册、项目/任务管理及 GitHub 来源，再启动应用。核验交接要求旧核验任务全部结束；GitHub 交接要求旧同步执行排空，未领取请求交给 Java 继续处理。普通 Agent Worker 不接收管理凭据。旧入口及数据库触发器同时检查写入方，旧拓扑启动要求沿用重构拓扑。

Java 核验消费者在结果接受和运行完成的同一事务保存 `report_generation_jobs`。Java 队列通过短事务、SKIP LOCKED 和嵌套保存点生成草稿，成功事件与正文同事务提交；失败保存实际错误和受限重试。人工裁决只追加记录，并同步刷新可编辑草稿；发布冻结正文及计划基线。

报告 v1 hash 使用 UTF-8、按键排序的紧凑 JSON；结果数组沿报告条目的顺序，保留 null，关闭非 ASCII/斜杠转义并使用小写 Unicode 控制字符转义。人工决定时间按 UTC 输出六位微秒（零微秒省略小数）。历史存储 hash 不因切流重算；命令幂等使用原始请求字节，业务变更和响应记录在同一事务提交。真实历史数据兼容与完整审批流程仍待验收。

`verification` 模块已实现准备/正式输入冻结、核验建单、候选校验、确定性对账和终态事务。045 加入核验守卫及 Attempt 模型审计；046 加入注册守卫；047 加入项目/任务守卫；048 加入 GitHub 来源守卫和同步执行方。网关把对应管理、来源和核验命令交给 Java，本机七项所有权已实际激活 JAVA，真实业务与历史数据兼容尚待验收。

创建项目时，项目/管理员成员/系统编排、所选仓库连接/Git 登记/同步请求以及知识库挂载同事务提交。Java 同步 lane 使用短领取/心跳/分页提交事务；网络读取在事务外执行，每页的资源修订、PR 交付投影、累计计数和下一页进度原子保存，同步终态另外提交。软删除检查实际活动任务。核验任务只能绑定本项目真实 PR，下一轮须从已发布轮次创建；已有 Git 范围更换交付归属时继续复核仓库身份。

GitHub 读取固定 `https://api.github.com` 和版本头，禁止重定向，优先读取 PR。`GITHUB_SYNC_MAX_PAGES` 默认每批 5 页，每页最多 100 项；达到上限为部分完成，继续同步及失败重试复用已提交的下一页进度。相同连接已有 RUNNING 任务时重复提交返回原任务。匿名额度耗尽时按 `X-RateLimit-Reset` / `Retry-After` 保存恢复时间，恢复前不发请求；网络及次级限流采用有界退避，权限错误直接终止。`GITHUB_SYNC_TIMEOUT_SECONDS`、`GITHUB_SYNC_RESPONSE_LIMIT_BYTES` 和 `JOB_LEASE_SECONDS` 约束实际读取/租约；`GITHUB_SOURCE_SECRET_REFS` 允许环境凭据引用（默认 GITHUB_SOURCE_TOKEN），自定义引用值需在部署中显式注入。计数来自实际保存的响应，`next_retry_at` 返回暂停任务的恢复时间。

Java 新快照使用 `verification-input-v2`，以完整规范化正文的原始 UTF-8 字节计算 SHA-256，正文及版本/hash 同事务保存到不可变 `input_snapshot_bodies`。正文包含已选分块、索引版本、实际脱敏摘录与定位，PR、Git 制品摘要、交付主张、外部退出码、人工来源和指定计划基线。格式见 `contracts/schemas/verification-input-v2.json`；源/分块/引用按稳定顺序保存，JSON 对象按键排序、紧凑编码，读取时校验原始正文 hash，消费者不解析后重编码来计算 hash。旧快照不回填或重算为 v2。

受控制品读取只接受项目内已登记、位于 ARTIFACT_ROOT 真实路径下的文件，验证内容 hash 和大小/编码上限。`VerificationRules` 保留确定性/人工/模型关联、冲突优先、仅精确 Diff 语义支持可得 SUPPORTED 的规则，已由 `VerificationResultConsumer` 调用；自定义能力关联仍作为提示，不能决定正式状态。

上下文工具仅读取本地缓存中冻结 SHA 的登记候选，Python 用 Tree-sitter 提取，Java 复核原文行范围后保存一轮 CONTEXT_ONLY 制品。HTTP 工具使用 `AGENT_TOOL_ALLOWED_HOSTS` 白名单和 `AGENT_TOOL_SECRET_REFS` 授权的环境密钥引用；部署需另向 business 容器注入所需引用的值。模型不控制 URL 或请求参数，响应只保存为 TEMPORARY。新制品写入 `BUSINESS_ARTIFACT_WRITE_ROOT`，开发 Compose 使用独立 java-artifacts 卷，旧 API/Worker 以只读方式挂载以便人工导入。

个人 AI 配置通过 `/api/v1/me/ai-settings` 按登录用户读取、保存及清除；GET 返回服务端支持的模型目录，PUT 只接收 `modelId`、`apiKey` 和 `expectedVersion`，由服务端匹配模型名称及服务地址。切换服务商必须提供对应的新 Key，同服务商切换模型可保留已有 Key。API Key 使用独立的 32 字节 Base64 `MODEL_CREDENTIAL_ENCRYPTION_KEY` 经 AES-GCM 加密，认证数据绑定用户和凭据版本。模型服务域名由 `USER_MODEL_ALLOWED_HOSTS` 及服务端默认地址授权。普通响应只含配置状态和非敏感模型参数。规划、审查、交付主张及问答任务冻结发起者的配置引用；持有对应有效租约的 Worker 才能通过内部接口领取该版本 Key，配置变更后未启动的旧任务需要重新创建。Embedding 配置继续由服务端统一管理。
