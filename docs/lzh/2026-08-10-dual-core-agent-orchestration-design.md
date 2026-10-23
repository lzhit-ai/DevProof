# 双核核验与可编排 Agent 功能块设计

## 已确认范围

平台的固定主干是两个核心 Agent：

1. **需求/验收核验核心**：从冻结的权威资料生成带来源和权威等级的 `Claim`。
2. **交付证据核验核心**：从冻结 Git 范围生成代码证据；`Git Diff` 是正式代码核验中不可删除、不可关闭的默认能力块。

围绕双核，用户可以创建 Agent 功能块，将自定义 Prompt、工具、参数和顺序组合进模板。默认模板为：

`资料 Claim → Git Diff → CI 证据（存在时）→ 风险扫描 → 证据裁决与 Coverage → 报告草稿 → 人工审批`

## 自定义 Agent 的受控边界

第一阶段允许自定义 Prompt 和工具组合，但不允许任意本地代码执行。自定义 Agent 必须声明：名称、说明、目标核心（需求/验收、交付证据或共享）、版本化 Prompt、输入/输出 JSON Schema、已授权工具列表和参数 schema。

工具初始类型为只读 `DOCUMENT_RETRIEVAL`、`GIT_DIFF`、`CI_EVIDENCE`、`EVIDENCE_QUERY` 与可配置的 `HTTP_QUERY`。HTTP 工具只能访问管理员登记的端点，凭据只以服务端环境变量引用保存，不能写入数据库、日志或 Prompt。后续如需写工具，必须加入人工审批令牌和独立授权策略，不能默认开放。

自定义 Agent 输出只能映射到 `EvidenceItem`、`ClaimEvidenceLink`、`RiskFinding` 或结构化建议。它不能直接创建 `VerificationResult=CONFIRMED`、提交/批准/发布报告，也不能修改 InputSnapshot、GitSnapshot 或已有证据。

## 持久化模型

| 对象 | 关键字段 | 作用 |
| --- | --- | --- |
| `agent_capabilities` | `key,name,core_scope,kind,is_system,is_locked,is_default_enabled` | 内置与用户创建能力块目录。 |
| `agent_capability_versions` | `capability_id,version_no,prompt_template,input_schema,output_schema,tool_bindings,parameter_schema,content_hash` | 不可变的 Prompt/工具/Schema 版本。 |
| `agent_tools` | `key,name,tool_type,endpoint_ref,input_schema,output_schema,is_active` | 可授权给 Agent 的工具目录。 |
| `orchestration_templates` | `project_id,name,is_default,version` | 项目级编排模板。 |
| `orchestration_template_nodes` | `template_id,capability_version_id,core_scope,display_order,enabled,parameters` | 模板中的能力块与顺序。 |
| `task_orchestration_bindings` | `task_id,template_id,template_version` | 任务选择的模板。 |
| `analysis_run_orchestration_snapshots` | `run_id,content_hash,template_snapshot,nodes_snapshot` | 分析开始时冻结实际编排。 |

系统会种子化双核、Git Diff、证据裁决和默认模板；主干节点的删除、禁用、跨核心移动由服务端拒绝。

## 工作流

LangGraph 保留固定阶段、转为动态能力列表：加载运行编排快照 → 需求/验收核心 → 交付证据核心（含锁定 Git Diff）→ 已启用的外围 Agent → 引用校验/证据裁决/Coverage → 报告草稿。

每个 Agent 通过统一处理器接口读取授权快照和上游结构化输出，返回状态增量。运行记录继续写 `node_attempts`、`run_events`，并保存能力块版本、参数、使用的工具和输出证据 ID。模型只可用所授权的工具和 Evidence ID；模型生成的关联始终要求二次校验和人工确认。

CI 证据只导入绑定冻结 `target_sha` 的既有测试/构建结果。系统不执行仓库代码、Build 或 Git Hook。

## API 与工作台

新增项目成员可管理的 Agent 功能块、工具目录、编排模板和任务绑定 API；已有运行与发布记录仅可读取其冻结快照。

工作台在“项目空间”下新增“Agent 功能块”页，含“功能块库 / 工具 / 编排模板”三个区域。任务创建或编辑时选择模板；Notebook 的运行详情新增“双核编排”区，展示核心、节点顺序、版本、工具、状态、证据输出和跳过原因。新增页面沿用当前工作台的浅色企业风格、左侧层级导航、分隔线信息布局和现有组件尺度；不新增浏览器原型、流程图或对比图功能。

## 验收

1. 新任务默认绑定含双核和锁定 Git Diff 的模板。
2. 服务端拒绝禁用或移除主干能力；普通 Agent 可创建、版本化、启停和排序。
3. 自定义 Prompt 和工具授权能被保存、校验、版本化，并随运行冻结。
4. 自定义 Agent 不可获得仓库执行权限或写入正式结论/审批/发布状态。
5. 修改模板/Prompt 后，旧运行仍可回放原配置；新运行读取新版本。
6. FakeModel 可跑通默认模板，DeepSeek 仅用于后续真实模型联调。
