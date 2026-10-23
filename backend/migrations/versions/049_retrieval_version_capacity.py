"""Preserve full parser/provider/model/dimension index identities."""
from alembic import op
import sqlalchemy as sa

revision = "049_retrieval_version_capacity"
down_revision = "048_java_github_sources"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("document_chunks", "index_version"),
    ("project_retrieval_indexes", "index_version"),
    ("retrieval_index_build_runs", "target_index_version"),
]


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(table, column, existing_type=sa.String(64), type_=sa.String(512), existing_nullable=False)


def downgrade() -> None:
    # Refuse a lossy downgrade; never truncate an existing version or recompute hashes.
    for table, column in _COLUMNS:
        op.execute(f"DO $$ BEGIN IF EXISTS(SELECT 1 FROM {table} WHERE length({column})>64) THEN "
            "RAISE EXCEPTION 'Existing retrieval versions require the expanded column'; END IF; END $$")
    for table, column in _COLUMNS:
        op.alter_column(table, column, existing_type=sa.String(512), type_=sa.String(64), existing_nullable=False)
