"""Admin model controls must fail closed for unsupported registry entries."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.admin import resume_model
from app.services import auth_service
from app.models.clinician import Clinician
from app.services.model_metrics_service import _diabetes_holdout_accuracy, verified_holdout_accuracy
from app.services.diabetes_service import MODEL_ID as DIABETES_MODEL_ID
from app.services.risk_analysis_service import MODEL_ID as HEART_MODEL_ID
from app.schemas.clinician_assessment import ClinicianProfileUpdate


class _RegistrySession:
    def __init__(self, model):
        self.model = model

    def get(self, model_class, model_id):
        return self.model


def test_unsupported_model_cannot_be_resumed():
    model = SimpleNamespace(id=uuid4(), prediction_target="drug_response")
    with pytest.raises(HTTPException) as error:
        resume_model(model.id, admin=SimpleNamespace(id=uuid4()),
                     db=_RegistrySession(model))
    assert error.value.status_code == 409


def test_clinician_profile_gender_is_explicit_and_limited():
    assert ClinicianProfileUpdate(gender="female").gender == "female"
    with pytest.raises(ValidationError):
        ClinicianProfileUpdate(gender="unknown")
    with pytest.raises(ValidationError):
        ClinicianProfileUpdate(gender="male", is_admin=True)


def test_admin_user_names_need_no_pending_clinician_gender_column():
    from sqlalchemy import select

    query = select(Clinician.user_id, Clinician.first_name, Clinician.last_name)
    assert "clinicians.gender" not in str(query)


def test_verified_model_accuracies_are_scoped_to_artifact_versions():
    diabetes = SimpleNamespace(id=DIABETES_MODEL_ID, prediction_target="diabetes_risk", version="1.0.0")
    heart = SimpleNamespace(id=HEART_MODEL_ID, prediction_target="heart_disease", version="1.0.0")
    diabetes_accuracy, diabetes_source = verified_holdout_accuracy(diabetes)
    heart_accuracy, heart_source = verified_holdout_accuracy(heart)
    assert diabetes_accuracy == pytest.approx(640 / 944)
    assert diabetes_source == "NHANES held-out test split"
    assert heart_accuracy == pytest.approx(0.541)
    assert heart_source == "Cleveland held-out test split"
    assert verified_holdout_accuracy(SimpleNamespace(id=uuid4(), prediction_target="diabetes_risk", version="1.0.0")) == (None, None)
    assert verified_holdout_accuracy(SimpleNamespace(id=DIABETES_MODEL_ID, prediction_target="diabetes_risk", version="2.0.0")) == (None, None)


def test_diabetes_accuracy_requires_consistent_holdout_summary():
    assert _diabetes_holdout_accuracy({"split": "other"}) is None


def test_clinician_login_updates_timestamp_without_loading_profile(monkeypatch):
    user = SimpleNamespace(id=uuid4(), email="clinician@example.test", role=auth_service.UserRole.CLINICIAN,
                           password_hash="stored", is_active=True)
    monkeypatch.setattr(auth_service, "get_user_by_email", lambda db, email: user)
    monkeypatch.setattr(auth_service, "verify_password", lambda supplied, stored: True)

    class Session:
        def __init__(self):
            self.statement = None
            self.committed = False

        def execute(self, statement):
            self.statement = statement

        def commit(self):
            self.committed = True

    session = Session()
    assert auth_service.authenticate_user(session, user.email, "provided") is user
    assert session.committed
    assert "UPDATE clinicians SET last_login_at" in str(session.statement)
    assert "gender" not in str(session.statement)


def test_clinician_dashboard_lookup_does_not_require_pending_gender_column():
    from sqlalchemy import select

    statement = select(Clinician).where(Clinician.user_id == uuid4())
    assert "clinicians.gender" not in str(statement)
    assert "clinicians.approval_status" in str(statement)
