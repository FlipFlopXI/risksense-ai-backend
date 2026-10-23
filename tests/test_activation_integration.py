from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.core.config import settings
from app.models.activation_session import ActivationSession
from app.models.clinician import Clinician, ClinicianApprovalStatus
from app.models.patient import Patient
from app.models.user import User, UserRole


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def user(db, role, suffix):
    row = User(email=f"{suffix}-{uuid4()}@example.test", password_hash=hash_password("SafeTestPassword123!"), role=role, is_active=True)
    db.add(row)
    db.flush()
    if role == UserRole.PATIENT:
        db.add(Patient(user_id=row.id, first_name="Test", last_name="Patient"))
        db.flush()
    return row, create_access_token(str(row.id), role.value)


def clinician(db, approved=True):
    owner, _ = user(db, UserRole.CLINICIAN, "activation-clinician")
    row = Clinician(user_id=owner.id, risk_sense_id=f"RS-CLN-{uuid4().int % 100000:05d}", first_name="Test", last_name="Clinician", approval_status=ClinicianApprovalStatus.APPROVED if approved else ClinicianApprovalStatus.PENDING, approved_at=datetime.now(timezone.utc) if approved else None)
    db.add(row)
    db.commit()
    return row


def handoff(client, token):
    response = client.post("/api/v1/access/activation-session", headers=auth(token))
    assert response.status_code == 200, response.text
    return parse_qs(urlparse(response.json()["activation_url"]).fragment)["token"][0]


def exchange(client, raw):
    response = client.post("/api/v1/access/activation-session/exchange", json={"token": raw})
    assert response.status_code == 200, response.text
    return response.json()["activation_credential"]


def test_patient_demo_activation_is_scoped_atomic_and_idempotent(client, db, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_ACTIVATION_ENABLED", True)
    patient, token = user(db, UserRole.PATIENT, "activation-patient")
    doctor = clinician(db)
    assert client.get("/api/v1/access/status", headers=auth(token)).json()["active"] is False
    raw = handoff(client, token)
    row = db.scalar(select(ActivationSession).where(ActivationSession.patient_id == patient.patient.id))
    assert row and raw != row.handoff_hash and len(row.handoff_hash) == 64
    credential = exchange(client, raw)
    assert client.post("/api/v1/access/activation-session/exchange", json={"token": raw}).status_code == 401
    assert client.get("/health/profile", headers=auth(credential)).status_code == 401
    assert client.get(f"/api/v1/access/activation/clinicians/lookup/{doctor.risk_sense_id}", headers=auth(credential)).status_code == 200
    payload = {"method": "subscription", "plan": "free", "clinician_risk_sense_id": doctor.risk_sense_id}
    first = client.post("/api/v1/access/activation/complete", headers=auth(credential), json=payload)
    assert first.status_code == 200, first.text
    assert first.json() == {"active": True, "status": "active", "access_method": "subscription", "clinician_linked": True}
    assert client.post("/api/v1/access/activation/complete", headers=auth(credential), json=payload).status_code == 200
    assert client.get("/api/v1/access/status", headers=auth(token)).json()["active"] is True
    assert client.post("/api/v1/access/mock/subscription/complete", headers=auth(token), json={"patient_id": str(patient.patient.id)}).status_code == 403


def test_activation_rejects_invalid_expired_revoked_and_missing_clinician(client, db, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_ACTIVATION_ENABLED", True)
    patient, token = user(db, UserRole.PATIENT, "activation-negative")
    assert client.post("/api/v1/access/activation-session").status_code == 401
    _, clinician_token = user(db, UserRole.CLINICIAN, "activation-role")
    assert client.post("/api/v1/access/activation-session", headers=auth(clinician_token)).status_code == 403
    assert client.post("/api/v1/access/activation-session/exchange", json={"token": "x" * 64}).status_code == 401
    raw = handoff(client, token)
    row = db.scalar(select(ActivationSession).where(ActivationSession.patient_id == patient.patient.id))
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert client.post("/api/v1/access/activation-session/exchange", json={"token": raw}).status_code == 401
    raw = handoff(client, token)
    row = db.scalar(select(ActivationSession).where(ActivationSession.patient_id == patient.patient.id, ActivationSession.revoked_at.is_(None)))
    row.revoked_at = datetime.now(timezone.utc)
    db.commit()
    assert client.post("/api/v1/access/activation-session/exchange", json={"token": raw}).status_code == 401
    credential = exchange(client, handoff(client, token))
    assert client.post("/api/v1/access/activation/complete", headers=auth(credential), json={"method": "subscription", "plan": "free", "clinician_risk_sense_id": "RS-CLN-99999"}).status_code == 404
    assert client.post("/api/v1/access/activation/complete", headers=auth(credential), json={"method": "subscription", "clinician_risk_sense_id": "RS-CLN-99999"}).status_code == 422


def test_insurance_is_patient_scoped_and_unapproved_clinician_fails(client, db, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_ACTIVATION_ENABLED", True)
    patient_a, token_a = user(db, UserRole.PATIENT, "activation-a")
    patient_b, token_b = user(db, UserRole.PATIENT, "activation-b")
    pending_doctor = clinician(db, approved=False)
    approved_doctor = clinician(db)
    credential = exchange(client, handoff(client, token_a))
    body = {"method": "insurance", "provider_name": "Demo Insurer", "clinician_risk_sense_id": pending_doctor.risk_sense_id}
    assert client.post("/api/v1/access/activation/complete", headers=auth(credential), json=body).status_code == 404
    body["clinician_risk_sense_id"] = approved_doctor.risk_sense_id
    body["patient_id"] = str(patient_b.patient.id)
    assert client.post("/api/v1/access/activation/complete", headers=auth(credential), json=body).status_code == 422
    del body["patient_id"]
    assert client.post("/api/v1/access/activation/complete", headers=auth(credential), json=body).status_code == 200
    assert client.get("/api/v1/access/status", headers=auth(token_a)).json()["active"] is True
    assert client.get("/api/v1/access/status", headers=auth(token_b)).json()["active"] is False


def test_scoped_credential_expires_and_revocation_blocks_use(client, db, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_ACTIVATION_ENABLED", True)
    patient, token = user(db, UserRole.PATIENT, "activation-scope")
    credential = exchange(client, handoff(client, token))
    row = db.scalar(select(ActivationSession).where(ActivationSession.patient_id == patient.patient.id))
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/v1/access/activation/context", headers=auth(credential)).status_code == 401
    credential = exchange(client, handoff(client, token))
    row = db.scalar(select(ActivationSession).where(ActivationSession.patient_id == patient.patient.id, ActivationSession.revoked_at.is_(None)))
    row.revoked_at = datetime.now(timezone.utc)
    db.commit()
    assert client.get("/api/v1/access/activation/context", headers=auth(credential)).status_code == 401
