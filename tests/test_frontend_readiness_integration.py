from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from app.core.security import create_access_token, hash_password
from app.models.clinician import Clinician, ClinicianApprovalStatus
from app.models.model import Model
from app.models.patient_clinician import PatientClinician, PatientClinicianStatus
from app.models.prediction import Prediction
from app.models.user import User, UserRole


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def register_and_login(client, monkeypatch, suffix="frontend"):
    from app.services import registration_verification
    sent = []
    monkeypatch.setattr(registration_verification, "_send_code", lambda email, code: sent.append((email, code)))
    email = f"{suffix}-{uuid4()}@example.com"
    payload = {"email": email, "password": "SyntheticPass123!", "first_name": "Synthetic",
               "last_name": "Patient", "date_of_birth": "1980-01-01", "gender": "female"}
    assert client.post("/auth/register", json=payload).status_code == 202
    assert client.post("/auth/register/verify", json={"email": email, "code": sent[-1][1]}).status_code == 201
    login = client.post("/auth/login", data={"username": email, "password": payload["password"]})
    assert login.status_code == 200
    return login.json()


def test_refresh_rotation_logout_and_revocation(client, monkeypatch):
    tokens = register_and_login(client, monkeypatch, "auth")
    refreshed = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    current = refreshed.json()
    assert client.get("/auth/me", headers=auth(current["access_token"])).status_code == 200
    assert client.post("/auth/logout", json={"refresh_token": current["refresh_token"]},
                       headers=auth(current["access_token"])).status_code == 204
    assert client.get("/auth/me", headers=auth(current["access_token"])).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": current["refresh_token"]}).status_code == 401


def test_historical_body_measurements_and_trends(client, monkeypatch):
    tokens = register_and_login(client, monkeypatch, "trends")
    headers = auth(tokens["access_token"])
    first = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    second = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert client.post("/health/profile", headers=headers,
                       json={"height_cm": 180, "weight_kg": 90, "waist_circumference_cm": 100,
                             "body_measurement_at": first}).status_code == 201
    assert client.put("/health/profile", headers=headers,
                      json={"weight_kg": 88, "waist_circumference_cm": 98,
                            "body_measurement_at": second}).status_code == 200
    measurements = client.get("/health/body-measurements", headers=headers)
    assert measurements.status_code == 200 and len(measurements.json()) == 2
    trends = client.get("/health/trends", headers=headers)
    assert trends.status_code == 200
    points = trends.json()["body_measurements"]
    assert points[0]["bmi"] == 27.78 and points[1]["bmi"] == 27.16


def test_report_generation_pdf_and_linked_clinician_access(client, db, monkeypatch):
    tokens = register_and_login(client, monkeypatch, "report")
    headers = auth(tokens["access_token"])
    patient = db.query(User).filter(User.email.like("report-%@example.test")).order_by(User.created_at.desc()).first().patient
    model = Model(name="Synthetic report model", version="test", prediction_target="diabetes",
                  algorithm="LogisticRegression", dataset_name="synthetic", model_path="synthetic", is_active=False)
    db.add(model); db.flush()
    prediction = Prediction(patient_id=patient.id, model_id=model.id, prediction_target="diabetes",
                            risk_score=0.4, risk_classification="standard", predicted_at=datetime.now(timezone.utc),
                            input_data={"model_version": "test", "decision_threshold": 0.5,
                                        "features": {"age": 46, "bmi": 27.16},
                                        "sources": {"bmi": {"updated_at": datetime.now(timezone.utc).isoformat()}}})
    db.add(prediction); db.commit()
    created = client.post("/reports", headers=headers, json={"prediction_id": str(prediction.id)})
    assert created.status_code == 201
    report_id = created.json()["id"]
    pdf = client.get(f"/reports/{report_id}/pdf", headers=headers)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF-")

    clinician_user = User(email=f"clinician-{uuid4()}@example.test", password_hash=hash_password("SyntheticPass123!"),
                           role=UserRole.CLINICIAN, is_active=True)
    db.add(clinician_user); db.flush()
    clinician = Clinician(user_id=clinician_user.id, risk_sense_id=f"RS-CLN-{str(uuid4().int)[:5]}",
                           approval_status=ClinicianApprovalStatus.APPROVED, first_name="Linked", last_name="Clinician")
    db.add(clinician); db.flush()
    db.add(PatientClinician(patient_id=patient.id, clinician_id=clinician.id, status=PatientClinicianStatus.ACTIVE))
    db.commit()
    clinician_headers = auth(create_access_token(str(clinician_user.id), clinician_user.role.value))
    assert client.get(f"/reports/{report_id}", headers=clinician_headers).status_code == 200
    db.query(PatientClinician).filter_by(patient_id=patient.id, clinician_id=clinician.id).update({"status": PatientClinicianStatus.INACTIVE})
    db.commit()
    assert client.get(f"/reports/{report_id}", headers=clinician_headers).status_code == 404


def test_patient_clinician_endpoint_and_admin_status(client, db, monkeypatch):
    tokens = register_and_login(client, monkeypatch, "relationship")
    headers = auth(tokens["access_token"])
    patient = db.query(User).filter(User.email.like("relationship-%@example.test")).order_by(User.created_at.desc()).first().patient
    assert client.get("/patients/me/clinician", headers=headers).status_code == 404
    admin = User(email=f"admin-{uuid4()}@example.test", password_hash="unused", role=UserRole.ADMIN, is_active=True)
    db.add(admin); db.commit()
    response = client.get("/admin/drug-assistant/status", headers=auth(create_access_token(str(admin.id), "admin")))
    assert response.status_code == 200 and response.json()["catalogue_medication_count"] == 208
