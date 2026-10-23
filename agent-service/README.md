# DevProof Python Agent 服务

该进程只通过 Java 内部 API 领取任务、续租、读取授权材料、发送事件及提交候选，没有业务数据库连接。

依赖方向：Worker/适配器与场景 Agent → 通用 Runtime → 模型和工具协议。Runtime 不认识规划业务、审批或 ORM。注册能力通过共享预算的 `delegate_agent` 受控委派，父子会话隔离，取消沿模型/工具/子任务传播。

```powershell
uv sync --no-dev
.venv/Scripts/python.exe -m devproof_agent.worker
```

必需配置：`BUSINESS_API_URL`、唯一的 `WORKER_ID`、对应的 `AGENT_SERVICE_TOKEN`。生成模型来自任务发起用户在设置页保存的个人配置；Worker 通过当前任务的有效租约领取匹配版本的凭据，每个任务独立创建模型客户端。API Key 不进入任务分配、队列正文或事件；缺少个人配置、配置已变更或租约失效时明确停止，不回退使用共享 Key。
契约目录由 `CONTRACT_SCHEMA_ROOT` 指定，开发时默认使用仓库 contracts/schemas；容器已设置。一次执行失败后由 Java 决定重试，从冻结输入开始新尝试，不声称任意中间断点恢复。

当前 Worker 注册规划与仓库探索能力；交付核验仍在迁移，不会领取尚未支持的 DELIVERY_VERIFY 任务。
