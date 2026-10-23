"""Database-coordinated handoff; old mutations cannot bypass the active writer."""

from sqlalchemy import text

from app.domain.errors import DomainError


def report_owner(session) -> str:
    # Shared lock is held through the business transaction; activation takes an exclusive lock.
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='reports' FOR SHARE")).scalar_one()
    if owner not in {"PYTHON", "JAVA"}:
        raise DomainError("BUSINESS_OWNER_MISMATCH", "报告业务写入方配置无效")
    return owner


def require_python_reports(session) -> None:
    if report_owner(session) != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "报告与人工裁决已交接给 Java，请通过业务网关操作")


def require_python_inputs(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='verification-inputs' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "核验输入已交接给 Java，请通过业务网关冻结")


def verification_owner(session) -> str:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='verification' FOR SHARE")).scalar_one()
    if owner not in {"PYTHON", "JAVA"}:
        raise DomainError("BUSINESS_OWNER_MISMATCH", "核验业务写入方配置无效")
    return owner


def require_python_verification(session) -> None:
    if verification_owner(session) != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "正式核验已交接给 Java，请通过业务网关发起或取消运行")


def require_python_identity(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='identity' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "账号注册已交接给 Java，请通过业务网关注册")


def require_python_projects(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='projects' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "项目与成员管理已交接给 Java，请通过业务网关操作")


def require_python_task_management(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='task-management' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "核验任务管理已交接给 Java，请通过业务网关操作")


def github_source_owner(session) -> str:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='github-sources' FOR SHARE")).scalar_one()
    if owner not in {"PYTHON", "JAVA"}:
        raise DomainError("BUSINESS_OWNER_MISMATCH", "GitHub 来源写入方配置无效")
    return owner


def require_python_github_sources(session) -> None:
    if github_source_owner(session) != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "GitHub 来源与同步已交接给 Java，请通过业务网关操作")


def require_python_knowledge_bases(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='knowledge-bases' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "知识库及挂载管理已交接给 Java，请通过业务网关操作")


def knowledge_source_owner(session) -> str:
    return session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='knowledge-sources' FOR SHARE")).scalar_one()


def require_python_knowledge_sources(session) -> None:
    if knowledge_source_owner(session) != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "资料入库与索引管理已交接给 Java，请通过业务网关操作")


def require_python_orchestration(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='orchestration' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "能力、工具和编排管理已交接给 Java，请通过业务网关操作")


def require_python_evidence_materials(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='evidence-materials' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "人工/外部补证及工具结果导入已交接给 Java，请通过业务网关操作")


def require_python_git_inputs(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='git-inputs' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "仓库登记和交付 Git 快照已交接给 Java，请通过业务网关操作")


def require_python_delivery_associations(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='delivery-associations' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "交付关联和关联候选已交接给 Java，请通过业务网关操作")


def require_python_delivery_claims(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='delivery-claims' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "交付主张生成和确认已交接给 Java，请通过业务网关操作")


def require_python_evidence_questions(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='evidence-questions' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "证据问答已交接给 Java，请通过业务网关提交并跟踪任务")


def require_python_project_status(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='project-status' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "项目态势与总结已交接给 Java，请通过业务网关操作")


def require_python_security_baselines(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='security-baselines' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "安全工件、风险处置及基线已交接给 Java，请通过业务网关操作")


def require_python_peripheral_profiles(session) -> None:
    owner = session.execute(text("SELECT owner FROM business_write_owners WHERE aggregate_key='peripheral-profiles' FOR SHARE")).scalar_one()
    if owner != "PYTHON":
        raise DomainError("BUSINESS_OWNER_MISMATCH", "外围事实投影已交接给 Java，请通过业务网关操作")


def enqueue_report_draft(session, *, run_id) -> None:
    session.execute(text("""INSERT INTO report_generation_jobs(run_id,status) VALUES(:id,'PENDING')
        ON CONFLICT(run_id) DO NOTHING"""), {"id": run_id})


if __name__ == "__main__":
    import sys
    from app.core.db import SessionLocal

    if sys.argv[1:] != ["require-legacy"]:
        raise SystemExit("Usage: python -m app.infrastructure.business_ownership require-legacy")
    try:
        with SessionLocal.begin() as session:
            require_python_reports(session)
            require_python_inputs(session)
            require_python_verification(session)
            require_python_identity(session)
            require_python_projects(session)
            require_python_task_management(session)
            require_python_github_sources(session)
            require_python_knowledge_bases(session)
            require_python_knowledge_sources(session)
            require_python_orchestration(session)
            require_python_evidence_materials(session)
            require_python_git_inputs(session)
            require_python_delivery_associations(session)
            require_python_delivery_claims(session)
            require_python_evidence_questions(session)
            require_python_project_status(session)
            require_python_security_baselines(session)
            require_python_peripheral_profiles(session)
    except DomainError as error:
        raise SystemExit(error.message) from None
    print("Formal business aggregates are owned by the legacy topology.")
