"""Drug conversations, patient medications and optional reproductive context.

Revision ID: c83f20a6d912
Revises: b72e9a61c403
Downgrade discards the new conversations, medications and reproductive fields.
Legacy current_medications text and all existing clinical tables are retained.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c83f20a6d912"
down_revision = "b72e9a61c403"
branch_labels = None
depends_on = None


def timestamps():
    return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade():
    for column in (
        sa.Column("pregnancy_status", sa.String(30)),
        sa.Column("estimated_due_date", sa.Date()),
        sa.Column("pregnancy_context_updated_at", sa.DateTime(timezone=True)),
        sa.Column("breastfeeding_status", sa.String(30)),
        sa.Column("infant_date_of_birth", sa.Date()),
        sa.Column("infant_premature", sa.Boolean()),
    ):
        op.add_column("health_profiles", column)
    op.create_check_constraint("ck_profile_pregnancy_status", "health_profiles", "pregnancy_status IS NULL OR pregnancy_status IN ('NOT_PREGNANT','PREGNANT','POSSIBLY_PREGNANT','TRYING_TO_CONCEIVE','POSTPARTUM','PREFER_NOT_TO_SAY','UNKNOWN')")
    op.create_check_constraint("ck_profile_breastfeeding_status", "health_profiles", "breastfeeding_status IS NULL OR breastfeeding_status IN ('YES','NO','PREFER_NOT_TO_SAY','UNKNOWN')")
    op.create_table("patient_medications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("drug_id", sa.String(100)), sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("dose", sa.String(100)), sa.Column("unit", sa.String(50)),
        sa.Column("frequency", sa.String(100)), sa.Column("route", sa.String(100)),
        sa.Column("reason", sa.String(300)), sa.Column("prescribed_by", sa.String(200)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("start_date", sa.Date()), sa.Column("end_date", sa.Date()), *timestamps(),
        sa.CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="ck_patient_medication_dates"),
        sa.CheckConstraint("length(trim(display_name)) > 0", name="ck_patient_medication_name"))
    op.create_index("ix_patient_medications_patient_active", "patient_medications", ["patient_id", "is_active"])
    op.create_table("drug_chat_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("initiated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(100)), sa.Column("status", sa.String(10), nullable=False),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column("next_sequence", sa.Integer(), nullable=False), *timestamps(),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('OPEN','CLOSED')", name="ck_drug_session_status"),
        sa.CheckConstraint("next_sequence >= 0", name="ck_drug_session_sequence"))
    op.create_index("ix_drug_sessions_patient_updated", "drug_chat_sessions", ["patient_id", "updated_at"])
    op.create_table("drug_chat_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("drug_chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text()), sa.Column("response", postgresql.JSONB()),
        sa.Column("intent", sa.String(60), nullable=False), sa.Column("resolved_drug_ids", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_status", sa.String(30), nullable=False), sa.Column("patient_context", postgresql.JSONB(), nullable=False),
        sa.Column("source_provenance", postgresql.JSONB(), nullable=False), sa.Column("safety_classification", sa.String(60)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_drug_message_role"),
        sa.CheckConstraint("sequence > 0", name="ck_drug_message_sequence"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_drug_message_sequence"))


def downgrade():
    op.drop_table("drug_chat_messages")
    op.drop_table("drug_chat_sessions")
    op.drop_table("patient_medications")
    op.drop_constraint("ck_profile_breastfeeding_status", "health_profiles", type_="check")
    op.drop_constraint("ck_profile_pregnancy_status", "health_profiles", type_="check")
    for column in ("infant_premature", "infant_date_of_birth", "breastfeeding_status", "pregnancy_context_updated_at", "estimated_due_date", "pregnancy_status"):
        op.drop_column("health_profiles", column)
