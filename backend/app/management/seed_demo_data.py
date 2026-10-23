"""Seed a demo project with realistic documents for testing the doc-viewer feature.

Run inside the api container:
  docker compose -f infra/docker-compose.yml exec api python -m app.management.seed_demo_data
"""

from uuid import UUID, uuid4

from app.application.security import hash_password
from app.application.services.source_service import create_source_revision
from app.core.db import SessionLocal
from app.domain.enums import ProjectRole
from app.infrastructure.persistence.models import Project, ProjectMember, User

DEMO_PROJECT_ID = UUID("c0ffee01-0000-0000-0000-000000000001")
SUBMITTER_ID = UUID("b0000001-0000-0000-0000-000000000001")
REVIEWER_ID = UUID("b0000002-0000-0000-0000-000000000002")

DEMO_DOCS = [
    (
        "需求",
        "需求规格说明书 v1.2",
        """# 需求规格说明书 v1.2

## 1. 引言

本文档定义了 DevProof 平台的软件交付核验功能需求，适用于秋招 portfolio 演示场景。

## 2. 功能需求

### 2.1 多源证据采集

系统应支持以下三种证据来源：
- **Git 仓库**：通过 Two-Dot / Three-Dot diff 模式采集变更范围
- **文档资料**：支持 Markdown 与纯文本格式的需求、设计、测试文档
- **外部证据**：测试报告、构建结果等 CI/CD 产出物

### 2.2 语义核验流程

核验工作流应包含以下节点：
1. 加载输入快照（Snapshot）
2. 采集 Git 证据
3. 生成核验声明（Claims）
4. 确定性关联匹配
5. 模型建议关联
6. 结果协调输出

### 2.3 报告管理

- 支持草稿、已提交、已批准、已驳回、已发布五种状态
- 审批操作需记录审计日志
- 发布后的报告不可修改

## 3. 非功能需求

| 指标 | 目标值 |
|------|--------|
| 单次分析耗时 | < 120s |
| 证据检索召回率 | > 85% |
| API 响应时间（P95） | < 500ms |
""",
    ),
    (
        "设计",
        "总体设计说明书 v2.0",
        """# 总体设计说明书 v2.0

## 架构概述

DevProof 采用**模块化单体**架构，分为以下层次：

```
┌─────────────────────────────────────┐
│          FastAPI REST API           │
├─────────────────────────────────────┤
│       Application Services          │
├─────────────────────────────────────┤
│         Domain (Ports + DTO)        │
├─────────────────────────────────────┤
│   Infrastructure (DB, Git, Model)   │
└─────────────────────────────────────┘
```

## 核心组件

### API 层
- FastAPI 路由，按资源分组（projects, sources, tasks, reports）
- JWT 认证中间件
- 幂等性保障（Idempotency-Key）

### 应用服务层
- `source_service` — 资料上传与版本管理
- `analysis_service` — 分析任务调度
- `report_service` — 报告生命周期管理

### 领域层
- 端口接口（Port）：定义外部依赖抽象
- DTO：跨层数据传输对象
- 枚举状态机：四种独立状态机

### 基础设施层
- PostgreSQL + pgvector：混合检索（全文搜索 + 向量相似度）
- Git 只读读取器：子进程调用 git 命令
- OpenAI 兼容模型适配器：生成与嵌入
- 本地文件存储：SHA-256 内容寻址

## Worker 设计

Worker 通过 PostgreSQL Job Queue 实现任务调度：
- `FOR UPDATE SKIP LOCKED` 避免竞争
- 租约心跳防止任务丢失
- 有界重试（默认 3 次）
""",
    ),
    (
        "测试",
        "集成测试报告 2025Q2",
        """# 集成测试报告

**测试周期**：2025-04-01 ~ 2025-06-30
**测试环境**：Docker Compose 四服务拓扑
**执行人**：演示提交者

## 测试覆盖

| 模块 | 用例数 | 通过 | 失败 | 通过率 |
|------|--------|------|------|--------|
| 用户认证 | 12 | 12 | 0 | 100% |
| 资料管理 | 18 | 17 | 1 | 94.4% |
| Git 采集 | 8 | 8 | 0 | 100% |
| 分析工作流 | 15 | 14 | 1 | 93.3% |
| 报告管理 | 10 | 10 | 0 | 100% |
| **合计** | **63** | **61** | **2** | **96.8%** |

## 失败用例分析

### TC-SRC-014：大文件上传超限
- **现象**：上传 3 MiB 文件时返回 500 而非 422
- **根因**：nginx 反向代理 `client_max_body_size` 未同步调整
- **修复**：已在 PR #87 中修复，增加统一错误响应

### TC-ANL-009：并发分析任务偶发死锁
- **现象**：两个分析同时启动时偶发 DB 死锁
- **根因**：`InputSnapshotSource` 批量插入未按固定顺序排序
- **修复**：已添加 `ORDER BY source_revision_id`，回归 20 次无复现

## 性能基准

| 操作 | P50 | P95 | P99 |
|------|-----|-----|-----|
| 资料上传 | 180ms | 420ms | 780ms |
| 分析启动 | 320ms | 890ms | 1.5s |
| 报告渲染 | 95ms | 210ms | 380ms |
""",
    ),
    (
        "会议纪要",
        "技术评审会议纪要 2025-05-15",
        """# 技术评审会议纪要

**会议时间**：2025-05-15 14:00-15:30
**参会人员**：演示提交者、演示审核者
**主题**：DevProof v1 架构评审

## 议题一：模块化单体 vs 微服务

**结论**：当前阶段保持模块化单体架构。
- 优势：部署简单，调试方便，适合演示场景
- 风险：Worker 与 API 共享 DB 连接池，需监控连接数
- 后续演进：如团队规模扩大，可先将 Worker 拆为独立服务

## 议题二：证据链完整性

**结论**：当前 Claim → EvidenceItem → VerificationResult → Report 链路完整，但缺少证据版本追溯。
- 已做：Git SHA 冻结、文档内容哈希
- 待做：证据之间的引用关系图（DAG）
- 优先级：P1，预计 v1.1 实现

## 议题三：安全性

**结论**：合规项基本满足，需关注以下风险点：
1. JWT Secret 强度 — 当前 256-bit，符合要求
2. 密码哈希 — PBKDF2-HMAC-SHA256，迭代次数需评审
3. 路径遍历防护 — `LocalArtifactStorage` 已做校验
4. SSRF 风险 — Git URL 校验需加强（v1.1）

## 后续行动项

| 编号 | 内容 | 负责人 | 截止日期 |
|------|------|--------|----------|
| A-01 | 优化 DB 连接池配置 | 演示提交者 | 2025-05-30 |
| A-02 | 证据 DAG 原型设计 | 演示提交者 | 2025-06-15 |
| A-03 | Git URL SSRF 加固 | 演示审核者 | 2025-06-01 |
""",
    ),
    (
        "补证",
        "人工补证：前端重构验证记录",
        """# 人工补证记录

**补证类型**：前端重构验证
**关联需求**：FR-UI-003 工作台多页面导航
**提交人**：演示审核者
**提交日期**：2025-05-22

## 补证说明

前端由单文件 App.vue（342 行）重构为 Vue Router 多页面 SPA 后，需人工验证以下功能点：

## 验证清单

- [x] 工作台首页 — 项目列表、审批简报、近期交付正常渲染
- [x] 知识库 — 文档列表、类型筛选、上传按钮可用
- [x] 任务中心 — 核验任务列表、状态筛选、跳转笔记本正常
- [x] 笔记本 — 三栏布局（证据、核验、详情）完整展示
- [x] 审批队列 — 待审批报告列表、操作按钮可用
- [x] 交付历史 — 按月分组、状态标记正常
- [x] 项目设置 — 成员管理、危险操作确认弹窗正常
- [x] 全局导航 — 侧边栏折叠/展开、路由高亮正确
- [x] 全局顶栏 — 项目切换下拉框、搜索框可用

## 已知问题

1. 项目切换器目前为装饰性组件，未与后端联动
2. 知识库页面硬编码演示数据，需要后续接入真实 API

## 结论

本次重构验证通过。前端架构已达到 v1 演示标准，剩余待办项已记录为 P2。
""",
    ),
]


def _get_or_create_users(session):
    users = {}
    for email, display_name, password, user_id in [
        ("submitter@example.local", "演示提交者", "demo-submitter", SUBMITTER_ID),
        ("reviewer@example.local", "演示审核者", "demo-reviewer", REVIEWER_ID),
    ]:
        user = session.query(User).filter_by(email=email).one_or_none()
        if user is None:
            user = User(
                id=user_id,
                email=email,
                display_name=display_name,
                password_hash=hash_password(password),
            )
            session.add(user)
            session.flush()
        users[display_name] = user
    return users


def _get_or_create_project(session, owner):
    project = session.get(Project, DEMO_PROJECT_ID)
    if project is None:
        project = Project(
            id=DEMO_PROJECT_ID,
            name="DevProof 演示项目",
            description="秋招 portfolio 演示用项目，展示多源证据核验能力",
            owner_id=owner.id,
        )
        session.add(project)
        session.flush()
    return project


def _ensure_members(session, project_id, users):
    for user in users.values():
        existing = (
            session.query(ProjectMember)
            .filter_by(project_id=project_id, user_id=user.id)
            .one_or_none()
        )
        if existing is None:
            role = ProjectRole.ADMIN if "提交者" in user.display_name else ProjectRole.REVIEWER
            session.add(ProjectMember(project_id=project_id, user_id=user.id, role=role.value))


def _seed_sources(session, project_id, actor_id):
    for role, name, content in DEMO_DOCS:
        # Skip if already seeded
        from app.infrastructure.persistence.models import SourceRevision
        existing = (
            session.query(SourceRevision)
            .filter_by(project_id=project_id, logical_name=name)
            .one_or_none()
        )
        if existing is not None:
            continue
        create_source_revision(
            session,
            project_id=project_id,
            source_role=role,
            logical_name=name,
            original_filename=f"{name}.md",
            claimed_media_type="text/markdown",
            content=content.encode("utf-8"),
            actor_id=actor_id,
            correlation_id=f"seed-demo-{uuid4().hex[:8]}",
        )


def main() -> None:
    with SessionLocal() as session:
        users = _get_or_create_users(session)
        owner = list(users.values())[0]
        project = _get_or_create_project(session, owner)
        _ensure_members(session, project.id, users)
        session.flush()
        _seed_sources(session, project.id, owner.id)
        session.commit()

    print(f"演示数据已就绪。项目 UUID: {DEMO_PROJECT_ID}")
    print("项目名称: DevProof 演示项目")
    print(f"文档数量: {len(DEMO_DOCS)}")
    for role, name, _ in DEMO_DOCS:
        print(f"  [{role}] {name}")


if __name__ == "__main__":
    main()
