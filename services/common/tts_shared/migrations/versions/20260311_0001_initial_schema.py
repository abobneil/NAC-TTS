from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260311_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("source_path", sa.String(length=512), nullable=True),
        sa.Column("text_path", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_message", sa.String(length=255), nullable=True),
        sa.Column("voice_id", sa.String(length=64), nullable=False),
        sa.Column("speaking_rate", sa.Float(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("audio_path", sa.String(length=512), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")
