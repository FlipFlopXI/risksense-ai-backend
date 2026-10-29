"""Add patient opt-in for elevated risk result emails.

Revision ID: b6e1a2d4c930
Revises: f851c4d3a920
"""

from alembic import op
import sqlalchemy as sa


revision = "b6e1a2d4c930"
down_revision = "f851c4d3a920"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_notification_preferences",
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("email_elevated_results", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("patient_notification_preferences")
