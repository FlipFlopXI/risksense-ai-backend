from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.ml.heart_disease import runtime
from app.models.audit import AuditLog
from app.models.clinician import ClinicianApprovalStatus
from app.models.lab_result import LabResult, LabTestType
from app.models.model import Model
from app.models.patient_clinician import PatientClinician, PatientClinicianStatus
from app.models.prediction import Prediction
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import UserRole
from app.models.vital import Vital
from app.services import risk_analysis_service
from app.services.verification_service import staged_activate_subscription
from test_security_integration import _auth, _clinician, _patient, _token, _user


ROUTE = "/api/v1/risk-analysis"
ACTIVATE = "/api/v1/admin/models/heart-disease/activate"


@pytest.fixture
def scenario(client, db):
    admin = _user(db, UserRole.ADMIN, "heart.admin@example.com")
    user, patient = _patient(db, "heart.patient@example.com")
    clinician_user, clinician = _clinician(db, "heart.clinician@example.com", "RS-CLN-20001",
                                          ClinicianApprovalStatus.APPROVED)
    patient.date_of_birth = date(datetime.now(timezone.utc).year - 50, 1, 1)
    patient.gender = "male"
    subscription = Subscription(patient_id=patient.id, plan="premium", status=SubscriptionStatus.PENDING,
                                requested_clinician_risk_sense_id=clinician.risk_sense_id)
    db.add(subscription)
    db.flush()
    entitlement = staged_activate_subscription(db, patient, subscription, clinician.risk_sense_id, admin.id)
    headers = _auth(_token(user))
    activation = client.post(ACTIVATE, headers=_auth(_token(admin)))
    assert activation.status_code == 200, activation.text
    measured_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    vital = client.post("/api/v1/health/vitals/", headers=headers, json={
        "blood_pressure_systolic": 130, "blood_pressure_diastolic": 80, "recorded_at": measured_at,
    })
    assert vital.status_code == 201
    labs = {}
    for test_type, value in (("total_cholesterol", 200), ("fasting_glucose", 120)):
        response = client.post("/api/v1/health/labs/", headers=headers, json={
            "test_type": test_type, "value": value, "unit": "mg/dL", "source": "synthetic integration test",
            "measured_at": measured_at,
        })
        assert response.status_code == 201
        labs[test_type] = db.get(LabResult, UUID(response.json()["id"]))
    return dict(admin=admin, user=user, patient=patient, clinician_user=clinician_user, clinician=clinician,
                entitlement=entitlement, headers=headers, labs=labs, vital=db.get(Vital, UUID(vital.json()["id"])))


def test_real_end_to_end_patient_prediction_history_and_audit(client, db, scenario):
    response = client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["prediction_target"] == "heart_disease"
    assert body["model_version"] == "1.0.0"
    assert body["decision_threshold"] == runtime.load_model().threshold
    assert 0 <= body["risk_score"] <= 1
    assert body["risk_classification"] == ("elevated" if body["risk_score"] >= body["decision_threshold"] else "not_elevated")
    assert body["explanation"] == runtime.DISCLAIMER
    db.expire_all()
    prediction = db.get(Prediction, UUID(body["id"]))
    assert prediction.model_id == risk_analysis_service.MODEL_ID
    assert prediction.input_data["features"] == {
        "age": 50, "sex": 1, "systolic_bp": 130, "total_cholesterol": 200, "fasting_blood_sugar_high": 0,
    }
    assert prediction.input_data["feature_order"] == list(runtime.FEATURE_ORDER)
    assert prediction.input_data["artifact_sha256"] == runtime.ARTIFACT_SHA256
    sources = prediction.input_data["sources"]
    assert sources["fasting_glucose"]["id"] == str(scenario["labs"]["fasting_glucose"].id)
    assert sources["fasting_glucose"]["measured_at"]
    assert sources["fasting_glucose"]["unit"] == "mg/dL"
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "PREDICTION_CREATED"))
    assert audit.resource_id == body["id"]
    assert audit.details == {"target": "heart_disease", "model_id": str(prediction.model_id)}
    history = client.get("/api/v1/predictions", headers=scenario["headers"])
    assert history.status_code == 200
    assert history.json()[0]["id"] == body["id"]
    # Historical runtime metadata is a snapshot, not a live registry lookup.
    prediction.model.version = "changed-later"
    db.commit()
    fetched = client.get(f"/api/v1/predictions/{prediction.id}", headers=scenario["headers"])
    assert fetched.json()["model_version"] == "1.0.0"


def test_unauthenticated_request_rejected(client):
    assert client.post(ROUTE, json={"model": "heart_disease"}).status_code == 401


def test_cross_patient_analysis_and_history_denied(client, db, scenario):
    _, other = _patient(db, "other.heart@example.com")
    db.commit()
    denied = client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease", "patient_id": str(other.id)})
    assert denied.status_code == 404
    response = client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease"})
    other_headers = _auth(_token(other.user))
    assert client.get(f"/api/v1/predictions/{response.json()['id']}", headers=other_headers).status_code == 404


def test_approved_linked_clinician_and_unlinked_denial(client, db, scenario):
    headers = _auth(_token(scenario["clinician_user"]))
    payload = {"model": "heart_disease", "patient_id": str(scenario["patient"].id)}
    assert client.post(ROUTE, headers=headers, json=payload).status_code == 201
    link = db.scalar(select(PatientClinician).where(PatientClinician.patient_id == scenario["patient"].id))
    link.status = PatientClinicianStatus.INACTIVE
    db.commit()
    assert client.post(ROUTE, headers=headers, json=payload).status_code == 404
    scenario["clinician"].approval_status = ClinicianApprovalStatus.PENDING
    db.commit()
    assert client.post(ROUTE, headers=headers, json=payload).status_code == 403


def test_patient_needs_entitlement_and_active_account(client, db, scenario):
    scenario["entitlement"].verified_at = datetime.now(timezone.utc) - timedelta(days=2)
    scenario["entitlement"].expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    assert client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease"}).status_code == 403
    scenario["user"].is_active = False
    db.commit()
    assert client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease"}).status_code == 401


@pytest.mark.parametrize("field", ["total_cholesterol", "fasting_glucose", "systolic_bp", "age", "sex"])
def test_missing_stored_fields_do_not_infer_or_persist(client, db, scenario, monkeypatch, field):
    if field in scenario["labs"]:
        db.delete(scenario["labs"][field])
    elif field == "systolic_bp":
        scenario["vital"].blood_pressure_systolic = None
    elif field == "age":
        scenario["patient"].date_of_birth = None
    else:
        scenario["patient"].gender = None
    db.commit()
    infer = Mock(side_effect=AssertionError("Inference must not run"))
    monkeypatch.setattr(runtime, "predict", infer)
    response = client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease"})
    assert response.status_code == 422
    assert response.json()["detail"]["status"] == "insufficient_data"
    assert response.json()["detail"]["missing_fields"] == [field]
    infer.assert_not_called()
    assert db.scalar(select(func.count(Prediction.id))) == 0


def test_random_glucose_and_ldl_are_not_substitutes(client, db, scenario):
    scenario["labs"]["fasting_glucose"].test_type = LabTestType.GLUCOSE
    scenario["labs"]["total_cholesterol"].test_type = LabTestType.LDL
    db.commit()
    response = client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease"})
    assert response.status_code == 422
    assert response.json()["detail"]["missing_fields"] == ["total_cholesterol", "fasting_glucose"]


def test_latest_measurements_units_and_unrelated_vitals(client, db, scenario):
    now = datetime.now(timezone.utc)
    newer = LabResult(patient_id=scenario["patient"].id, test_type="total_cholesterol", value=5,
                     unit="mmol/L", source="synthetic newer test", measured_at=now - timedelta(minutes=1))
    scenario["labs"]["fasting_glucose"].value = 7
    scenario["labs"]["fasting_glucose"].unit = "mmol/L"
    db.add_all([newer, Vital(patient_id=scenario["patient"].id, heart_rate=70, recorded_at=now)])
    db.commit()
    response = client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease"})
    assert response.status_code == 201
    record = db.get(Prediction, UUID(response.json()["id"]))
    assert record.input_data["features"]["total_cholesterol"] == pytest.approx(193.35)
    assert record.input_data["features"]["fasting_blood_sugar_high"] == 1
    assert record.input_data["features"]["systolic_bp"] == 130
    assert record.input_data["sources"]["total_cholesterol"]["id"] == str(newer.id)


@pytest.mark.parametrize("invalid", ["sex", "unit", "future_birth"])
def test_invalid_stored_values_rejected(client, db, scenario, invalid):
    if invalid == "sex":
        scenario["patient"].gender = "unknown"
    elif invalid == "unit":
        scenario["labs"]["total_cholesterol"].unit = "unspecified"
    else:
        scenario["patient"].date_of_birth = date.today() + timedelta(days=1)
    db.commit()
    response = client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease"})
    assert response.status_code == 422
    assert response.json()["detail"]["status"] == "invalid_data"


def test_admin_activation_idempotent_patient_denied_and_model_suspension(client, db, scenario):
    assert client.post(ACTIVATE, headers=scenario["headers"]).status_code == 403
    headers = _auth(_token(scenario["admin"]))
    assert client.post(ACTIVATE, headers=headers).status_code == 200
    assert db.scalar(select(func.count(Model.id)).where(Model.prediction_target == "heart_disease")) == 1
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "MODEL_ACTIVATED"))
    assert client.post(ROUTE, headers=headers, json={"model": "heart_disease"}).status_code == 403
    assert client.post(f"/api/v1/admin/models/{risk_analysis_service.MODEL_ID}/suspend", headers=headers).status_code == 200
    response = client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease"})
    assert response.status_code == 503 and response.json()["detail"]["code"] == "MODEL_INACTIVE"


def test_arbitrary_model_paths_and_features_rejected(client, scenario):
    for extra in ({"model_path": "untrusted.pkl"}, {"fasting_blood_sugar_high": 0}, {"bmi": 25}):
        response = client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease", **extra})
        assert response.status_code == 422


def test_inference_failure_is_sanitized_and_nothing_persisted(client, db, scenario, monkeypatch):
    pipeline = runtime.load_model().pipeline
    monkeypatch.setattr(pipeline, "predict_proba", Mock(side_effect=RuntimeError("internal/path/secret")))
    response = client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease"})
    assert response.status_code == 503
    assert "secret" not in response.text and "Traceback" not in response.text
    assert db.scalar(select(func.count(Prediction.id))) == 0


def test_audit_failure_rolls_back_prediction(client, db, scenario, monkeypatch):
    monkeypatch.setattr(risk_analysis_service, "add_audit_event", Mock(side_effect=SQLAlchemyError("private SQL")))
    response = client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease"})
    assert response.status_code == 503 and "private SQL" not in response.text
    assert db.scalar(select(func.count(Prediction.id))) == 0


def test_ambiguous_registry_fails_closed(client, db, scenario):
    db.add(Model(id=uuid4(), name="Other", version="other", prediction_target="heart_disease",
                 algorithm="LogisticRegression", is_active=True))
    db.commit()
    response = client.post(ROUTE, headers=scenario["headers"], json={"model": "heart_disease"})
    assert response.status_code == 503
