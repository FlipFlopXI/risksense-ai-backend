"""Store pending patient registrations until email OTP verification.

Revision ID: fe30b9a82104
Revises: e7b51c629a04
"""
from alembic import op
import sqlalchemy as sa

revision = "fe30b9a82104"
down_revision = "e7b51c629a04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_registrations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(50), nullable=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resend_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_pending_registrations_attempts"),
    )
    op.create_index("ix_pending_registrations_email", "pending_registrations", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_pending_registrations_email", table_name="pending_registrations")
    op.drop_table("pending_registrations")
