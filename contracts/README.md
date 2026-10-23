# DevProof Java / Python 内部契约

`schemas/` 保存 `agent-task-v1` JSON Schema；Python 定义来自
`backend/app/domain/agent_contracts.py`。修改协议时同步生成对应 Schema。
独立 Worker 已接入规划、核验、主张提取及证据问答任务。Flaskr 的真实仓库冻结、模型规划、注册式委派与 Java 草案接受已有实际执行记录；其他业务闭环仍待验收。

| Schema | 目标请求 |
| --- | --- |
| task-assignment-v1.json | Java 事务领取后发放任务与尝试 |
| task-heartbeat-v1.json | Worker 请求续租并读取取消标记 |
| task-result-v1.json | Worker 提交结构化候选 |
| task-failure-v1.json | Worker 报告失败、取消或预算耗尽 |
| task-event-v1.json | Worker 记录脱敏执行事件 |
| tool-call-v1.json | Worker 请求执行已授权的注册工具 |
| delivery-claim-input-v1.json | Java 冻结的 PR 元数据、所选资料摘录与来源清单 |
| delivery-claim-proposal-v1.json | 模型返回的有界候选主张，仍需人工确认 |
| evidence-question-input-v1.json | Java 冻结的问题、快照摘要及授权证据 |
| evidence-question-result-v1.json | 仅供参考的回答及事实支持状态 |

内部任务、事件和工具协议使用 camelCase。版本号、空列表和可空引用必须显式提供；时间带时区；SHA 为完整不可变提交标识；摘要使用 `sha256:<hex>`。
核验任务关联 AnalysisRun 和核验快照；规划任务关联 PlanningRun 和规划快照，不能借用核验周期外键。`DELIVERY_CLAIM_PROPOSE` 关联独立 `CLAIM_PROPOSAL_RUN`，输入种类为 `CLAIM_PROPOSAL`；不授予仓库访问、正式 Evidence ID 或计划版本引用。`EVIDENCE_QUESTION` 关联 `EVIDENCE_QUESTION_RUN`，输入种类为 `EVIDENCE_QUESTION`，只授予此次选定的证据，不授予仓库或计划引用。四类业务引用在数据库中必须且只能选择一种。

主张和问答执行器均在首个模型调用前读取并校验 Java 保存的原始输入字节、hash 和 Schema。问答结果保留五种事实支持状态，返回的 citations 表示全部供参考证据（`citation_scope=SUPPLIED_EVIDENCE`），不表示模型逐条建立了支持关系；结果不修改正式核验状态。

Schema 校验不代替业务鉴权。Java 必须检查当前 Worker、尝试、代次、租约、取消、资源归属、输入和 manifest；模型提供的引用不授予权限。
`candidatesJson` 是结构化候选对象的 JSON 文本；`resultHash` 是该文本原始 UTF-8 字节的 SHA-256。Java 先检查摘要，再解析对象并按 `resultSchemaVersion` 校验和执行正式规则，避免两种语言重新序列化数字/Unicode 导致摘要漂移。同一尝试同摘要重放返回原接受结果；不同摘要冲突；结果与任务终态同事务保存。
模型完成、事件和候选不能自动确认计划、审批或发布。

凭据只通过运行配置/凭据引用传入，不放入契约记录或日志。[Flaskr 实际规划记录](real-samples/flaskr-planning-2026-10-22.json) 保存公开仓库的完整提交、冻结摘要、实际需求、HTTP 读取投影、模型原始候选和三次执行历史；不包含账号联系方式或凭据，也不会在启动时导入业务库。第三次执行形成 DRAFT；前两次分别因预算耗尽和 Java 校验拒绝而失败。当前草案按用户决定保留待审阅，真实取消、核验、审批发布、缓存降级和历史兼容不在该记录的已验收范围内。

在仓库根目录生成 Schema：

```powershell
python contracts/export_schemas.py
python contracts/export_agent_registry.py
```
