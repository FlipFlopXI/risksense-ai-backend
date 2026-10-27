"""Patient activity and body composition logs.

Revision ID: a7c2e6d48f31
Revises: f6a4b29c8d10
"""
from alembic import op
import sqlalchemy as sa

revision = "a7c2e6d48f31"
down_revision = "f6a4b29c8d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("steps", sa.Integer(), nullable=False),
        sa.Column("activity_minutes", sa.Integer(), nullable=False),
        sa.Column("activity_calories_kcal", sa.Float(), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("steps BETWEEN 0 AND 100000", name="ck_activity_steps"),
        sa.CheckConstraint("activity_minutes BETWEEN 0 AND 1440", name="ck_activity_minutes"),
        sa.CheckConstraint("activity_calories_kcal BETWEEN 0 AND 10000", name="ck_activity_calories"),
        sa.CheckConstraint("distance_km BETWEEN 0 AND 500", name="ck_activity_distance"),
    )
    op.create_index("ix_activity_patient_date", "activity_entries", ["patient_id", "log_date"])
    op.create_table(
        "body_composition_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skeletal_muscle_kg", sa.Float(), nullable=False),
        sa.Column("body_fat_percent", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("skeletal_muscle_kg > 0 AND skeletal_muscle_kg <= 250", name="ck_body_composition_muscle"),
        sa.CheckConstraint("body_fat_percent >= 0 AND body_fat_percent <= 100", name="ck_body_composition_fat"),
    )
    op.create_index("ix_body_composition_patient_time", "body_composition_entries", ["patient_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_body_composition_patient_time", table_name="body_composition_entries")
    op.drop_table("body_composition_entries")
    op.drop_index("ix_activity_patient_date", table_name="activity_entries")
    op.drop_table("activity_entries")
