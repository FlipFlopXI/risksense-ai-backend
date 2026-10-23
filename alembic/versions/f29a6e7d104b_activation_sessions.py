"""Add patient web activation sessions.

Revision ID: f29a6e7d104b
Revises: d54b8c21e7f0
"""
from alembic import op
import sqlalchemy as sa

revision = "f29a6e7d104b"
down_revision = "d54b8c21e7f0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "activation_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("handoff_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("credential_hash", sa.String(64), unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exchanged_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("entitlement_id", sa.Uuid(), sa.ForeignKey("access_entitlements.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_activation_sessions_patient_id", "activation_sessions", ["patient_id"])
    op.create_index("ix_activation_sessions_expires_at", "activation_sessions", ["expires_at"])


def downgrade():
    op.drop_index("ix_activation_sessions_expires_at", table_name="activation_sessions")
    op.drop_index("ix_activation_sessions_patient_id", table_name="activation_sessions")
    op.drop_table("activation_sessions")
