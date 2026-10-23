from uuid import uuid4
import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from conftest import TEST_DATABASE_URL, alembic_config, reset_test_schema


def test_drug_upgrade_legacy_preservation_constraints_and_downgrade():
    reset_test_schema()
    engine = create_engine(TEST_DATABASE_URL)
    user_id, patient_id, profile_id = uuid4(), uuid4(), uuid4()
    clinician_user, clinician, subscription, model = uuid4(), uuid4(), uuid4(), uuid4()
    try:
        command.upgrade(alembic_config(), "b72e9a61c403")
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id,email,password_hash,role,is_active) VALUES (:id,'drug.migration@example.test','unused','PATIENT',true)"), {"id": user_id})
            conn.execute(text("INSERT INTO patients (id,user_id,first_name,last_name) VALUES (:id,:user,'Legacy','Patient')"), {"id": patient_id, "user": user_id})
            conn.execute(text("INSERT INTO health_profiles (id,patient_id,height_cm,weight_kg,waist_circumference_cm,current_medications) VALUES (:id,:patient,178,80,100,'legacy medication text')"), {"id": profile_id, "patient": patient_id})
            conn.execute(text("INSERT INTO users (id,email,password_hash,role,is_active) VALUES (:id,'drug.clinician@example.test','unused','CLINICIAN',true)"), {"id": clinician_user})
            conn.execute(text("INSERT INTO clinicians(id,user_id,first_name,last_name,risk_sense_id,approval_status) VALUES (:id,:user,'Legacy','Clinician','RS-CLN-89001','approved')"), {"id": clinician, "user": clinician_user})
            conn.execute(text("INSERT INTO subscriptions(id,patient_id,plan,status) VALUES (:id,:patient,'premium','active')"), {"id": subscription, "patient": patient_id})
            conn.execute(text("INSERT INTO patient_clinicians(id,patient_id,clinician_id,status) VALUES (:id,:patient,:clinician,'active')"), {"id": uuid4(), "patient": patient_id, "clinician": clinician})
            conn.execute(text("INSERT INTO access_entitlements(id,patient_id,source,status,clinician_id,subscription_id,reference_number,verified_at) VALUES (:id,:patient,'subscription','active',:clinician,:subscription,'legacy-drug-test',now())"), {"id": uuid4(), "patient": patient_id, "clinician": clinician, "subscription": subscription})
            conn.execute(text("INSERT INTO vitals(id,patient_id,blood_pressure_systolic,blood_pressure_diastolic) VALUES (:id,:patient,130,80)"), {"id": uuid4(), "patient": patient_id})
            conn.execute(text("INSERT INTO lab_results(id,patient_id,test_type,value,unit,source,verification_status,measured_at) VALUES (:id,:patient,'glucose',100,'mg/dL','synthetic migration test','patient_reported',now())"), {"id": uuid4(), "patient": patient_id})
            conn.execute(text("INSERT INTO ml_models(id,name,version,prediction_target,algorithm,is_active) VALUES (:id,'Legacy test','1','test','test',false)"), {"id": model})
            conn.execute(text("INSERT INTO predictions(id,patient_id,model_id,prediction_target,risk_score,risk_classification) VALUES (:id,:patient,:model,'test',0.5,'test')"), {"id": uuid4(), "patient": patient_id, "model": model})
            before = {table: conn.scalar(text(f'SELECT count(*) FROM {table}')) for table in ('patients','health_profiles','vitals','lab_results','predictions','access_entitlements','patient_clinicians')}
            snapshots = {table: conn.execute(text(f'SELECT row_to_json(t)::jsonb FROM {table} t ORDER BY id')).all() for table in before if table != 'health_profiles'}
        command.upgrade(alembic_config(), "head")
        inspector = inspect(engine)
        assert {"drug_chat_sessions", "drug_chat_messages", "patient_medications"} <= set(inspector.get_table_names())
        assert {fk["referred_table"] for fk in inspector.get_foreign_keys("drug_chat_messages")} == {"drug_chat_sessions", "users"}
        assert "ix_drug_sessions_patient_updated" in {i["name"] for i in inspector.get_indexes("drug_chat_sessions")}
        assert "uq_drug_message_sequence" in {i["name"] for i in inspector.get_unique_constraints("drug_chat_messages")}
        with engine.connect() as conn:
            row = conn.execute(text("SELECT height_cm,weight_kg,waist_circumference_cm,current_medications,pregnancy_status FROM health_profiles WHERE id=:id"), {"id": profile_id}).one()
            assert tuple(row) == (178,80,100,'legacy medication text',None)
            for table, count in before.items():
                assert conn.scalar(text(f'SELECT count(*) FROM {table}')) == count
            for table, rows in snapshots.items():
                assert conn.execute(text(f'SELECT row_to_json(t)::jsonb FROM {table} t ORDER BY id')).all() == rows
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text("UPDATE health_profiles SET pregnancy_status='invented' WHERE id=:id"), {"id": profile_id})
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text("INSERT INTO patient_medications(id,patient_id,display_name,is_active,start_date,end_date) VALUES (:id,:patient,'medicine',true,'2026-02-01','2026-01-01')"), {"id": uuid4(), "patient": patient_id})
        command.downgrade(alembic_config(), "b72e9a61c403")
        assert "drug_chat_sessions" not in inspect(engine).get_table_names()
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT current_medications FROM health_profiles WHERE id=:id"), {"id": profile_id}) == 'legacy medication text'
    finally:
        engine.dispose()
        command.upgrade(alembic_config(), "head")
