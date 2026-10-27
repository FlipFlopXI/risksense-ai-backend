"""Add email challenges for password recovery.

Revision ID: f851c4d3a920
Revises: fe30b9a82104
"""
from alembic import op
import sqlalchemy as sa

revision = "f851c4d3a920"
down_revision = "fe30b9a82104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_challenges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resend_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_password_reset_challenges_attempts"),
    )
    op.create_index("ix_password_reset_challenges_user_id", "password_reset_challenges", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_password_reset_challenges_user_id", table_name="password_reset_challenges")
    op.drop_table("password_reset_challenges")
