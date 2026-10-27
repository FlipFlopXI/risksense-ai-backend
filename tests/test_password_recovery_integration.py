from datetime import datetime, timedelta, timezone
import re
from uuid import uuid4

from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.models.audit import AuditLog
from app.models.auth_session import AuthSession
from app.models.patient import Patient
from app.models.user import User, UserRole
from app.services import password_recovery_service


def _patient(db, email: str):
    user = User(email=email, password_hash=hash_password("OriginalPass123!"),
                role=UserRole.PATIENT, is_active=True)
    db.add(user)
    db.flush()
    db.add(Patient(user_id=user.id, first_name="Sample", last_name="Patient"))
    db.flush()
    return user


def test_password_recovery_requires_email_code_and_revokes_sessions(client, db, monkeypatch):
    sent = []
    monkeypatch.setattr(password_recovery_service, "_send", lambda email, subject, body: sent.append((email, subject, body)))
    user = _patient(db, "password.recovery@example.com")
    session = AuthSession(id=uuid4(), user_id=user.id, refresh_jti_hash="a" * 64,
                          expires_at=datetime.now(timezone.utc) + timedelta(days=1))
    db.add(session)
    db.flush()

    start = client.post("/auth/password-recovery/start", json={"email": user.email})
    assert start.status_code == 202
    assert "password" not in start.json()
    assert len(sent) == 1
    code = re.search(r"\b\d{6}\b", sent[0][2]).group()
    assert client.post("/auth/password-recovery/complete", json={"email": user.email, "code": "999999" if code != "999999" else "000000"}).status_code == 400
    assert verify_password("OriginalPass123!", user.password_hash)
    assert session.revoked_at is None

    completed = client.post("/auth/password-recovery/complete", json={"email": user.email, "code": code})
    assert completed.status_code == 204
    assert len(sent) == 2
    temporary = re.search(r"temporary RiskSense AI password is: (\S+)", sent[1][2]).group(1)
    assert temporary.startswith("Samp")
    assert len(temporary) >= 20
    assert re.search(r"\d", temporary) and re.search(r"[^A-Za-z0-9]", temporary)
    assert verify_password(temporary, user.password_hash)
    assert not verify_password("OriginalPass123!", user.password_hash)
    db.refresh(session)
    assert session.revoked_at is not None
    assert client.post("/auth/password-recovery/complete", json={"email": user.email, "code": code}).status_code == 400
    audit = list(db.scalars(select(AuditLog).where(AuditLog.user_id == user.id)).all())
    assert any(row.action == "PASSWORD_RESET" for row in audit)
    assert all(temporary not in str(row.details) for row in audit)


def test_password_recovery_is_generic_for_unknown_email_and_rolls_back_failed_delivery(client, db, monkeypatch):
    sent = []
    monkeypatch.setattr(password_recovery_service, "_send", lambda email, subject, body: sent.append((email, subject, body)))
    unknown = client.post("/auth/password-recovery/start", json={"email": "unknown.person@example.com"})
    assert unknown.status_code == 202
    assert len(sent) == 0

    user = _patient(db, "delivery.failure@example.com")
    assert client.post("/auth/password-recovery/start", json={"email": user.email}).status_code == 202
    code = re.search(r"\b\d{6}\b", sent[0][2]).group()

    def fail_delivery(email, subject, body):
        raise password_recovery_service.RecoveryRejected("We could not send the email.", 503)

    monkeypatch.setattr(password_recovery_service, "_send", fail_delivery)
    assert client.post("/auth/password-recovery/complete", json={"email": user.email, "code": code}).status_code == 503
    db.refresh(user)
    assert verify_password("OriginalPass123!", user.password_hash)
