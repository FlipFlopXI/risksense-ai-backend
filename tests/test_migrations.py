from uuid import uuid4

from alembic import command
from sqlalchemy import create_engine, inspect, text

from conftest import TEST_DATABASE_URL, alembic_config, reset_test_schema


ORIGINAL_REVISION = "e31c044fd963"
FOUNDATION_REVISION = "a14f1c2d9b01"


def _index_names(inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table)}


def _constraint_names(inspector, table: str) -> set[str]:
    return {item["name"] for item in inspector.get_check_constraints(table) if item["name"]}


def test_fresh_database_upgrades_to_head_with_expected_schema():
    reset_test_schema()
    try:
        command.upgrade(alembic_config(), "head")
        engine = create_engine(TEST_DATABASE_URL)
        try:
            inspector = inspect(engine)
            assert set(inspector.get_table_names()) == {
                "access_entitlements", "alembic_version", "audit_logs", "clinicians",
                "health_profiles", "insurance", "lab_results", "ml_models",
                "patient_clinicians", "patients", "predictions", "reports",
                "subscriptions", "users", "vitals",
            }
            entitlement_fks = {
                tuple(fk["constrained_columns"]): (fk["referred_table"], fk["options"].get("ondelete"))
                for fk in inspector.get_foreign_keys("access_entitlements")
            }
            assert entitlement_fks[("patient_id",)] == ("patients", "CASCADE")
            assert entitlement_fks[("clinician_id",)] == ("clinicians", "SET NULL")
            assert entitlement_fks[("subscription_id",)] == ("subscriptions", "CASCADE")
            assert entitlement_fks[("insurance_id",)] == ("insurance", "CASCADE")
            link_fks = {
                tuple(fk["constrained_columns"]): fk["referred_table"]
                for fk in inspector.get_foreign_keys("patient_clinicians")
            }
            assert link_fks == {("patient_id",): "patients", ("clinician_id",): "clinicians"}
            assert {
                "ck_entitlement_source_reference", "ck_entitlement_dates",
                "ck_entitlement_source", "ck_entitlement_status",
            } <= _constraint_names(inspector, "access_entitlements")
            assert "uq_patient_clinician" in {
                item["name"] for item in inspector.get_unique_constraints("patient_clinicians")
            }
            indexes = {item["name"]: item for item in inspector.get_indexes("access_entitlements")}
            assert {
                "ix_entitlements_patient_status", "uq_entitlements_current_source",
                "ix_access_entitlements_expires_at",
            } <= set(indexes)
            assert indexes["uq_entitlements_current_source"]["unique"]
        finally:
            engine.dispose()
    finally:
        command.upgrade(alembic_config(), "head")


def test_original_revision_upgrades_without_trusting_legacy_authorization_state():
    reset_test_schema()
    patient_user_id, patient_id = uuid4(), uuid4()
    clinician_user_id, clinician_id = uuid4(), uuid4()
    subscription_id, insurance_id = uuid4(), uuid4()
    try:
        command.upgrade(alembic_config(), ORIGINAL_REVISION)
        engine = create_engine(TEST_DATABASE_URL)
        try:
            with engine.begin() as connection:
                connection.execute(text("""
                    INSERT INTO users (id, email, password_hash, role, is_active)
                    VALUES (:patient_user_id, 'legacy.patient@example.test', 'legacy-hash', 'PATIENT', true),
                           (:clinician_user_id, 'legacy.clinician@example.test', 'legacy-hash', 'CLINICIAN', true)
                """), {"patient_user_id": patient_user_id, "clinician_user_id": clinician_user_id})
                connection.execute(text("""
                    INSERT INTO patients (id, user_id, first_name, last_name)
                    VALUES (:patient_id, :user_id, 'Legacy', 'Patient')
                """), {"patient_id": patient_id, "user_id": patient_user_id})
                connection.execute(text("""
                    INSERT INTO clinicians (id, user_id, first_name, last_name, license_number)
                    VALUES (:id, :user_id, 'Legacy', 'Clinician', 'LIC-LEGACY-1')
                """), {"id": clinician_id, "user_id": clinician_user_id})
                connection.execute(text("""
                    INSERT INTO subscriptions (id, patient_id, plan, status)
                    VALUES (:id, :patient_id, 'premium', 'active')
                """), {"id": subscription_id, "patient_id": patient_id})
                connection.execute(text("""
                    INSERT INTO insurance (id, patient_id, provider_name, coverage_status)
                    VALUES (:id, :patient_id, 'Legacy Health', 'active')
                """), {"id": insurance_id, "patient_id": patient_id})
            command.upgrade(alembic_config(), FOUNDATION_REVISION)
            with engine.connect() as connection:
                patient = connection.execute(text(
                    "SELECT first_name, last_name, gender, ethnicity FROM patients WHERE id=:id"
                ), {"id": patient_id}).mappings().one()
                assert dict(patient) == {
                    "first_name": "Legacy", "last_name": "Patient", "gender": None, "ethnicity": None,
                }
                assert connection.scalar(text(
                    "SELECT status FROM subscriptions WHERE id=:id"
                ), {"id": subscription_id}) == "pending"
                insurance = connection.execute(text("""
                    SELECT coverage_status, verification_status, verified_at,
                           requested_clinician_risk_sense_id
                    FROM insurance WHERE id=:id
                """), {"id": insurance_id}).mappings().one()
                assert insurance["coverage_status"] == "pending"
                assert insurance["verification_status"] == "pending"
                assert insurance["verified_at"] is None
                assert insurance["requested_clinician_risk_sense_id"] is None
                assert connection.scalar(text(
                    "SELECT count(*) FROM access_entitlements WHERE status='active'"
                )) == 0
                clinician = connection.execute(text("""
                    SELECT risk_sense_id, approval_status, approved_at, institution
                    FROM clinicians WHERE id=:id
                """), {"id": clinician_id}).mappings().one()
                assert clinician["risk_sense_id"].startswith("RS-CLN-")
                assert clinician["approval_status"] == "pending"
                assert clinician["approved_at"] is None
                assert clinician["institution"] is None
        finally:
            engine.dispose()
    finally:
        command.upgrade(alembic_config(), "head")


def test_foundation_revision_downgrades_to_original_revision():
    reset_test_schema()
    try:
        command.upgrade(alembic_config(), FOUNDATION_REVISION)
        command.downgrade(alembic_config(), ORIGINAL_REVISION)
        engine = create_engine(TEST_DATABASE_URL)
        try:
            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
            assert {"users", "patients", "clinicians", "subscriptions", "insurance"} <= tables
            assert {"access_entitlements", "patient_clinicians", "lab_results"}.isdisjoint(tables)
            assert "risk_sense_id" not in {column["name"] for column in inspector.get_columns("clinicians")}
            assert "verification_status" not in {column["name"] for column in inspector.get_columns("insurance")}
            assert "gender" not in {column["name"] for column in inspector.get_columns("patients")}
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == ORIGINAL_REVISION
        finally:
            engine.dispose()
    finally:
        command.upgrade(alembic_config(), "head")
