"""Patient-owned food log and calorie goal.

Revision ID: e42d6b93c107
Revises: c91d7e2a4f06
"""
from alembic import op
import sqlalchemy as sa

revision = "e42d6b93c107"
down_revision = "c91d7e2a4f06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nutrition_goals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("calories_kcal", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("patient_id", name="uq_nutrition_goals_patient"),
        sa.CheckConstraint("calories_kcal BETWEEN 500 AND 6000", name="ck_nutrition_goal_calories"),
    )
    op.create_table(
        "food_log_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("meal_type", sa.String(24), nullable=False),
        sa.Column("food_name", sa.String(200), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(100)),
        sa.Column("amount_g", sa.Numeric(9, 2), nullable=False),
        sa.Column("calories_kcal", sa.Numeric(10, 2), nullable=False),
        sa.Column("carbs_g", sa.Numeric(10, 2), nullable=False),
        sa.Column("fat_g", sa.Numeric(10, 2), nullable=False),
        sa.Column("protein_g", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("meal_type IN ('breakfast','lunch','dinner','morning_snack','afternoon_snack','evening_snack')", name="ck_food_log_meal_type"),
        sa.CheckConstraint("amount_g > 0 AND amount_g <= 5000", name="ck_food_log_amount"),
        sa.CheckConstraint("calories_kcal >= 0 AND calories_kcal <= 20000", name="ck_food_log_calories"),
        sa.CheckConstraint("carbs_g >= 0 AND fat_g >= 0 AND protein_g >= 0", name="ck_food_log_macros"),
    )
    op.create_index("ix_food_log_patient_date", "food_log_entries", ["patient_id", "log_date"])


def downgrade() -> None:
    op.drop_index("ix_food_log_patient_date", table_name="food_log_entries")
    op.drop_table("food_log_entries")
    op.drop_table("nutrition_goals")
