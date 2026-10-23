from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.ml.diabetes import runtime
from app.models.audit import AuditLog
from app.models.health_profile import HealthProfile
from app.models.model import Model
from app.models.prediction import Prediction
from app.models.vital import Vital
from app.models.patient_clinician import PatientClinician, PatientClinicianStatus
from app.models.clinician import ClinicianApprovalStatus
from app.models.access_entitlement import EntitlementStatus
from app.services import diabetes_service, risk_analysis_service
from test_heart_disease_integration import scenario
from test_security_integration import _auth, _token, _patient

ROUTE = "/risk-analysis"
ACTIVATE = "/admin/models/diabetes/activate"


@pytest.fixture
def diabetes(client, db, scenario):
    response = client.post("/health/profile", headers=scenario["headers"], json={
        "height_cm": 180, "weight_kg": 97.2, "waist_circumference_cm": 100,
    })
    assert response.status_code == 201, response.text
    scenario["profile"] = db.get(HealthProfile, UUID(response.json()["id"]))
    assert client.post(ACTIVATE, headers=_auth(_token(scenario["admin"]))).status_code == 200
    return scenario


def infer(client, diabetes):
    return client.post(ROUTE, headers=diabetes["headers"], json={"model": "diabetes"})


def test_prediction_snapshot_audit_and_heart_coexistence(client, db, diabetes):
    response = infer(client, diabetes)
    assert response.status_code == 201, response.text
    body = response.json()
    record = db.get(Prediction, UUID(body["id"]))
    assert record.model_id == diabetes_service.MODEL_ID
    assert body["prediction_target"] == "diabetes_risk"
    assert body["model_version"] == "1.0.0" and body["decision_threshold"] == 0.455
    assert body["risk_classification"] == ("elevated" if body["risk_score"] >= 0.455 else "standard")
    snapshot = record.input_data
    assert snapshot["features"] == dict(age=50, sex=1, bmi=30, waist_circumference=100, systolic_bp=130, diastolic_bp=80)
    assert snapshot["feature_order"] == list(runtime.FEATURE_ORDER)
    assert snapshot["artifact_sha256"] == runtime.ARTIFACT_SHA256
    assert snapshot["sources"]["bmi"]["id"] == str(diabetes["profile"].id)
    assert snapshot["sources"]["waist_circumference"]["unit"] == "cm"
    assert snapshot["sources"]["systolic_bp"] == snapshot["sources"]["diastolic_bp"]
    assert snapshot["sources"]["systolic_bp"]["id"] == str(diabetes["vital"].id)
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "PREDICTION_CREATED", AuditLog.resource_id == body["id"]))
    assert audit.details["target"] == "diabetes_risk"
    assert client.post(ROUTE, headers=diabetes["headers"], json={"model": "heart_disease"}).status_code == 201
    assert db.scalar(select(func.count(Model.id)).where(Model.is_active.is_(True))) == 2


@pytest.mark.parametrize("field", ["age", "sex", "bmi", "waist_circumference", "blood_pressure"])
def test_missing_data_never_infers_or_persists(client, db, diabetes, monkeypatch, field):
    if field == "age":
        diabetes["patient"].date_of_birth = None
    elif field == "sex":
        diabetes["patient"].gender = None
    elif field == "bmi":
        diabetes["profile"].height_cm = None
    elif field == "waist_circumference":
        diabetes["profile"].waist_circumference_cm = None
    else:
        diabetes["vital"].blood_pressure_diastolic = None
    db.commit()
    prediction = Mock(side_effect=AssertionError("must not infer"))
    monkeypatch.setattr(runtime, "predict", prediction)
    response = infer(client, diabetes)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "MODEL_INPUT_INCOMPLETE" and detail["status"] == "insufficient_data"
    assert detail["missing_fields"] == (["systolic_bp", "diastolic_bp"] if field == "blood_pressure" else [field])
    prediction.assert_not_called()
    assert db.scalar(select(func.count(Prediction.id))) == 0
    assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "PREDICTION_CREATED")) == 0


@pytest.mark.parametrize("invalid", ["underage", "sex", "zero_height"])
def test_invalid_inputs(client, db, diabetes, invalid):
    if invalid == "underage":
        diabetes["patient"].date_of_birth = date(datetime.now(timezone.utc).year - 17, 1, 1)
    elif invalid == "sex":
        diabetes["patient"].gender = "unknown"
    else:
        diabetes["profile"].height_cm = 0
    db.commit()
    response = infer(client, diabetes)
    assert response.status_code == 422
    if invalid == "underage":
        assert "under 18" in response.json()["detail"]["message"]
    assert db.scalar(select(func.count(Prediction.id))) == 0


def test_latest_complete_bp_pair(client, db, diabetes):
    now = datetime.now(timezone.utc)
    pair = Vital(patient_id=diabetes["patient"].id, blood_pressure_systolic=140, blood_pressure_diastolic=85,
                 recorded_at=now - timedelta(minutes=5))
    db.add_all([pair, Vital(patient_id=diabetes["patient"].id, blood_pressure_systolic=150, recorded_at=now),
                Vital(patient_id=diabetes["patient"].id, blood_pressure_systolic=160, blood_pressure_diastolic=90,
                      recorded_at=now + timedelta(days=1))])
    db.commit()
    response = infer(client, diabetes)
    assert response.status_code == 201
    record = db.get(Prediction, UUID(response.json()["id"]))
    assert record.input_data["features"]["systolic_bp"] == 140
    assert record.input_data["features"]["diastolic_bp"] == 85
    assert record.input_data["sources"]["systolic_bp"]["id"] == str(pair.id)


def test_auth_ownership_and_admin_only_activation(client, db, diabetes):
    assert client.post(ROUTE, json={"model": "diabetes"}).status_code == 401
    assert client.post(ACTIVATE, headers=diabetes["headers"]).status_code == 403
    admin = _auth(_token(diabetes["admin"]))
    assert client.post(ACTIVATE, headers=admin).status_code == 200
    assert db.scalar(select(func.count(Model.id)).where(Model.prediction_target == runtime.TARGET)) == 1
    assert client.post(ROUTE, headers=admin, json={"model": "diabetes"}).status_code == 403
    _, other = _patient(db, "other.diabetes@example.test")
    db.commit()
    assert client.post(ROUTE, headers=diabetes["headers"], json={"model": "diabetes", "patient_id": str(other.id)}).status_code == 404
    for extra in ({"bmi": 30}, {"model_path": "other.pkl"}):
        assert client.post(ROUTE, headers=diabetes["headers"], json={"model": "diabetes", **extra}).status_code == 422


def test_clinician_link_and_approval(client, db, diabetes):
    headers = _auth(_token(diabetes["clinician_user"]))
    body = {"model": "diabetes", "patient_id": str(diabetes["patient"].id)}
    assert client.post(ROUTE, headers=headers, json=body).status_code == 201
    link = db.scalar(select(PatientClinician).where(PatientClinician.patient_id == diabetes["patient"].id))
    link.status = PatientClinicianStatus.INACTIVE
    db.commit()
    assert client.post(ROUTE, headers=headers, json=body).status_code == 404
    diabetes["clinician"].approval_status = ClinicianApprovalStatus.PENDING
    db.commit()
    assert client.post(ROUTE, headers=headers, json=body).status_code == 403


@pytest.mark.parametrize("state", ["inactive", "expired"])
def test_entitlement_required(client, db, diabetes, state):
    if state == "inactive":
        diabetes["entitlement"].status = EntitlementStatus.CANCELLED
    else:
        diabetes["entitlement"].verified_at = datetime.now(timezone.utc) - timedelta(days=2)
        diabetes["entitlement"].expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    assert infer(client, diabetes).status_code == 403


def test_inactive_model(client, db, diabetes):
    db.get(Model, diabetes_service.MODEL_ID).is_active = False
    db.commit()
    response = infer(client, diabetes)
    assert response.status_code == 503 and response.json()["detail"]["code"] == "MODEL_INACTIVE"


@pytest.mark.parametrize("failure", ["inference", "audit"])
def test_failures_atomic_and_sanitized(client, db, diabetes, monkeypatch, failure):
    if failure == "inference":
        monkeypatch.setattr(runtime.load_model().pipeline, "predict_proba", Mock(side_effect=RuntimeError("private secret")))
    else:
        monkeypatch.setattr(risk_analysis_service, "add_audit_event", Mock(side_effect=SQLAlchemyError("private secret")))
    response = infer(client, diabetes)
    assert response.status_code == 503 and "private secret" not in response.text
    assert db.scalar(select(func.count(Prediction.id))) == 0
    assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "PREDICTION_CREATED")) == 0
