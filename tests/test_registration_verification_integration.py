from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from app.models.pending_registration import PendingRegistration
from app.models.user import User
from app.services import registration_verification


def test_email_otp_creates_patient_only_after_verification(client, db, monkeypatch):
    sent = []
    monkeypatch.setattr(registration_verification, "_send_code", lambda email, code: sent.append(code))
    payload = {"email": "otp.patient@example.com", "password": "StrongPass123!",
               "first_name": "Otp", "last_name": "Patient", "date_of_birth": "1985-02-02", "gender": "Female"}
    started = client.post("/auth/register", json=payload)
    assert started.status_code == 202
    assert started.json()["code_length"] == 6
    assert db.scalar(select(User).where(User.email == payload["email"])) is None
    assert client.post("/auth/login", data={"username": payload["email"], "password": payload["password"]}).status_code == 401
    wrong_code = "000000" if sent[-1] != "000000" else "999999"
    assert client.post("/auth/register/verify", json={"email": payload["email"], "code": wrong_code}).status_code == 400
    assert client.post("/auth/register/resend", json={"email": payload["email"]}).status_code == 429
    verified = client.post("/auth/register/verify", json={"email": payload["email"], "code": sent[-1]})
    assert verified.status_code == 201
    assert db.scalar(select(User).where(User.email == payload["email"])) is not None
    assert client.post("/auth/register/verify", json={"email": payload["email"], "code": sent[-1]}).status_code == 400
    assert client.post("/auth/login", data={"username": payload["email"], "password": payload["password"]}).status_code == 200


def test_resend_invalidates_old_code_and_expired_code_fails(client, db, monkeypatch):
    sent = []
    monkeypatch.setattr(registration_verification, "_send_code", lambda email, code: sent.append(code))
    codes = iter([123456, 654321])
    monkeypatch.setattr(registration_verification.secrets, "randbelow", lambda _: next(codes))
    email = "otp.resend@example.com"
    payload = {"email": email, "password": "StrongPass123!", "first_name": "Otp", "last_name": "Resend"}
    assert client.post("/auth/register", json=payload).status_code == 202
    pending = db.scalar(select(PendingRegistration).where(PendingRegistration.email == email))
    pending.resend_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.flush()
    assert client.post("/auth/register/resend", json={"email": email}).status_code == 200
    assert client.post("/auth/register/verify", json={"email": email, "code": sent[0]}).status_code == 400
    pending.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.flush()
    assert client.post("/auth/register/verify", json={"email": email, "code": sent[1]}).status_code == 400
    assert db.scalar(select(User).where(User.email == email)) is None
