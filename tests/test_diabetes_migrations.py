from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from conftest import TEST_DATABASE_URL, alembic_config, reset_test_schema


def test_waist_upgrade_preserves_legacy_profile_and_downgrade():
    reset_test_schema()
    engine = create_engine(TEST_DATABASE_URL)
    user, patient, profile = uuid4(), uuid4(), uuid4()
    try:
        command.upgrade(alembic_config(), "a14f1c2d9b01")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id,email,password_hash,role,is_active) VALUES (:id,'waist@example.test','unused','PATIENT',true)"), {"id": user})
            connection.execute(text("INSERT INTO patients (id,user_id,first_name,last_name) VALUES (:id,:user,'Legacy','Profile')"), {"id": patient, "user": user})
            connection.execute(text("INSERT INTO health_profiles (id,patient_id,height_cm,weight_kg) VALUES (:id,:patient,178,80)"), {"id": profile, "patient": patient})
        command.upgrade(alembic_config(), "b72e9a61c403")
        with engine.connect() as connection:
            row = connection.execute(text("SELECT height_cm,weight_kg,waist_circumference_cm FROM health_profiles WHERE id=:id"), {"id": profile}).one()
            assert tuple(row) == (178, 80, None)
        with engine.begin() as connection:
            connection.execute(text("UPDATE health_profiles SET waist_circumference_cm=100 WHERE id=:id"), {"id": profile})
        for invalid in (0, -1, 301):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(text("UPDATE health_profiles SET waist_circumference_cm=:value WHERE id=:id"), {"value": invalid, "id": profile})
        command.downgrade(alembic_config(), "a14f1c2d9b01")
        assert "waist_circumference_cm" not in {c["name"] for c in inspect(engine).get_columns("health_profiles")}
        with engine.connect() as connection:
            assert tuple(connection.execute(text("SELECT height_cm,weight_kg FROM health_profiles WHERE id=:id"), {"id": profile}).one()) == (178, 80)
    finally:
        engine.dispose()
        command.upgrade(alembic_config(), "head")
