"""Project-scoped repository listing regression coverage."""

import unittest
from unittest.mock import patch
from uuid import uuid4

from app.application.services.git_service import list_repositories
from app.application.services.analysis_service import start_analysis_run
from app.domain.errors import DomainError
from app.infrastructure.persistence.models import GitRepository, InputSnapshot, VerificationCycle, VerificationTask


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters.update(kwargs)
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return [row for row in self.rows if all(getattr(row, key) == value for key, value in self.filters.items())]

    def one_or_none(self):
        rows = self.all()
        return rows[0] if rows else None


class _Session:
    def __init__(self, rows):
        self.rows = rows

    def query(self, _model):
        return _Query(self.rows)


class _SnapshotGateSession:
    def __init__(self, objects):
        self.objects = objects

    def get(self, model, identifier):
        return self.objects.get((model, identifier))

    def query(self, _model):
        return _Query([])


class GitRepositoryListingTests(unittest.TestCase):
    def test_returns_only_repositories_owned_by_the_requested_project(self) -> None:
        first_project_id, second_project_id = uuid4(), uuid4()
        first = GitRepository(project_id=first_project_id, display_url="https://github.com/demo/first.git")
        second = GitRepository(project_id=second_project_id, display_url="https://github.com/demo/second.git")
        with patch("app.application.services.git_service.require_project_role") as authorization:
            result = list_repositories(_Session([first, second]), project_id=first_project_id, actor_id=uuid4())

        self.assertEqual(result, [first])
        authorization.assert_called_once()

    def test_delivery_run_requires_a_frozen_git_snapshot(self) -> None:
        project_id, task_id, cycle_id, snapshot_id, actor_id = (uuid4() for _ in range(5))
        task = VerificationTask(id=task_id, project_id=project_id, title="演示", requirement_key="DEMO-1", created_by=actor_id)
        cycle = VerificationCycle(id=cycle_id, task_id=task_id, sequence_no=1, business_status="DRAFT")
        snapshot = InputSnapshot(
            id=snapshot_id,
            cycle_id=cycle_id,
            snapshot_hash="sha256:demo",
            policy_version="v1",
            workflow_version="v1",
            created_by=actor_id,
            purpose="FORMAL",
            assessment_profile="DELIVERY_VERIFICATION",
        )
        session = _SnapshotGateSession({
            (InputSnapshot, snapshot_id): snapshot,
            (VerificationCycle, cycle_id): cycle,
            (VerificationTask, task_id): task,
        })
        with patch("app.application.services.analysis_service.require_project_role"):
            with self.assertRaises(DomainError) as raised:
                start_analysis_run(session, snapshot_id=snapshot_id, actor_id=actor_id, idempotency_key="demo", correlation_id="demo")

        self.assertEqual(raised.exception.code, "INPUT_STALE")


if __name__ == "__main__":
    unittest.main()
