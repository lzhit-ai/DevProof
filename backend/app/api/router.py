from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.analysis import run_router, snapshot_router as analysis_snapshot_router, task_router as analysis_task_router
from app.api.routes.agent_tool_executions import router as agent_tool_execution_router
from app.api.routes.evidence import router as evidence_router
from app.api.routes.external_evidence import router as external_evidence_router
from app.api.routes.external_sources import router as external_sources_router
from app.api.routes.delivery_associations import router as delivery_associations_router
from app.api.routes.project_status import router as project_status_router
from app.api.routes.peripheral_profiles import router as peripheral_profiles_router
from app.api.routes.security_baselines import router as security_baselines_router
from app.api.routes.git import repository_router, snapshot_read_router, snapshot_router
from app.api.routes.health import router as health_router
from app.api.routes.manual_evidence import router as manual_evidence_router
from app.api.routes.orchestration import project_router as orchestration_project_router, run_router as orchestration_run_router, task_router as orchestration_task_router
from app.api.routes.projects import router as projects_router
from app.api.routes.questions import router as questions_router
from app.api.routes.retrieval import router as retrieval_router
from app.api.routes.retrieval_indexes import router as retrieval_indexes_router
from app.api.routes.reports import cycle_router as report_cycle_router, project_router as project_report_router, report_router
from app.api.routes.snapshots import router as snapshots_router
from app.api.routes.sources import all_knowledge_bases_router, knowledge_bases_router, sources_router
from app.api.routes.tasks import router as tasks_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(analysis_snapshot_router, tags=["analysis"])
api_router.include_router(run_router, tags=["analysis"])
api_router.include_router(analysis_task_router, tags=["analysis"])
api_router.include_router(agent_tool_execution_router, tags=["agent-orchestration"])
api_router.include_router(evidence_router, tags=["evidence"])
api_router.include_router(external_evidence_router, tags=["evidence"])
api_router.include_router(external_sources_router, tags=["external-sources"])
api_router.include_router(delivery_associations_router, tags=["delivery-associations"])
api_router.include_router(project_status_router, tags=["project-status"])
api_router.include_router(peripheral_profiles_router, tags=["peripheral-profiles"])
api_router.include_router(security_baselines_router, tags=["security-baselines"])
api_router.include_router(manual_evidence_router, tags=["evidence"])
api_router.include_router(orchestration_project_router, tags=["agent-orchestration"])
api_router.include_router(orchestration_task_router, tags=["agent-orchestration"])
api_router.include_router(orchestration_run_router, tags=["agent-orchestration"])
api_router.include_router(repository_router, tags=["git"])
api_router.include_router(snapshot_router, tags=["git"])
api_router.include_router(snapshot_read_router, tags=["git"])
api_router.include_router(projects_router, tags=["projects"])
api_router.include_router(questions_router, tags=["questions"])
api_router.include_router(retrieval_router, tags=["retrieval"])
api_router.include_router(retrieval_indexes_router, tags=["retrieval"])
api_router.include_router(report_cycle_router, tags=["reports"])
api_router.include_router(report_router, tags=["reports"])
api_router.include_router(project_report_router, tags=["reports"])
api_router.include_router(tasks_router, tags=["verification-tasks"])
api_router.include_router(sources_router, tags=["sources"])
api_router.include_router(knowledge_bases_router, tags=["sources"])
api_router.include_router(all_knowledge_bases_router, tags=["sources"])
api_router.include_router(snapshots_router, tags=["snapshots"])
