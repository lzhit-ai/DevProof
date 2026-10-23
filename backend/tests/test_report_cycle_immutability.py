"""Regression guard for immutable published verification cycles."""

import os
import unittest

os.environ.setdefault("JWT_SECRET", "test-only-placeholder-key-0123456789")

from app.application.services.report_service import _assert_cycle_open_for_report_write
from app.domain.errors import DomainError
from app.infrastructure.persistence.models import VerificationCycle


class ReportCycleImmutabilityTests(unittest.TestCase):
    def test_published_cycle_rejects_later_report_writes(self) -> None:
        with self.assertRaisesRegex(DomainError, "已发布") as raised:
            _assert_cycle_open_for_report_write(VerificationCycle(business_status="PUBLISHED"))

        self.assertEqual(raised.exception.code, "STATE_CONFLICT")

    def test_open_cycle_remains_writable(self) -> None:
        _assert_cycle_open_for_report_write(VerificationCycle(business_status="DRAFT"))
