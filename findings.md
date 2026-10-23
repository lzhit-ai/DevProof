# 架构设计发现

## 2026-09-01 PR 交付核验 LangGraph 编排设计

- 当前主链已经具备冻结 Claim、Diff Artifact、代码 Finding、反方复核、Coverage、确定性 reconcile、外围 Agent 及报告审批基础，适合增量重组，不需要引入自由 Supervisor。
- 用户确认方案同时服务面试讲解与后续落地；LangGraph 仅负责自动分析，人工确认、关键业务决定、报告审批和正式留档继续由业务状态机负责。
- 首版输入明确排除 CI/测试平台，仅使用可直接读取和冻结的 PR 元数据、确认主张、可选知识库资料和 Git Diff。
- 人工介入需弱化：部分支持、证据不足和普通 Finding 自动形成结果；只有关键冲突或高风险业务歧义进入关键决策队列。
- 为避免把“证据结论”和“是否需要人工介入”混为一个状态，设计将 `verdict` 与 `key_review_required` 分离；人工决定不得覆盖系统原始裁决。
- 没有 CI 时，`SUPPORTED` 必须限定为“当前冻结代码证据支持”，不能表达为运行、测试、上线或生产验证通过。
- 模型失败不能被解释为没有证据，因此新增 `NOT_ANALYZED` 与 Coverage 区分“分析未完成”和“分析完成但未证明”。

## 2026-08-12 第一性原则全链路复核

- 核验口径：只有当输入穿过声明的边界、产生声明的持久化输出，且下游消费者能实际使用该输出时，才标记为“已验证”。页面可见、类可导入或早先单点成功都不构成可用性证明。
- 当前运行配置按职责分离：DeepSeek 用于生成，DashScope `text-embedding-v4` 是默认 Embedding；本地运行配置中不再保留 Gemini Key。
- 已有隔离实调证明两段正向链路：资料上传 → 768 维语义索引 → 冻结文档证据 → 语义检索；以及公开 Git Diff 冻结 → 固定双核 → 确定性支持 → `PARTIALLY_SUPPORTED` → 需人工确认的报告草稿。
- 未发现自动化测试套件（不存在 `tests/`、`test_*.py`、`*_test.py`），本轮不能把单测覆盖当作证据，将改用定向真实状态流转和直接不变量检查。
- 已知缺口：虽已建模 `credential_ref`，只读 Git Reader 仍未注入非交互凭据。容器可读取公开 Git；当前不能读取 GitHub 私有仓库，不能宣称已支持。
- 运行基线已实际确认：PostgreSQL、API、Worker 与前端容器均在运行，数据库已处于 `023_peripheral_profile_runs` head。直接请求 `http://localhost:8000/health` 返回 HTTP 404，不能以容器 healthy 代替 HTTP 可达性；下一步必须从实际路由确认健康检查的正确契约，或记录为缺陷。
- HTTP 存活与就绪的正确契约为 `/api/v1/health/live` 和 `/api/v1/health/ready`，两者均实际返回成功；Compose healthcheck 也使用该存活路径。因此根路径 `/health` 的 404 是错误探测路径，而不是服务故障。
- 资料链源码复核：上传时先限定 UTF-8/媒体类型/大小并完成逐块 Embedding，只有全部分块成功后才能置为 `READY`；冻结快照时会复制每个分块为 `DOCUMENT` 证据，检索严格按快照中已选资料的 ID 过滤。正式快照同样校验 Git SHA、外部证据 SHA 与轮次归属。
- 待实测的实现风险：`freeze_formal_snapshot` 对 `source_revision_ids` 未显式拒绝重复 ID（与准备快照不同）。当前条件会把 `[同一资料, 同一资料]` 视为一个已选资料，应以可回滚的实测确认该输入是否被错误接受。
- 真实数据盘点已证明资料存储和历史快照不是空壳：最近的 Gemini 隔离资料为 `READY` 且有 3 个分块；双核验收资料为 `READY` 且有分块；最近正式快照包含与资料/外部证据数对应的证据行。下一步将用该冻结快照重新调用检索，而不是只核对数据库行数。
- 历史快照检索复验结果为部分失败：当前默认 DashScope 查询对已由临时 Gemini 生成的 768 维历史索引做中文语义改写检索，实际返回 0 条；同一快照以原文精确词检索可返回 1 条，但仅有 `ftsRank`、没有 `vectorRank`。根因是检索服务用“当前全局模型的 index version”过滤候选，而非按历史分块的 index version 选择兼容查询模型。这意味着切换 Embedding 供应商后，旧索引退化为词法检索，不能满足“冻结快照随时可语义复查”的链路目标。
- 正式快照的重复资料输入已用真实历史快照和事务回滚实测：传入 `[同一 source_revision_id, 同一 source_revision_id]` 被服务错误接受，并直接返回既有快照，而非抛出 `INPUT_INVALID`。该缺陷不会重复写入证据，但破坏了“输入清单必须无重复”的前置契约，和准备快照的行为不一致。
- 为避免把历史验收误作当前可用性，本轮尝试在当前默认 DashScope 配置下完整重跑“建任务 → 上传资料 → 768 维分块 → 冻结 → 检索”。上传阶段实际收到 `MODEL_UNAVAILABLE`，底层为百炼 TLS `UNEXPECTED_EOF_WHILE_READING`；因此本轮不能确认当前执行通道的真实向量写入可用。已确认只留下一个标记为 `first-principles-dashscope-*` 的空白 DRAFT 验收任务（0 资料、0 快照）；未伪造通过结果，也未重试相同调用。
- 双核正向验收的持久化事实已重新盘点：任务轮次处于 `NEEDS_CONFIRMATION`，有 1 个正式快照、1 个 `SUCCEEDED` 运行、1 份冻结编排、1 个 Claim、2 个证据关联、1 个裁决结果和 1 个真实模型调用；自动报告仍为 `DRAFT`，尚未发布。这证明此前双核的“需人工确认”分支确实到达草稿边界，但发布链仍需单独实测。
- Git 冻结完整性已对同一公开验收范围重新实测：用冻结 SHA 重读 Diff 后哈希匹配、Diff 非空且覆盖 1 个变更文件；故意传入错误哈希时准确返回 `INPUT_STALE`。这证明“分支名只是选择输入，运行只读取冻结 SHA 和哈希”的防篡改链实际生效。
- 当前数据库没有任何 `DeliveryItem`。因此可以验证交付结论的发布，但不能在不伪造外部平台事项的前提下验证“正式记录回写真实研发事项状态”这条链；它将明确列为未覆盖，而不是以零数据断言通过。
- 首次构造“确定性确认”隔离运行时，已提交的新任务在同一 SQLAlchemy 会话中依次冻结 Git、外部测试证据和正式快照后立即启动运行，启动服务因会话关闭自动 flush 而看不到刚添加的 `InputSnapshotGit`，返回 `INPUT_STALE`。该组合调用已整体回滚（任务本身已在前一提交边界保留为无输入 DRAFT）；HTTP 正常流程本来将每一步作为独立提交请求，因此这不是对 API 可用性的失败，但说明服务层不能被安全地当成无边界的同事务编排接口。
- 按真实 HTTP 提交边界重建后，隔离运行的 Git 哈希、成功 `TEST` 外部证据、正式快照和 Worker 均实际成功；但最终仍为 `PARTIALLY_SUPPORTED` 且需人工确认，而非代码规则宣称可达的 `CONFIRMED`。因此“成功测试证据 + 支持性代码证据即可自动确认”的裁决链尚未通过；下一步追踪结果原因、Claim 权威级别和关联关系，确认这是正确的保守拒绝还是实现断链。
- 追踪事实已排除权威级别与代码关联问题：Claim 权威级别为 4，且有冻结 Git `CODE` 的确定性 `SUPPORTS` 关联；结果仍走部分支持分支，说明“成功外部测试”没有被裁决识别。需继续检查外部证据的加载/状态判断，而不是把该保守结果误解为资料或代码不足。
- 裁决代码与持久化证据确认了具体原因：`has_passing_external_test` 只查看已成为该 Claim 确定性 `SUPPORTS` 的 `TEST/BUILD` 证据；测试工件也必须先与 Claim 有标识符重叠。本轮第一个成功测试工件不含 Claim 的代码标识符，故没有关联，这是符合当前规则的保守结果，不是 Worker 丢失测试。下一次将提交带有同一冻结变更标识符的成功测试工件，验证自动确认的完整条件。
- 完整条件已实际通过：带 `hello` 标识符的成功 `TEST` 工件被确定性关联后，Worker 返回 `SUCCEEDED`，裁决为 `CONFIRMED`、`requires_human_confirmation=false`，轮次进入 `DRAFT_READY`，并生成报告草稿。由此确认固定双核能够在“权威资料 + 冻结实现证据 + 关联到 Claim 的成功测试”三者齐全时自动确认。
- 待发布的 `CONFIRMED` 草稿已定位，但该隔离项目当前只有提交者这一名 `ADMIN` 成员。系统正确禁止提交者批准自己的报告，因此独立审批必须先让另一现有用户加入此隔离项目；不会用提交者本人绕过审批来制造通过结果。
- 运行库中存在活动的独立演示审核者。其身份和项目成员服务均已定位；将通过实际登录与受保护的“添加成员”接口把该审核者仅加入隔离验收项目，然后才执行审批，确保审批边界用 HTTP 契约而非直接改库验证。
- 已通过 HTTP 实测认证与受保护成员接口：提交者登录成功，并将独立审核者以 `REVIEWER` 角色加入仅用于验收的项目。该步骤提供了可执行的独立审批主体，且没有用直接数据库写入绕过 API/RBAC。
- 报告 HTTP 路由已确认具备草稿提交、批准和发布入口，并将 `AUTH_FORBIDDEN` 映射为 403。首次使用 PowerShell `Invoke-WebRequest` 驱动无请求体的 POST 时，客户端自身抛出空引用异常，未获得可判定响应；将先只读核查草稿未被改变，再改用 `curl.exe` 复验同一 HTTP 链，不把客户端工具异常误记为产品失败。
- 报告审批与发布已通过容器内真实 HTTP 链路验证：草稿直接发布返回 `409 STATE_CONFLICT`；提交者批准自己返回 `403 AUTH_FORBIDDEN`；独立审核者批准返回 `200 APPROVED`；管理员随后发布返回 `201` 和正式记录号。该链证明发布的是内部不可变、可引用的交付核验记录，不是向终端用户发布应用功能。
- 正式记录的持久化约束已复核：报告、轮次均为 `PUBLISHED`，批准动作绑定当前报告哈希/快照哈希/运行，正式记录哈希存在；1 个报告项的 2 条引用都回到同一正式快照的 `CODE` 与 `TEST` 证据。
- 发现严重状态回退缺陷：同一已发布轮次仍保留较早运行产生的 `DRAFT` 报告。对该旧草稿调用 `submit_for_review` 的可回滚实测被错误接受，并会把它置为 `SUBMITTED`（同时把轮次改回待审）。发布后历史草稿没有被封存，也没有在提交服务中检查轮次是否已发布，破坏“发布记录不可回退”的核心不变量。
- 已创建带同一 `hello` 标识符且 `exit_code=1` 的隔离失败测试，作为确定性冲突分支验证输入；Worker 在 49 秒观察窗口内仍未终态，不能写成冲突通过或失败。下一步读取任务租约/运行事件与 Worker 日志，确认是执行中、重试还是阻塞。
- 作业状态和运行事件证明前述等待只是轮询窗口未覆盖 Worker 的领取时间，并非卡死或重试：最终 `SUCCEEDED`。冲突裁决完整分支已实际通过：失败 `TEST` 被确定性关联为 `CONTRADICTS`，结果为 `CONFLICTING`、要求人工确认，并自动创建 1 条风险发现。
- 外部事项与外围 Profile 的源码边界已复核：GitHub 同步可无 Token 读取公开仓库的 Issue/PR/Milestone，只有同步生成的 Issue 才能成为 `DeliveryItem`；项目态势只冻结事项、已发布记录、风险和归属缺口；安全/质量 Profile 只投影已导入的扫描工件，不扫描仓库或调用模型。下一步将以公开仓库创建隔离的真实来源同步，验证事项投影和后续回写，不把手工造的数据库行当作外部事实。
- 公开来源同步已经由真实 HTTP 执行到服务端：连接创建返回 201，但 GitHub `octocat/Spoon-Knife` 同步记录终态为 `FAILED / SOURCE_UNAVAILABLE`，0 条抓取、0 条变更。故当前执行环境不能确认“GitHub 外部事项 → DeliveryItem → 状态回写”全链；将读取已持久化的错误信息后明确归因，不能用此前公开 Git clone 成功替代 GitHub REST 同步成功。
- 归因已收窄：同一 Worker 对 GitHub REST 的单页 Issue 与 Milestone 请求均返回 200，而服务全量分页同步收到 HTTP 422。故这不是“无法访问 GitHub”，而是同步的分页/容量处理缺陷或与该仓库数据规模相关的服务端拒绝；仍需逐页复现定位，且当前同步结论仍为失败。
- 逐页复现已确认缺陷：`octocat/Spoon-Knife` 的 Issue 第 11 页返回 GitHub 422，提示大型数据集不再支持 `page` 分页、需 cursor；现有客户端固定最多 50 页的 page 分页，遇到此情况会让整个同步失败。Milestone 端点正常。该缺陷影响大型仓库，而非网络连通性。为继续验证健康的来源链，正在选择一个分页规模较小的公开仓库；所有候选均只做只读探测。
- 分页较小的公开候选已确认：`octocat/test-repo1` 的完整 Issue 首页只有 5 条，适合在不触发 GitHub 大型分页限制的前提下验证健康的来源同步与 `DeliveryItem` 投影。接下来将把它作为第二个、隔离的只读来源接入同一验收项目。
- 健康小仓库同步已真实通过：连接创建 201、同步 `SUCCEEDED`，抓取并写入 5 个外部资源与版本。但这 5 条均为 `PULL_REQUEST`，而产品定义只把同步来的普通 `ISSUE` 投影为 `DeliveryItem`，所以 `DeliveryItem=0` 是符合现有边界的结果，不能作为“事项投影成功”的证明。需要再选择含普通 Issue 的小仓库。
- 含普通 Issue 的公开来源 `octocat/git-consortium` 已真实同步成功：54 个资源、93 个变更，并投影出 39 个 `DeliveryItem`；新事项起始为 `NOT_ASSESSED`。来源同步 → 外部资源版本 → 研发事项投影链已通过。该仓库公开 Git 的默认分支为 `master`，可用于后续同源 Git 冻结验证。
- 已通过 HTTP 创建绑定真实 `DeliveryItem` 的隔离核验任务，并注册同一外部仓库的只读 Git、冻结 `master~1 → master` 差异、冻结正式输入并排队双核运行。任务—事项和 Git—来源使用同一仓库，未以跨仓库引用冒充验收；下一步等待其如实裁决后再决定是否可发布并回写事项状态。
- 事项状态回写链已真实通过：同源 Git 的运行如实裁决为 `INSUFFICIENT_EVIDENCE`，报告经独立审核后发布；对应真实 `DeliveryItem` 从 `NOT_ASSESSED` 更新为 `INSUFFICIENT_EVIDENCE`，且已有正式记录 ID。这里验证的是“已发布的核验结论回写事项”，不是把外部 Issue 关闭或宣称 Issue 已交付。
- 发现事项—代码来源一致性缺陷：任务绑定某 `DeliveryItem` 后，服务仍会接受同项目内任意 `GitRepository` 的冻结范围。以同一真实事项（来源 `octocat/git-consortium`）和不同仓库（`octocat/Hello-World`）的可回滚实测被接受。当前只校验“同项目”，未校验 Git 仓库是否等于事项的外部来源仓库；这会允许错误的用户确认跨仓库关联，必须补充来源一致性或显式跨仓库豁免的可审计机制。
- 项目态势外围链已通过真实 HTTP 验收：冻结健康快照正确统计 39 个事项（1 个 `INSUFFICIENT_EVIDENCE`、38 个 `NOT_ASSESSED`）并显式标出 `UNATTRIBUTED_GIT_ACTIVITY`；日报草稿与个人确认记录均成功创建；`PROJECT_STATUS_SUMMARY` 专用 Profile 返回 `SUCCEEDED`。它没有进入双核，也没有把 Issue 状态写成“已完成”。
- 安全/质量外围链已通过“已导入工件”的控制面验收：导入了明确标记为 `fixtureOnly` 的 2 个 SAST 时点和 3 类同 SHA 工件，安全基线涵盖 SAST/DEPENDENCY/SECRET/CONFIG 后确认成功；`SECURITY_BASELINE` 与 2 点 `QUALITY_TREND` Profile 均返回 `SUCCEEDED`。这只验证导入、冻结、投影与边界，不构成对公开仓库的真实安全扫描或安全结论。
- 私有 Git 复探测仍以 `GIT_TERMINAL_PROMPT=0` 退出 128（不可交互用户名/凭据），与代码中未使用 `credential_ref` 的事实一致；私有仓库验收仍未可用。前端生产构建通过。一次后端 `compileall` 命令因在 `frontend` 工作目录中错误寻找 `infra/.env` 而没有执行，须回到仓库根目录重跑后端静态检查。
- 回到仓库根目录后，后端 `compileall` 与 `git diff --check` 均通过。自定义 Agent/工具的边界源码已复核：能力只能为 `SHARED`，不能替换双核；HTTP 工具必须由管理员登记为无凭据 HTTPS 且命中服务端白名单。当前 `AGENT_TOOL_ALLOWED_HOSTS` 为空，因此任何 HTTP 工具都应被拒绝，不能伪称已可执行。
- 自定义能力生命周期已开始真实验收：默认模板含 7 个固定/系统能力节点；尝试登记 `HTTP_QUERY` 返回 403（白名单为空）；`SHARED` 外围能力与其第二个 Prompt 版本均已通过 HTTP 创建。下一步会将该新版本连同固定节点编入独立模板，冻结到一次运行中，验证其不能越过双核裁决。
- 自定义 Prompt/编排隔离链已实际通过：含 7 个固定节点与 1 个 `SHARED` 节点的模板被绑定并冻结到运行；自定义模型调用成功、没有工具执行，也没有产生模型 `SUPPORTS` 进而改变最终 `PARTIALLY_SUPPORTED` 裁决。停用该能力后新版本请求返回 409，而该次已冻结运行仍保留其节点快照。当前工具链已验证“受白名单限制地拒绝”，但由于白名单为空，尚未验证一个真实 `HTTP_QUERY` 成功执行后的临时结果和人工导入链。
## 2026-08-12 百炼 Embedding 接入

- `DocumentChunk.embedding` 使用 `Vector(768)`，因此百炼 `text-embedding-v4` 必须显式请求 `dimensions=768`；不能接受服务端默认维度。
- 当前生成模型与 Embedding 模型通过独立端口和环境变量配置；本次只替换资料入库与查询阶段的 Embedding，不改变双核核验、冻结 Git Diff 或正式结论规则。
- 使用用户提供的工作区 OpenAI 兼容地址 `/compatible-mode/v1/embeddings`；Key 仅写入被 Git 忽略的 `infra/.env`，不能写入 Compose、示例或文档。
- 历史 FakeEmbedding 向量与百炼向量不能混用。当前本地 Compose 的 API、Worker、PostgreSQL 与前端正在运行，代码和环境变量更新后必须重建 API 与 Worker；后续真实资料入库将直接生成百炼向量。
- 用户已在本机 Worker 中通过项目真实适配器完成调用，返回 `dashscope`、`text-embedding-v4` 和 768 维向量；这验证了百炼凭据、兼容地址、请求格式及维度契约。尚未以真实上传资料单独验收解析、入库和检索全链路。

## 2026-08-12 Gemini 临时验收发现

- 当前执行通道已真实调用 Gemini `gemini-embedding-001` 并得到 768 维向量。该模型默认返回 3072 维；请求必须显式指定 768。容器安装的 Google GenAI SDK 已提供 `EmbedContentConfig(outputDimensionality=...)`。
- `create_source_revision` 在 API 请求内同步完成解析、分块、调用 Embedding 和写入 `DocumentChunk`，不是由 Worker 延后执行。`search_snapshot` 会为问题生成向量，并在模型异常时退回关键词检索；全链路验收必须确认结果含 `vectorRank`，不能仅凭命中资料判定成功。
- Gemini Key 只能暂存于被 Git 忽略的 `infra/.env`，验收后恢复 `EMBEDDING_PROVIDER=dashscope`。代码中只保存供应商通用配置和模型名，不保存 Key。
- `SessionLocal` 关闭自动刷新。真实产品在“资料上传”“冻结快照”“快照检索”三个独立请求中分别提交，因此可正常看到分块；将三步塞进一个未提交会话会使快照查询不到尚未刷新的分块。回滚诊断已证明修复后的快照逻辑可把一个带供应商索引版本的分块写为一个 `DOCUMENT` 证据；正式验收将按真实请求边界分三段执行。
- 旧快照服务按 `index_version=parser_version` 读取分块，与新的 `markdown-v1|embedding:<provider>:<model>:d768` 索引版本不兼容。已改为按来源版本读取其当前全部分块；来源版本当前只在上传时产生一组分块，不会改写既有快照。
- 按产品实际的“上传资料并提交 → 冻结快照并提交 → 查询快照”边界验收通过：Gemini 临时模型写入 3 个 768 维分块，冻结得到 3 条 `DOCUMENT` 证据，语义改写问题返回 3 条结果并携带 `vectorRank`，因此确认走到了向量排序而非仅关键词兜底。
- 本次修复还覆盖本地升级阻断：迁移 015 先把 `alembic_version.version_num` 从 32 扩至 64，开发库已升级到 023。该迁移只调整迁移元数据字段长度，不重写业务记录。

## 2026-08-12 双核编排运行验收

- `orchestration_fingerprint` 与 `freeze_run_orchestration` 原先各自构造模板哈希输入：后者多了模板 `name`，导致每次启动分析运行都触发 `ORCHESTRATION_CHANGED`，双核图从未进入 Worker。
- 已抽取单一 `_template_snapshot` 作为预检哈希和冻结运行快照的共同输入；它不改变模板节点、双核必需项、Git Diff 冻结策略或任何历史运行。
- 使用公共仓库的只读冻结 Diff 和隔离验收资料完成真实运行：`create_claims`、`collect_git_evidence`、`reconcile` 三个节点均成功；一个 Claim、一个代码证据和确定性 `SUPPORTS` 关联形成 `PARTIALLY_SUPPORTED` 结果，仍要求人工确认；自动报告草稿也已生成。
- 私有仓库远程地址在 API 容器内会要求 GitHub 用户名/凭据。现有 `GitRepository.credential_ref` 尚未被只读 Git Reader 注入，私有 GitHub 验收仍是明确缺口。

## 2026-08-11 Agent 生命周期切片审计

- 当前编排 API 已具备创建自定义 `SHARED` Agent、创建只读 HTTP 工具、创建任务模板、为任务绑定模板，以及为能力创建新版本的基础入口；前端只覆盖了创建，没有把版本编辑、停用和任务模板绑定暴露为可操作工作流。
- 固定双核仍由系统能力和固定编排约束保证；本切片只允许操作自定义 `CUSTOM` 能力，不能编辑、停用或替换系统能力。
- 停用能力后，历史运行与已冻结编排保持可追溯；新建版本、模板校验和任务绑定必须拒绝停用能力，避免让历史配置悄然成为新的运行配置。
- 任务绑定需要读取项目内真实任务与其当前模板绑定，不能要求用户粘贴 UUID，也不能以模板关联推断交付已经完成。
- `bind_task_template` 已在服务端重新校验模板节点；因此停用能力后可自然阻止旧模板再次绑定，但需要让工作台显示当前绑定及“不可再绑定”的原因。
- 编排工作台保留了能力块、工具授权、编排模板三个页签和已有的分隔线式布局；新增操作应在这三处就近展开，避免再创建另一套配置页。
- 服务端模板校验已经筛除 `is_active = false` 的能力；但创建新版本目前未检查停用状态，且编排列表没有暴露版本内容或任务绑定投影，这正是本切片需要补足的服务契约。
- `list_tasks` 已有项目内任务读取投影，但不返回编排绑定；在编排模块内新增受角色保护的任务绑定投影，比让前端跨模块拼接 UUID 更能保持边界清楚。
- `TaskOrchestrationBinding` 本身已保存模板版本与绑定时间，足以形成可追溯的“任务当前编排”投影，无需新增迁移或改变历史运行快照。
- 生命周期操作只需新增服务方法与 API：读取指定能力的最新版本、停用自定义能力、列出项目任务绑定；所有写操作保持提交者/管理员角色和幂等键约束。
- 已补齐生命周期服务契约：系统能力不可停用、停用后的自定义能力不可再创建版本；版本内容只读返回用于从上一版创建新版本；任务绑定投影保留绑定的模板版本和可用性标记。
- 本切片没有改变 `AgentCapabilityVersion`、`TaskOrchestrationBinding` 或冻结运行快照的数据结构，因此无需迁移，也不会改写历史编排或正式记录。
- 静态检查中后端 `compileall`、空白字符检查和 Agent 页面样式检测均已通过；首次在仓库根目录运行前端构建失败，因为前端包位于 `frontend` 子目录。后续构建改在该目录执行，避免重复同一失败命令。

## 2026-08-11 事项—变更候选切片审计

- `DeliveryChangeLink` 已有 `AGENT + CANDIDATE` 数据语义和唯一目标约束，人工确认会将同一链接升级为 `USER + CONFIRMED`；因此候选工作流应复用该对象，而不是新增另一份平行关联记录。
- 当前交付核验图中的 `model-link-proposal` 只针对 Claim—Evidence 关联，不会创建事项—PR/Git 范围关联；两类“链接建议”必须保持分开，不能把证据引用建议误写成项目事项关联。
- 候选的合法目标只能是同一项目已同步的 PR 或已经冻结、且所属任务绑定同一事项的 Git 范围。候选不影响事项状态、完成率、正式记录或核验结论。
- `confirm_change_link` 已经是正确的人工升级入口：若同目标已是候选，它会在同一记录上改为 `USER + CONFIRMED` 并补齐确认人、时间与审计事件；新候选只应调用同一内部校验与去重规则。
- 现有前端尚未展示事项—变更链接，因此本切片需要在“研发事项 / 交付项”真实项目页面增加候选列表和确认动作，而不是把候选塞进 Agent 配置页。
- 已同步的 Issue/PR 修订有标题、正文、版本与内容哈希，可作为候选 Agent 的受控文本输入；Git 范围只能从已绑定同一事项的核验任务中选择。不能把任意工作区代码、提交记录或网络结果放入候选输入。
- 现有生成模型端口只定义 Claim—Evidence 建议和证据问答。为避免把不同任务的输出协议混在一起，本切片采用可审计的受控词元匹配候选器，并将其明确标识为 `AGENT + CANDIDATE`，不调用模型、也不依赖 API Key。
- 候选运行需要单独持久化输入清单、输入哈希、规则版本和计数，再把新建候选链接回指该运行；这保留了“为什么提出”而不把候选误当成正式事实。需要新增第 022 号迁移。
- 候选 Agent 已采用受控目标池：最多 20 个用户显式选择的同项目 PR 或同事项已归属冻结 Git 范围；每次运行保存输入清单/哈希和规则版本，只写 `AGENT + CANDIDATE`。人工确认复用既有正式关联入口。
- 前端生产构建已通过；同一批命令在 `frontend` 子目录执行时找不到仓库根目录的 `.venv`，因此后端静态编译需改在仓库根目录单独执行，避免重复错误路径。

## 2026-08-11 安全解释与质量趋势切片审计

- 安全扫描工件与风险都已绑定项目、仓库、目标 SHA、扫描器/规则版本、覆盖声明和导入时间；可以不新增表，通过只读投影生成定向解释和质量时间序列。
- 趋势不能跨扫描器、扫描器版本、规则版本、扫描类型或仓库比较。每条序列必须按这五个维度分组；换版本或规则只显示为新序列，而不是伪造“风险升降”。
- 安全解释只能汇总选定工件内已导入风险的严重度、处置状态、分类和覆盖限制；它不读取工件之外的仓库内容，不调用模型，也不输出“安全通过”。

## 2026-08-12 非交付 Profile 专用运行审计

- 非交付 Profile 不能复用 `AnalysisRun`、`InputSnapshot`、固定双核图、报告草稿、审批或发布链路，否则项目管理与安全治理会被误写成一次 Git Diff 交付核验。新增的 `PeripheralProfileRun` 只接受三类已冻结的专用输入，并固定为同步完成的确定性只读投影。
- `PROJECT_STATUS_SUMMARY` 以 `ProjectHealthSnapshot` 为唯一输入；`SECURITY_BASELINE` 以 `SecurityBaselineSnapshot` 为唯一输入；`QUALITY_TREND` 以至少两个严格可比的 `SecurityScanArtifact` 为唯一输入。服务端再次校验项目归属、输入专属性、重复选择和趋势可比性，前端不承担边界校验。
- 外围运行冻结输入清单与输入哈希，并保存输出、覆盖和限制。它们可作为后续总结/追溯的来源，但不会修改项目总结记录、安全基线记录、事项状态、交付核验结论或正式发布记录。
- 023 迁移为外围运行建立独立表和非交付 Profile 约束；离线 SQL 校验时临时 `JWT_SECRET` 首次少于配置要求的 32 字符，被配置层拒绝。更换为仅进程内的合规占位值后迁移 SQL 成功生成，未连接数据库、未写入 `.env`。

## 2026-08-10 总体方向规划发现

- 已确认的新方向文档将产品拆为交付核验、项目态势与研发总结、安全与质量治理三条业务线，共用项目、来源、快照、证据与正式记录。
- 当前实现已经具备固定双核、交付核验 Git Diff、冻结编排、外围 Agent 的受控 Prompt/只读工具、报告草稿、人工审批链和真实运行详情。
- 目标架构要求后续新增运行配置类型、外部来源镜像、研发事项/交付项、关联关系、项目态势快照、安全基线和多类型正式记录。
- 当前实现与目标架构最关键的冲突是：Git Snapshot 被全部分析运行全局强制；后续必须只在交付核验配置中强制。

## 2026-08-10 当前实现审计

- `analysis_service.start_analysis_run` 要求正式快照且必须存在 `InputSnapshotGit`；`snapshot_service` 冻结正式快照时也强制写入 Git 绑定。因此项目总结、安全基线目前无法作为独立运行启动。
- `verification_graph`、报告服务和现有 `VerificationTask -> VerificationCycle -> InputSnapshot -> AnalysisRun -> ReportVersion -> PublishedRecord` 语义均围绕单次正式交付核验构建，应保留该链但不能直接承担项目态势或安全基线。
- 编排服务固定 `requirement-claim-core`、`delivery-git-diff`、`evidence-reconciliation` 三个必经节点；默认模板名称和任务绑定也明确为“默认交付核验”。这是正确基础，但必须增加按运行配置验证模板的能力，不能继续对所有模板使用同一必经集合。
- 数据模型已有来源版本、Git 快照、外部 CI/构建证据、手工证据、风险、Coverage、报告与发布记录；尚无外部连接/同步、外部事项镜像、交付项、关联关系、项目态势快照和安全基线专用对象。
- 前端有任务、交付历史、审批、知识库、Agent 功能块和 Notebook 页面；任务中心、工作台、审批和交付历史仍主要依赖 fixtures，知识库和 Agent 功能块要求用户粘贴项目 UUID，尚未形成真实项目到事项到运行的导航链。
- API 现状只有项目创建/读取、资料、Git 仓库与快照、核验任务、分析、报告、审批和编排端点；不存在项目列表、外部连接、同步、事项、关联、态势或安全基线端点。
- Worker 固定调用 `run_verification_graph`，运行完成后依照现有核验结果更新轮次状态并生成报告草稿；未来的项目态势和安全基线必须有独立 workflow/worker dispatch，而不是塞进该图。
- 当前数据库迁移最新为 `015_dual_core_agent_orchestration.py`。后续扩展应使用追加迁移、保留既有交付核验历史，不能重写或复用历史快照与报告语义。

## 2026-08-10 运行范围切片实现审计

- `InputSnapshot` 目前只有 `purpose`，`AnalysisRun`、`OrchestrationTemplate`、`ReportVersion` 与 `PublishedRecord` 都没有运行配置/记录类型字段。
- `freeze_formal_snapshot` 将 Git SHA/Diff 纳入正式快照哈希，并总是创建 `InputSnapshotGit`；该逻辑应明确为交付核验专用函数和 Profile 校验。
- `start_analysis_run` 固定工作流为 `dual-core-v1`，固定调用编排指纹，也只允许含 Git 的正式快照；应将其改为 Profile 分发入口，但本切片只允许执行 `DELIVERY_VERIFICATION`。
- 现有历史数据可安全兼容：新增列的数据库默认值和非空约束均使用 `DELIVERY_VERIFICATION`，不会改变现有输入快照、报告内容哈希或记录哈希。
- Profile 字段将落在 `InputSnapshot`、`AnalysisRun`、`OrchestrationTemplate`、`AnalysisRunOrchestrationSnapshot`、`ReportVersion` 和 `PublishedRecord`；现有列与哈希不重算，新增字段由迁移默认值兼容。
- 对外响应需要显示快照和运行的 Profile；新建编排模板的请求可以声明 Profile，但本切片只允许创建和绑定 `DELIVERY_VERIFICATION` 模板，防止未实现外围 workflow 被提前启用。
- Worker 应保留单独的 Profile dispatcher：当前仅路由 `DELIVERY_VERIFICATION` 到既有 `run_verification_graph`，其他值一律报明确的“未开放”领域错误。

## 2026-08-10 运行范围切片已实施内容

- 已新增 `AssessmentProfile` 及 016 追加迁移：历史数据通过默认 `DELIVERY_VERIFICATION` 保持原有语义。
- 已将 Profile 写入快照、运行、模板、运行编排快照、报告和正式记录；新的交付快照哈希显式包含该 Profile。
- 已将 Git 范围约束改为交付核验专用校验，并加入未开放 Profile 的显式拒绝逻辑；Worker 使用 Profile dispatcher 且当前只路由到既有双核图。

## 2026-08-10 外部来源切片审计

- 当前仓库远端为 GitHub，因此首个实际 Git 平台适配器确定为 GitHub；适配器仍只读，不执行 Webhook、写操作或仓库代码。
- 现有 `GitRepository` 只服务本地只读 Git Diff，不能承载 Issue、PR 或 Milestone 的远程元数据；需要独立的来源连接和资源版本模型。
- 已有 `SourceRevision` 是项目文档的版本化证据来源。新交付项模型将为后续文档关联预留关系，不复制文档内容或用本系统手工文本覆盖外部事实。
- `agent_tool_runner` 的 HTTP 能力不适合承担正式来源同步：其结果是运行期临时工具证据，且 URL 由 Agent 模板配置。GitHub 同步必须走独立的服务端连接适配器、凭据引用和同步审计。

## 2026-08-10 事项关联切片审计

- `VerificationTask` 目前没有交付项外键，因此一次核验尚不能正式归属到同步事项；需要新增可空外键，以保留历史任务未归属状态。
- `GitSnapshot` 已通过 `VerificationCycle -> VerificationTask` 链接到项目；确认 Git Diff 与事项关系时必须要求该任务已绑定同一事项，避免跨事项误归属。
- GitHub 同步已将 PR 保存为 `ExternalResource(PULL_REQUEST)`，但尚未读取 Issue timeline 中的平台关联；可在本切片通过受控 GitHub timeline 请求生成平台来源的正式 PR 关系。

## 2026-08-10 事项关联切片已实施内容

- `VerificationTask.delivery_item_id` 允许新任务在创建时归属研发事项；已存在且已固化正式记录的任务保持历史未关联，不能被事后改写。
- `DeliveryChangeLink` 区分 `PLATFORM`、`USER` 与预留的 `AGENT` 来源，并区分 `CONFIRMED` 与 `CANDIDATE` 状态；数据库确保一次关联只指向一个 PR 或一个 Git Snapshot，且同一事项的同一目标不重复。
- 平台发现只把 GitHub Issue 时间线的 PR 交叉引用确认成“平台已记录的关联”。它不确认需求已实现、不更新事项核验状态；事项完成仍必须经由同一事项下的冻结 Diff、双核核验和正式记录。
- 文档资料继续复用既有 `SourceRevision`，通过 `ACCEPTANCE`、`DESIGN` 或 `PLAN` 角色链接到事项，不复制资料内容。

## 2026-08-10 项目态势切片实现原则

- 项目态势以 `ProjectHealthSnapshot` 保存结构化输入清单、输入哈希、汇总、数据缺口和观察边界；它是独立的项目管理事实快照，不伪装成一次 Git Diff 交付核验。
- 完成口径必须拆开：外部声明完成、核验状态已确认、拥有正式交付记录、已关联变更分别统计。没有有效计划分母时不展示完成率；即使有分母，也只展示核验覆盖，不将其称为项目完成率。
- 日报、周报和迭代总结首先从态势快照生成确定性草稿。固化时标记为 `PERSONAL_CONFIRMED`，作为个人可追溯记录，不冒充独立审核或团队批准。
- 此前 `DeliveryItem.verification_status` 没有在交付记录发布时更新。发布已批准的交付核验报告后，应由报告内冻结结果计算该事项的当前核验状态，再由态势快照读取该状态。

## 2026-08-10 安全基线切片实现原则

- 安全基线只能由绑定项目仓库和完整 SHA 的扫描/CI 输入组成；每个输入保存扫描器、扫描器版本、规则版本、覆盖说明、原始输出哈希和结构化风险，不能由模型凭空生成。
- 风险通过 `SecurityFinding -> SecurityScanArtifact -> repository/SHA` 追溯；风险状态只允许 `OPEN`、`ACCEPTED_RISK` 与 `REMEDIATION_CLAIMED`。最后一种只是整改声明，必须由新扫描结果验证，不能被写成已解决。
- 基线快照冻结所选扫描输入、风险、覆盖与缺失扫描类型；固化记录要求审核者或管理员确认，并始终包含“仅针对指定范围”的限制说明。

## 2026-08-10 开发方案结论

- 实施必须先完成运行配置与快照规则收敛，再建立外部来源和交付项；项目态势、安全基线、真实工作台均不能跳过这两个前置层。
- 建议拆为七个独立提交切片：运行范围、来源同步、事项关联、项目态势、安全质量、工作台导航、工具证据收口。
- 首个实际外部 Git 平台适配器的提供方仍需以项目实际使用的平台为准；这不影响先行的数据模型与适配器接口设计。

## 2026-08-10 真实工作台切片发现与处理

- 前端项目概览、任务中心、审批、交付历史和 Notebook 原先都依赖相同的演示 fixtures；知识库和 Agent 功能块还要求手工输入项目 UUID。这会掩盖“当前项目”边界，也会让演示事实混入真实核验路径。
- 后端已有事项、态势和安全基线的项目级查询，但缺少当前用户的项目列表、核验任务列表、项目级报告列表和正式记录列表。因此先补只读投影，再让前端基于统一项目上下文加载。
- 报告的待审批状态实际是 `SUBMITTED`，而 `PENDING_REVIEW` 是核验轮次状态。工作台查询必须按报告状态 `SUBMITTED` 过滤，不能混用两套状态机。
- 自定义能力块原先可选择 `REQUIREMENT` 或 `DELIVERY` 归属，语义上可能使外围 Agent 被误认为可替换固定双核。已改为 API 和服务端同时只允许 `SHARED`；历史数据不迁移或重写。
- Notebook 真实读取路径已经存在，但无运行时会退回到固定演示内容。已删除回退，改为显示当前任务轮次和缺少正式输入/运行的真实空状态。
- 质量趋势仍未实现；安全页面当前仅展示已导入扫描、基线和记录，不能解释为运行安全扫描或项目完整安全审计。

## 2026-08-12 可信边界补强设计

- 用户确认按“可信边界优先”的顺序实施：已发布周期锁定、来源与 Git 归属、GitHub 只读接入、索引重建、回归与观测。
- 已发布周期的历史草稿不是删除对象，而是状态转换必须被周期的 `PUBLISHED` 终态拒绝；读取和回放保持兼容。
- 交付项—变更关联本轮采用严格同仓库规则，避免用无审计的跨仓库例外掩盖错误归因。
- 私有 GitHub 首期采用 Fine-grained PAT 的环境变量引用，凭据值不得进入数据库、日志、URL、API 响应或 Git 配置；GitHub App 延后。
- Embedding 迁移使用派生索引版本和活动索引选择，不重写冻结事实；不同模型的向量不得混合比较。

## 2026-08-12 GitHub 只读来源补强验收

- 024 迁移已在本地开发数据库应用：`source_sync_runs` 新增 `page_count` 和 `continuation_cursor`，数据库版本为 `024_source_sync_pagination_cursor`；API 与 Worker 重建后均通过就绪检查。
- GitHub 的真实 `Link` 下一页会把命名仓库 URL 规范为 `/repositories/<numeric-id>/issues`。客户端只接受 `api.github.com` 上同一端点的命名路径或这一官方等价路径，拒绝跨主机、跨仓库和缺少分页参数的链接。
- 对公开大型仓库 `octocat/Spoon-Knife` 的真实同步在未配置 Token 的条件下连续读取 6 个 cursor 页后触发 GitHub 公共限流，终态为 `SOURCE_RATE_LIMITED`，并持久化 `page_count=6` 与 `after` cursor。它证明了 Cursor 续页和可追溯失败恢复信息，不证明无 Token 的全量同步成功。
- 私有仓库已由环境变量引用通道支持：凭据值不会写入数据库、审计载荷、URL、命令行、日志或 API 响应；单测验证 Git 子进程只使用进程内 HTTP Header 配置并关闭交互/Hook/重定向。没有真实私有 PAT，因此私有仓库访问仍是未覆盖项。

## 2026-08-12 派生检索索引重建验收

- 已通过 025 迁移建立项目级单活动索引契约。派生索引记录模型/维度/解析器版本，激活新索引前会先将旧索引转为历史；资料、冻结快照、证据、报告和发布记录没有被迁移重写。
- 检索实现已从“当前全局模型直接过滤分块”改为“只对项目活动索引做向量比较”。派生分块通过资料版本和分块序号回映冻结证据，使重建后的向量可以服务旧快照而不改变其证据 ID；词法检索仍可从历史分块提供受限回退。
- 实际重建测试发现两类真实运行边界：早期本机脚本写入的 Windows 宿主机工件 URI 在容器中不可读，正确返回 `SOURCE_ARTIFACT_UNAVAILABLE`；重新走 API 上传的隔离资料在当前 API 容器到百炼时返回 `MODEL_UNAVAILABLE`。两种情况均未激活索引或写入半成品，真实百炼重建仍未覆盖。

## 2026-08-12 运行观测收口验收

- 索引重建失败原本只能由 HTTP 错误观察，无法与后续外部条件问题区分。现已添加独立重建运行记录：主体重建放入保存点，失败回滚派生数据，外层提交失败状态、错误码和受限摘要；因此不会为保留日志而泄漏半成品索引或将失败误写为成功。
- 026 迁移和 API 已实际部署。零资料隔离项目的重建请求返回 `SOURCE_NOT_READY`，随后查询运行历史得到同一 `FAILED / SOURCE_NOT_READY` 记录和当前目标索引版本；失败的持久化输出与 API 错误一致。
- 当前可验证范围已覆盖发布终态、同源 Git 归属、GitHub Cursor/限流、私有凭据通道、派生索引切换和失败观测。真实私有 PAT 访问与可从当前 API/Worker 成功调用百炼的跨模型重建仍依赖外部网络/凭据条件，保留为未覆盖而非未实现。

## 仓库现状

- 仓库已初始化，当前分支为 `main`，暂无提交。
- `origin` 指向 `https://github.com/yyy2045/one.git`。
- 当前没有现有代码、架构文档或仓库级 `AGENTS.md` 需要兼容。

## 架构审查结论

- 当前产品方向成立，关键卖点是多源证据核验、受控 AI 编排和人工审批闭环。
- 下一次完整架构设计必须优先固定不可变输入快照、证据引用、三类独立状态机、持久异步执行、权限审批和失败恢复。
- 不能通过增加框架代替领域边界设计；首版保持模块化单体。
- 完整架构设计应明确哪些内容已固定、哪些仍需决策，以及每项决策的验收标准。

## 最终文档结构

- 采用“模块化单体 + 独立 Worker + PostgreSQL Job”。
- 固定核心数据主链、不可变快照、四套状态机、证据协议、LangGraph 边界、权限审批和失败恢复。
- 下一次对话必须产出一份完整架构文档和一份一个月实现计划，并通过端到端一致性走查与验收清单。
- 使用默认值关闭非关键歧义；只有真实仓库冲突、覆盖风险或权限阻塞才停下询问。
# 2026-08-24 双人协作开发功能清单审查发现

- 审查开始时工作树存在多处未提交后端、前端、Docker、迁移和测试变更；这些变更属于当前项目事实，但其可用性需要与 HEAD 能力分开标注。
- 既有架构目标为 FastAPI 模块化单体 + PostgreSQL/pgvector + 独立 Worker + Vue/Vite；可信边界为固定双核、只读 Git Diff、不可变快照、人工审批和可回放正式记录。
- 当前 HEAD 为 `4b13ded 文档：明确多格式知识库设计`；工作树在此基础上有 31 个文件变动，主要是多格式知识库、项目 Git 仓库列表、Notebook P0、审批固化和前端布局，另有新迁移 027、新 ingestion worker 与 Git 仓库列表测试。
- 后端有 28 个路由模块、26 个迁移（001-026 已提交，027 未提交）、6 个已提交测试文件加 1 个未提交测试；前端有 11 个页面、3 个 Notebook 子面板，无独立组件测试框架或 test script。
- 前端技术栈为 Vue 3 + TypeScript + Vue Router + Pinia + Vite；后端为 Python 3.12 + FastAPI + SQLAlchemy/Alembic + PostgreSQL/pgvector + LangGraph，并在工作树新增 pypdf/python-docx/python-pptx/openpyxl/Pillow/pytesseract/BeautifulSoup/PyYAML 等多格式解析依赖。
- 文档体系包含架构总览、双核/Agent、可信边界、工作台 UI 和多格式知识库设计；但架构文档中的全勾选验收是设计闭合，不等于当前代码/运行验收，必须以源码、测试和实时状态另行判定。
- 当前领域表已覆盖项目/成员、外部来源同步、交付项、任务/轮次、资料/摄取任务/分块/检索索引、Git 仓库/快照、Claim/证据/裁决、运行/Job/事件/模型调用、报告/审批/发布、外围 Profile、安全基线、Agent 编排等；尚未看到新设计所需 `DeliveryItemRevision`、`ClaimSet`、`ArtifactObject`、正式 Manifest V2 独立对象。
- 前端多数业务页面已通过统一 `apiRequest('/api/v1...')` 接真实接口；项目上下文在顶栏切换，写请求使用项目头和幂等头。是否闭环仍需逐页面核对按钮后的状态与后端权限。
- P0 核心语义仍未按最新可信方案落地：Workflow 从知识块逐块生成 `ACCEPTANCE_CANDIDATE` Claim，没有冻结 GitHub Issue Revision，也没有模型草稿→人工确认→ClaimSet 的门禁；正式快照不含 Issue/ClaimSet。
- 当前裁决仍使用旧五态：`CONFIRMED` 需要确定性支持 + SHA 绑定成功 TEST/BUILD + authority>=3；仅 Git Diff 命中只会得到 `PARTIALLY_SUPPORTED`。这与最新 P0 “Issue 验收项在冻结 Diff 中是否有可定位支持”的 `DIFF_SUPPORTED` 等五态设计不一致。
- 正式快照只持久化 source/git/external/manual 关联、哈希与 EvidenceItem 摘要；Git Diff 正文仍在运行时从远端仓库重读，资料原件/提取文本仍依赖共享 artifact 卷。尚无自包含 ArtifactObject/Manifest V2，因此远端或 artifact 丢失后不能保证离线回放。
- 正式记录 `PublishedRecord` 只存 task/cycle/report 外键、记录号/哈希/固化人；详情投影只展示哈希和审批元数据，没有报告条目、引用、快照清单、Diff/资料定位与完整审批事件，尚不满足“完整回放”。
- 报告状态机后端已实现草稿编辑、提交、非自审批准/退回/驳回、管理员固化以及已发布轮次不可回退；前端未读取当前用户/项目角色，所有人都能看到审批和管理员固化按钮，依赖后端 403 才拒绝。
- 身份入口只有登录，没有 `/auth/me` 或成员列表接口；前端左下角固定显示“张伟/交付核验负责人”。项目创建者自动为 ADMIN，成员添加仅有后端接口、无成员管理页面；新建项目无法仅靠 UI 把演示审核者加入项目，因此双人审批闭环无法从空项目纯前端完成。
- 知识库工作树已实现异步多格式导入：文本/结构化文本、PDF、doc/docx、xls/xlsx、ppt/pptx、odt/ods/odp、图片 OCR，原件与提取文本分开存储，Worker 有租约/心跳/重试，Embedding 不可用时保留 READY+词法分块。该实现尚未提交、迁移 027 尚未验证应用，且没有任何解析器/上传/API/Worker/OCR/真实测试目录自动化用例。
- 知识库前端支持批量顺序上传、3 秒轮询、分类/版本/状态/快照引用和提取文本查看；后端虽有原件下载和分块接口，但前端没有下载原件、查看定位分块、失败详情/手动重试、取消/删除/重新处理、批量进度与重复文件策略。
- 多格式解析可靠性缺口：CSV 仅按 UTF-8 普通文本处理；XML 只保留原始文本且未做安全结构化解析；HTML 未显式移除 script/style；XLS/PPT/DOC/ODF 依赖 LibreOffice 转 PDF 后可能丢失表格结构；XLSX 公式只取缓存值；PPTX 不含备注/图表/表格完整语义；OCR 置信度按 token 均值，没有页面无文字时的独立低置信判定；压缩炸弹/超大行列/图片像素上限与并发资源隔离尚无门禁。
- GitHub 公开来源、Cursor/Link 分页、限流错误、私有 PAT 引用和同仓库匹配已实现；设置页可创建连接、同步、登记/列出 Git 仓库。连接与仓库仍是两次手工录入，没有“一次连接自动登记同源 Git 仓库”、编辑/禁用/删除/连通性测试、续传同步操作与限流恢复倒计时。
- Notebook 工作树已接入 READY 资料、项目仓库列表、Git Diff 冻结、正式快照、真实运行轮询、事件/结果、草稿保存/提交；但页面只在 `!liveRun` 时显示准备区，失败或终态后无法在原页面创建新轮次/重新冻结，`canStartRun` 计算值未实际用于按钮，取消运行按钮缺失，Diff tab 仅显示说明而不是实际只读高亮 Diff。
- 当前 API 错误解析只提取 message，丢弃稳定 error code；多数页面共用一个 message 字符串，缺少字段级错误、可恢复动作和全局 401 失效处理。
- 自动化测试目前仅覆盖凭据引用、GitHub 分页、已发布轮次锁、仓库标识、检索索引策略和新增 Git 仓库列表/缺 Git 快照门禁；架构文档宣称的 RBAC、快照、引用、幂等、Worker 恢复、浏览器 E2E 等广泛覆盖并不存在。前端没有测试脚本或组件/E2E 测试依赖。
- 项目态势、安全与质量、外围 Profile、Agent 编排存在后端与真实页面，但多为“读取/固化已导入事实”，不执行扫描器、CI、构建或完整非交付 Worker；它们不属于当前可信 P0，宜保持二阶段能力而非与 P0 同时扩张。
- 本轮 `docker compose ps` 无法连接 Docker Engine，当前运行态不能确认；只能确认源码与工作树，不能把 2026-08-12 文档中的历史运行验收当作当前可用证明。
- `git diff --check` 本轮未输出空白错误，仅出现 Windows 工作树 LF→CRLF 提示；未运行后端/前端测试或构建。
- 标准化承接文档已落在 `docs/handoff/2026-08-24-two-person-development-context.md`，不预设功能负责人，以功能切片组织协作，并要求共同确认迁移、状态枚举、Manifest 和正式记录公开契约。

# 2026-08-25 GitHub 开源代码审查项目采纳调研

- 候选包括 The-PR-Agent/pr-agent、Gerrit Code Review、Reviewpad 和早期开源 CodeRabbit reviewer。Gerrit 是成熟人工评审平台但不聚焦 LLM Diff 分析；Reviewpad 原仓库入口不可用；早期 CodeRabbit 开源实现体量和维护状态不适合作为当前主参考。
- 选定 `The-PR-Agent/pr-agent`（原 `qodo-ai/pr-agent`）作为主参考：MIT 许可、完整 Python 源码、测试、GitHub Action/Docker/CLI 多种部署、GitHub/GitLab/Bitbucket/Azure DevOps/Gitea provider 抽象，具备 `/review`、`/describe`、`/improve`、`/ask`、大 PR 压缩、动态上下文和多模型支持。
- 该仓库当前明确声明为社区维护的开源 PR Reviewer，与 Qodo 商业产品不同；截至官方仓库当前页面有约 5,148 次提交、12.7k stars，2026-07 仍发布新版本。适合作为“Diff 获取、Token 预算、Prompt 结构、结构化输出、评论定位”的代码参考，不作为审批/正式记录架构参考。
- 已浅克隆官方仓库到系统临时目录，审查基线为 `f76c74cb8edd5ab8a46031aced2f30c5060756c1`（2026-08-25）。只读检查，不运行其依赖或外部调用。
- 核心结构清晰分层：`git_providers/*` 统一不同代码托管平台；`algo/pr_processing.py` 负责 Diff 组织、Token 预算和大 PR 分片；`tools/pr_reviewer.py` 负责 review 用例；`settings/*_prompts.toml` 保存结构化 Prompt；`ai_handlers/*` 隔离模型；provider 负责评论/行号投影。
- 其当前实现含增量审查、持久化行内评论、评论指纹去重、无 patch 时重建大 Diff、无在线 PR 的 plain-diff/local provider、关联 ticket 内容抽取、repo context/AGENTS.md、动态上下文和 CI artifact 注入。这些机制与当前项目的 Diff Artifact、Issue 上下文和证据定位缺口高度相关。
- Review 主链为：provider 获取 PR/文件/merge-base → 过滤文件并构造 `FilePatchInfo(base, head, patch, editType)` → 扩展 Hunk 上下文并加新文件行号 → 根据模型上下文预算压缩/分组 → 将 PR 标题、描述、commit、ticket、repo context、Diff 注入结构化 Prompt → 解析 YAML → 验证文件/行号 → 发布摘要或行内评论。
- 大 Diff 不会悄悄声称全覆盖：算法保留 `remaining_files_list`，Review 输出明确列出因 Token 预算未处理的文件；对单文件超限提供 skip/clip 策略，多分片路径用于部分工具。当前项目应借鉴 Coverage 契约，但不能照搬“按大文件优先”的排序作为证据权威顺序。
- Prompt 明确限制“只审查 PR 新增代码、只报告本 PR 引入的问题、看不到全仓库时不要猜”；输出字段包含文件、start/end 行、具体触发场景和可操作问题。发布前再次验证文件存在、行号不越界，无法定位则留在摘要，不伪造行内定位。
- Ticket 支持从 PR 描述和分支名提取 GitHub Issue，限制候选数和每项正文长度，读取标题/正文/标签/子任务并进入 `ticket_compliance_check`。其结果仍由模型直接生成，不具备本项目要求的 Issue Revision、ClaimDraft 人工确认和不可变 ClaimSet，因此只借鉴“上下文获取/裁剪/字段结构”，不能照搬其信任语义。
- 评论采用正文指纹、代码建议指纹和位置指纹去重；先扫描已有评论中的隐藏 marker，失败时降级为单次运行内去重。该机制适合借鉴到“同一 Snapshot/Run 的 Finding 去重”，但本项目正式记录仍必须依赖数据库唯一键与哈希，不能把 HTML marker 当正式状态。
- 模型重试支持 fallback models；这与当前 P0“DeepSeek 唯一真实模型、失败不切 Fake/其他模型”的约束冲突，不采纳 provider fallback，只可借鉴稳定错误分类、次数和耗时记录。
- 仓库具有约 134 个 Python 测试文件，包含 Diff 预算、Coverage footer、Plain Diff、行内评论去重、Repo 设置安全等定向回归；测试切片设计值得借鉴。
- 最终采纳方向：不引入或复制 PR-Agent 包；以其算法作为参考，在当前边界内实现 `FrozenDiffArtifact → CanonicalDiffFile/Hunk → TokenBudgetPlan/Coverage → EvidenceItem → DeepSeek LinkProposal → deterministic reconciliation`。
- 第一优先级是冻结完整 Diff artifact 并让 Worker 从 artifact 读取；第二优先级是建立 file/hunk 规范结构和 Token/Coverage 清单；第三优先级是 Issue Revision→ClaimDraft→人工 ClaimSet；随后再补可信 base-SHA 仓库上下文、Finding 指纹和增量对比。
- 全文件内容只可作为 `CONTEXT_ONLY`，来源必须是冻结 base/target SHA 且受大小/文件类型限制；正式支持结论只能引用冻结 Diff Evidence。删除 Hunk 不得像 PR-Agent 压缩策略那样默认降为文件名，因为删除实现也可能直接违背验收目标。
- 明确不采纳：模型/Provider 自动 fallback、模型直接给“Ticket fully compliant”、回写 GitHub 评论/标签/Approve、自动应用代码建议、P0 多托管平台扩张、基于已有评论 marker 作为正式状态、任何 checkout/构建/测试/项目代码执行。
- 用户确认采用“方案 1：增量升级现有交付核心”，允许新增数据库迁移和持久化对象，并要求在同一切片补 Notebook 的 Finding、文件行号、触发场景和未分析范围展示。
- 性能决策：PR-Agent 的主要质量收益来自前后文件内容、规范化 Hunk、Token/Coverage 和结构化 Prompt，这些均可在现有 LangGraph/Worker 内实现；无需为较小的编排开销重写整个运行、报告和审批链路。

## 2026-08-25 交付代码审查核心 v2 规格决策

- 已按用户确认将设计写入 `docs/specs/2026-08-25-delivery-code-review-core-v2-design.md`。设计选择通用不可变 `ArtifactObject` 保存完整 Diff 与代码变更 Bundle，不把可回放输入继续依赖于远端 Git 或临时工作目录。
- 手工 base/target 维持 `DIRECT_SHA_RANGE`，避免升级时静默改变现有范围语义；保存 merge-base 供后续 PR 语义扩展使用。由已确认 PR 创建范围时才允许显式切换为 `MERGE_BASE_TO_HEAD`。
- `CodeReviewFinding` 与既有 `RiskFinding` 分离：一般代码风险不自动改变验收项结论；只有经过 Evidence/Claim 定位校验的关联候选才进入现有确定性协调流程。
- 原始冻结 Diff Hunk 是唯一正式代码证据；base/target 文件全文只作为 `CONTEXT_ONLY`，读取失败或预算不足必须落入可见 Coverage，而不是伪装成全量审查。

## 2026-08-25 标准交付核验规划发现

- 当前 v2 已提供冻结 Hunk、`CodeReviewFinding`、DeepSeek-only `review_code`、`AnalysisCoverage.details` 和 Notebook 的真实 Diff/Finding 投影，可增量实现固定标准核验，不需要引入独立 Agent 编排框架。
- 反证必须作为原 Finding 的不可变补充记录，而非覆盖 Finding 或影响 `VerificationResult`；否则会突破“模型草稿、确定性裁决”的既有边界。
- Coverage 需要汇总审查输入、复核结果与未覆盖原因，但它是运行事实说明，不能转译为完成率或无风险结论。
- 当前 Docker Desktop Linux Engine 不可用是唯一已知外部 E2E 阻断；不得为完成验收擅自重启 Docker、服务或调用真实模型。
- 已实现固定反证节点：复核记录以 `(analysis_run_id, finding_id)` 唯一约束保存，模型输出必须携带原 Finding 的 Hunk Evidence ID；模型遗漏、虚构定位、预算截断和模型失败都通过 Coverage 透明暴露。

## 2026-08-25 v2 实施前代码核对

- 当前 `ReadOnlyGitReader.freeze_range` 已使用 `--no-checkout` 克隆、受控 fetch、`rev-parse`、`merge-base` 和 `git diff --binary`，但只把 hash/coverage 写进 `GitSnapshot`；`read_frozen_diff` 在运行时重新读取远端 Git，正是本切片要移除的可回放缺口。
- 当前 Git 输出用文本 `.strip()` 和行分割解析 `--name-status`/`--numstat`，会丢失末尾换行且对带特殊字符路径不够稳健；v2 必须添加原始 bytes 与 NUL 分隔解析，不能改变只读命令边界。
- `verification_graph` 目前自行 `_parse_hunks` 并只从新增行创建 Git Evidence；这不足以表示删除、重命名和二进制范围，v2 应以独立规范化 parser 替换这一局部解析。
- 当前 `AnalysisCoverage` 只有 scope/ref/state/reason，`RiskFinding` 强制 claim/evidence 且字段不足，`GitSnapshot` 无 Artifact 引用；因此需要 028 追加迁移和独立 `CodeReviewFinding`。
- Notebook 当前已能冻结 Diff 和轮询真实运行，但未读取实际 Diff/Finding/Coverage 接口；其 `TWO_DOT/THREE_DOT` 枚举须在 v2 保持兼容并映射为规格中的范围模式语义。

## 2026-08-25 v2 实施结果与验证边界

- 028 已新增 `ArtifactObject`、`CodeReviewFinding`、GitSnapshot 的 Diff/Bundle 制品引用和 `AnalysisCoverage.details`。新正式快照与新分析运行均拒绝没有可回放 Git 制品的范围；历史快照保持可读，但会得到明确的 `GIT_ARTIFACT_MISSING`。
- `ReadOnlyGitReader.freeze_range` 在冻结期写入原始 Diff bytes、规范化 Hunk 和受限 base/target 上下文。Worker 只读取受哈希校验的本地制品，远端 Git 不再参与分析期证据读取。
- 新增 `GET /git-snapshots/{id}/diff`、`GET /analysis-runs/{id}/code-review`。Notebook 已调用这些投影，展示变更文件、二进制跳过、模型 Finding、触发场景、建议与 Coverage 状态。
- 静态与定向测试可证明 Parser/上下文以及前端类型构建，但不能替代完整 API 运行：当前 `.venv` 缺 `pytest`，且 API 导入被已有知识库模块引用的 `bs4` 缺失阻断。未安装依赖、未启动容器、未调用真实 DeepSeek。
- 后续已按当前 `pyproject.toml` 安装声明依赖并安装 pytest：API 导入和新增路由声明通过，交付代码审查 6 项测试与后端全量 22 项 pytest 均通过。Docker Desktop Linux Engine 仍不可用，因此真实数据库、Worker 与 DeepSeek E2E 仍未覆盖。

## 2026-08-26 交付主张确认改造发现

- 当前 `Claim` 由 `analysis_run_id` 唯一约束，只能在运行图内创建；当前图的 `create_claims` 主要从正式快照资料生成 `DOC-*` Claim，资料为空时 Notebook 只能展示 PR 标题的前端占位，不构成可核验交付范围。
- 当前正式快照哈希只覆盖资料、Git、外部/人工证据，不覆盖交付主张；需要新增“确认主张快照清单”并把其内容哈希加入正式快照，防止运行前后悄悄改变审查对象。
- DeepSeek 已有严格 JSON 模式与 `MODEL_NOT_CONFIGURED` / `MODEL_UNAVAILABLE` 错误边界；候选主张提取应复用该边界，绝不能改用 `FakeGenerationModelAdapter`。
- `CodeReviewFinding` 是代码风险阅读结果，不能被“未发现 P0”转译为交付已完成；Notebook 的交付结论应只聚合逐条 `VerificationResult`。
