"""Nullable waist circumference in centimetres for Diabetes screening.

Revision ID: b72e9a61c403
Revises: a14f1c2d9b01
"""
from alembic import op
import sqlalchemy as sa

revision = "b72e9a61c403"
down_revision = "a14f1c2d9b01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("health_profiles", sa.Column("waist_circumference_cm", sa.Float(), nullable=True))
    op.create_check_constraint(
        "ck_health_profiles_waist_cm", "health_profiles",
        "waist_circumference_cm IS NULL OR (waist_circumference_cm > 0 AND waist_circumference_cm <= 300)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_health_profiles_waist_cm", "health_profiles", type_="check")
    op.drop_column("health_profiles", "waist_circumference_cm")
