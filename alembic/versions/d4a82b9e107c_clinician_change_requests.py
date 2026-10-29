"""Add reviewed patient clinician change requests.

Revision ID: d4a82b9e107c
Revises: b6e1a2d4c930
"""
from alembic import op
import sqlalchemy as sa

revision = "d4a82b9e107c"
down_revision = "b6e1a2d4c930"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinician_change_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_clinician_id", sa.Uuid(), sa.ForeignKey("clinicians.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("new_clinician_id", sa.Uuid(), sa.ForeignKey("clinicians.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_admin_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_clinician_change_status"),
        sa.CheckConstraint("old_clinician_id <> new_clinician_id", name="ck_clinician_change_distinct"),
    )
    op.create_index("uq_clinician_change_pending_patient", "clinician_change_requests", ["patient_id"],
                    unique=True, postgresql_where=sa.text("status = 'pending'"))
    op.create_index("ix_clinician_change_status_created", "clinician_change_requests", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_clinician_change_status_created", table_name="clinician_change_requests")
    op.drop_index("uq_clinician_change_pending_patient", table_name="clinician_change_requests")
    op.drop_table("clinician_change_requests")
