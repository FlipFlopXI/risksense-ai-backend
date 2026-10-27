"""Track completed patient meditation sessions.

Revision ID: e7b51c629a04
Revises: d18c7a41b903
"""
from alembic import op
import sqlalchemy as sa

revision = "e7b51c629a04"
down_revision = "d18c7a41b903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meditation_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("track_id", sa.String(length=40), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("category IN ('sleep','ambient','nature','instrumental')",
                           name="ck_meditation_sessions_category"),
        sa.CheckConstraint("duration_seconds > 0 AND duration_seconds <= 14400",
                           name="ck_meditation_sessions_duration"),
    )
    op.create_index("ix_meditation_sessions_patient_started", "meditation_sessions",
                    ["patient_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_meditation_sessions_patient_started", table_name="meditation_sessions")
    op.drop_table("meditation_sessions")
