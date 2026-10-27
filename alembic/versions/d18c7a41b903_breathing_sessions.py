"""Track completed patient breathing sessions.

Revision ID: d18c7a41b903
Revises: c0d48b7e6a92
"""
from alembic import op
import sqlalchemy as sa

revision = "d18c7a41b903"
down_revision = "c0d48b7e6a92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "breathing_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exercise", sa.String(length=12), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("exercise IN ('box','478','belly','custom')", name="ck_breathing_sessions_exercise"),
        sa.CheckConstraint("duration_seconds > 0 AND duration_seconds <= 3600", name="ck_breathing_sessions_duration"),
    )
    op.create_index("ix_breathing_sessions_patient_started", "breathing_sessions", ["patient_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_breathing_sessions_patient_started", table_name="breathing_sessions")
    op.drop_table("breathing_sessions")
