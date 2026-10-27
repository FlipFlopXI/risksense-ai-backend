"""Patient-reported glucose readings and insulin doses.

Revision ID: b94f7c3a2e51
Revises: a7c2e6d48f31
"""
from alembic import op
import sqlalchemy as sa

revision = "b94f7c3a2e51"
down_revision = "a7c2e6d48f31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metabolic_log_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("value", sa.Numeric(8, 2), nullable=False),
        sa.Column("unit", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("category IN ('fasting','post_meal','general','insulin_dose')", name="ck_metabolic_log_category"),
        sa.CheckConstraint("value > 0 AND value <= 1000", name="ck_metabolic_log_value"),
        sa.CheckConstraint("(category = 'insulin_dose' AND unit = 'U') OR (category <> 'insulin_dose' AND unit = 'mg/dL')", name="ck_metabolic_log_unit"),
    )
    op.create_index("ix_metabolic_log_patient_date", "metabolic_log_entries", ["patient_id", "log_date"])


def downgrade() -> None:
    op.drop_index("ix_metabolic_log_patient_date", table_name="metabolic_log_entries")
    op.drop_table("metabolic_log_entries")
