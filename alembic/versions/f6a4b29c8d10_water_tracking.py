"""Patient water goals and timestamped water log.

Revision ID: f6a4b29c8d10
Revises: e42d6b93c107
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a4b29c8d10"
down_revision = "e42d6b93c107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "water_goals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goal_ml", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("patient_id", name="uq_water_goals_patient"),
        sa.CheckConstraint("goal_ml BETWEEN 250 AND 4000", name="ck_water_goal_ml"),
    )
    op.create_table(
        "water_log_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("amount_ml", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_ml BETWEEN 1 AND 4000", name="ck_water_log_amount"),
    )
    op.create_index("ix_water_log_patient_date", "water_log_entries", ["patient_id", "log_date"])


def downgrade() -> None:
    op.drop_index("ix_water_log_patient_date", table_name="water_log_entries")
    op.drop_table("water_log_entries")
    op.drop_table("water_goals")
