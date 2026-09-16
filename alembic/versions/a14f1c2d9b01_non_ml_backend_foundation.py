"""Non-ML backend foundation and access control.

Revision ID: a14f1c2d9b01
Revises: e31c044fd963
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a14f1c2d9b01"
down_revision: Union[str, Sequence[str], None] = "e31c044fd963"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clinicians", sa.Column("risk_sense_id", sa.String(12), nullable=True))
    op.add_column("clinicians", sa.Column("approval_status", sa.String(20), nullable=False, server_default="pending"))
    op.add_column("clinicians", sa.Column("approved_at", sa.DateTime(timezone=True)))
    op.add_column("clinicians", sa.Column("institution", sa.String(200)))
    op.add_column("clinicians", sa.Column("last_login_at", sa.DateTime(timezone=True)))
    op.execute("""
        WITH numbered AS (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS number FROM clinicians
        )
        UPDATE clinicians c SET risk_sense_id = 'RS-CLN-' || lpad(numbered.number::text, 5, '0')
        FROM numbered WHERE numbered.id = c.id
    """)
    op.alter_column("clinicians", "risk_sense_id", nullable=False)
    op.create_index("ix_clinicians_risk_sense_id", "clinicians", ["risk_sense_id"], unique=True)
    op.create_index("ix_clinicians_approval_status", "clinicians", ["approval_status"])
    op.create_check_constraint("ck_clinicians_risk_sense_id_format", "clinicians", "risk_sense_id ~ '^RS-CLN-[0-9]{5}$'")
    op.create_check_constraint("ck_clinicians_approval_status", "clinicians", "approval_status IN ('pending', 'approved', 'suspended', 'rejected')")

    op.execute("UPDATE subscriptions SET status = 'pending'")
    op.create_check_constraint("ck_subscriptions_status", "subscriptions", "status IN ('pending', 'active', 'inactive', 'expired', 'cancelled')")
    op.add_column("subscriptions", sa.Column("requested_clinician_risk_sense_id", sa.String(12)))
    op.add_column("insurance", sa.Column("requested_clinician_risk_sense_id", sa.String(12)))
    op.add_column("insurance", sa.Column("verification_status", sa.String(20), nullable=False, server_default="pending"))
    op.add_column("insurance", sa.Column("verification_source", sa.String(50)))
    op.add_column("insurance", sa.Column("verified_at", sa.DateTime(timezone=True)))
    op.add_column("insurance", sa.Column("coverage_starts_at", sa.DateTime(timezone=True)))
    op.add_column("insurance", sa.Column("coverage_expires_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE insurance SET coverage_status = 'pending', verification_status = 'pending'")
    op.create_index("ix_insurance_verification_status", "insurance", ["verification_status"])
    op.create_check_constraint("ck_insurance_verification_status", "insurance", "verification_status IN ('pending', 'verified', 'rejected', 'expired')")

    op.add_column("patients", sa.Column("gender", sa.String(50)))
    op.add_column("patients", sa.Column("ethnicity", sa.String(100)))
    op.add_column("health_profiles", sa.Column("alcohol_status", sa.String(50)))
    op.add_column("health_profiles", sa.Column("family_history_diabetes", sa.Boolean()))
    op.add_column("health_profiles", sa.Column("family_history_heart_disease", sa.Boolean()))
    op.add_column("health_profiles", sa.Column("family_history_hypertension", sa.Boolean()))

    op.create_table(
        "patient_clinicians",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("clinician_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("unlinked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("unlinked_at IS NULL OR unlinked_at >= linked_at", name="ck_patient_clinicians_dates"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_patient_clinicians_status"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinician_id"], ["clinicians.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("patient_id", "clinician_id", name="uq_patient_clinician"),
    )
    op.create_index("ix_patient_clinicians_patient_status", "patient_clinicians", ["patient_id", "status"])
    op.create_index("ix_patient_clinicians_clinician_status", "patient_clinicians", ["clinician_id", "status"])

    op.create_table(
        "access_entitlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("clinician_id", sa.Uuid()),
        sa.Column("insurance_id", sa.Uuid()),
        sa.Column("subscription_id", sa.Uuid()),
        sa.Column("reference_number", sa.String(100), nullable=False),
        sa.Column("verification_source", sa.String(50)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("(source = 'subscription' AND subscription_id IS NOT NULL AND insurance_id IS NULL) OR (source = 'insurance' AND insurance_id IS NOT NULL AND subscription_id IS NULL)", name="ck_entitlement_source_reference"),
        sa.CheckConstraint("expires_at IS NULL OR verified_at IS NULL OR expires_at >= verified_at", name="ck_entitlement_dates"),
        sa.CheckConstraint("source IN ('subscription', 'insurance')", name="ck_entitlement_source"),
        sa.CheckConstraint("status IN ('pending', 'active', 'expired', 'cancelled')", name="ck_entitlement_status"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinician_id"], ["clinicians.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["insurance_id"], ["insurance.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_number"),
    )
    op.create_index("ix_entitlements_patient_status", "access_entitlements", ["patient_id", "status"])
    op.create_index("uq_entitlements_current_source", "access_entitlements", ["patient_id", "source"], unique=True, postgresql_where=sa.text("status IN ('pending', 'active')"))
    op.create_index("ix_access_entitlements_expires_at", "access_entitlements", ["expires_at"])

    op.create_table(
        "lab_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("test_type", sa.String(30), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("verification_status", sa.String(30), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("value >= 0", name="ck_lab_results_nonnegative"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lab_results_patient_test_time", "lab_results", ["patient_id", "test_type", "measured_at"])
    op.create_check_constraint("ck_predictions_risk_score", "predictions", "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 1)")


def downgrade() -> None:
    op.drop_constraint("ck_predictions_risk_score", "predictions", type_="check")
    op.drop_table("lab_results")
    op.drop_table("access_entitlements")
    op.drop_table("patient_clinicians")
    for name in ("family_history_hypertension", "family_history_heart_disease", "family_history_diabetes", "alcohol_status"):
        op.drop_column("health_profiles", name)
    op.drop_column("patients", "ethnicity")
    op.drop_column("patients", "gender")
    op.drop_column("insurance", "requested_clinician_risk_sense_id")
    op.drop_column("subscriptions", "requested_clinician_risk_sense_id")
    op.drop_constraint("ck_insurance_verification_status", "insurance", type_="check")
    op.drop_constraint("ck_subscriptions_status", "subscriptions", type_="check")
    op.drop_index("ix_insurance_verification_status", table_name="insurance")
    for name in ("coverage_expires_at", "coverage_starts_at", "verified_at", "verification_source", "verification_status"):
        op.drop_column("insurance", name)
    op.drop_constraint("ck_clinicians_risk_sense_id_format", "clinicians", type_="check")
    op.drop_constraint("ck_clinicians_approval_status", "clinicians", type_="check")
    op.drop_index("ix_clinicians_approval_status", table_name="clinicians")
    op.drop_index("ix_clinicians_risk_sense_id", table_name="clinicians")
    for name in ("last_login_at", "institution", "approved_at", "approval_status", "risk_sense_id"):
        op.drop_column("clinicians", name)
