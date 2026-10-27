"""Patient-owned mood log.

Revision ID: c0d48b7e6a92
Revises: b94f7c3a2e51
"""
from alembic import op
import sqlalchemy as sa

revision = "c0d48b7e6a92"
down_revision = "b94f7c3a2e51"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mood_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("mood", sa.String(12), nullable=False),
        sa.Column("emotion", sa.String(80), nullable=False),
        sa.Column("reason", sa.String(240), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("mood IN ('amazing','good','fine','bad','horrible')", name="ck_mood_entries_mood"),
    )
    op.create_index("ix_mood_entries_patient_date", "mood_entries", ["patient_id", "log_date"])


def downgrade() -> None:
    op.drop_index("ix_mood_entries_patient_date", table_name="mood_entries")
    op.drop_table("mood_entries")
