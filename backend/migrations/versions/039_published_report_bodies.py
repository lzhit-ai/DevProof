"""Persist report bodies at publication without reinterpreting historical records."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "039_published_report_bodies"
down_revision = "038_project_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "published_report_bodies",
        sa.Column("report_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_versions.id"), primary_key=True),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("body_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute("""
        CREATE FUNCTION devproof_reject_body_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Published report body is immutable'; END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER published_body_immutable BEFORE UPDATE OR DELETE ON published_report_bodies
        FOR EACH ROW EXECUTE FUNCTION devproof_reject_body_mutation()
    """)


def downgrade() -> None:
    op.drop_table("published_report_bodies")
    op.execute("DROP FUNCTION devproof_reject_body_mutation()")
