"""Authentication sessions and longitudinal body measurements.

Revision ID: d54b8c21e7f0
Revises: c83f20a6d912
"""
from alembic import op
import sqlalchemy as sa

revision = "d54b8c21e7f0"
down_revision = "c83f20a6d912"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_jti_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_index("ix_auth_sessions_revoked_at", "auth_sessions", ["revoked_at"])
    op.create_table(
        "body_measurements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("height_cm", sa.Float()), sa.Column("weight_kg", sa.Float()),
        sa.Column("waist_circumference_cm", sa.Float()),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("height_cm IS NULL OR (height_cm > 0 AND height_cm <= 300)", name="ck_body_measurement_height"),
        sa.CheckConstraint("weight_kg IS NULL OR (weight_kg > 0 AND weight_kg <= 500)", name="ck_body_measurement_weight"),
        sa.CheckConstraint("waist_circumference_cm IS NULL OR (waist_circumference_cm > 0 AND waist_circumference_cm <= 300)", name="ck_body_measurement_waist"),
        sa.CheckConstraint("height_cm IS NOT NULL OR weight_kg IS NOT NULL OR waist_circumference_cm IS NOT NULL", name="ck_body_measurement_nonempty"),
    )
    op.create_index("ix_body_measurements_patient_id", "body_measurements", ["patient_id"])
    op.create_index("ix_body_measurements_measured_at", "body_measurements", ["measured_at"])
    op.create_index("ix_body_measurements_patient_time", "body_measurements", ["patient_id", "measured_at"])
    # Preserve existing profile values as one honest historical baseline point.
    op.execute(sa.text("""
        INSERT INTO body_measurements
            (id, patient_id, height_cm, weight_kg, waist_circumference_cm, source, measured_at)
        SELECT gen_random_uuid(), patient_id, height_cm, weight_kg, waist_circumference_cm,
               'migration_health_profile', COALESCE(updated_at, created_at, now())
        FROM health_profiles
        WHERE height_cm IS NOT NULL OR weight_kg IS NOT NULL OR waist_circumference_cm IS NOT NULL
    """))


def downgrade():
    op.drop_table("body_measurements")
    op.drop_table("auth_sessions")
