"""add assessment profiles to frozen verification aggregates

Revision ID: 016_assessment_profiles
Revises: 015_dual_core_orchestration
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op


revision = "016_assessment_profiles"
down_revision = "015_dual_core_orchestration"
branch_labels = None
depends_on = None


_PROFILE_VALUES = "'DELIVERY_VERIFICATION', 'PROJECT_STATUS_SUMMARY', 'SECURITY_BASELINE', 'QUALITY_TREND'"


def _add_profile_column(table_name: str, column_name: str, constraint_name: str) -> None:
    op.add_column(
        table_name,
        sa.Column(column_name, sa.String(length=48), nullable=False, server_default="DELIVERY_VERIFICATION"),
    )
    op.create_check_constraint(constraint_name, table_name, f"{column_name} IN ({_PROFILE_VALUES})")


def upgrade() -> None:
    # Historical records retain their existing delivery-verification meaning. No hashes are recalculated.
    _add_profile_column("input_snapshots", "assessment_profile", "ck_input_snapshots_assessment_profile")
    _add_profile_column("analysis_runs", "assessment_profile", "ck_analysis_runs_assessment_profile")
    _add_profile_column("orchestration_templates", "assessment_profile", "ck_orchestration_templates_assessment_profile")
    _add_profile_column(
        "analysis_run_orchestration_snapshots",
        "assessment_profile",
        "ck_run_orchestration_snapshots_assessment_profile",
    )
    _add_profile_column("report_versions", "record_type", "ck_report_versions_record_type")
    _add_profile_column("published_records", "record_type", "ck_published_records_record_type")


def downgrade() -> None:
    for table_name, column_name, constraint_name in reversed(
        (
            ("published_records", "record_type", "ck_published_records_record_type"),
            ("report_versions", "record_type", "ck_report_versions_record_type"),
            (
                "analysis_run_orchestration_snapshots",
                "assessment_profile",
                "ck_run_orchestration_snapshots_assessment_profile",
            ),
            ("orchestration_templates", "assessment_profile", "ck_orchestration_templates_assessment_profile"),
            ("analysis_runs", "assessment_profile", "ck_analysis_runs_assessment_profile"),
            ("input_snapshots", "assessment_profile", "ck_input_snapshots_assessment_profile"),
        )
    ):
        op.drop_constraint(constraint_name, table_name, type_="check")
        op.drop_column(table_name, column_name)
