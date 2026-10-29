"""Email verification before a patient account is persisted."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.services.email_templates import EmailContent, registration_code_email
from app.models.patient import Patient
from app.models.pending_registration import PendingRegistration
from app.models.user import User, UserRole
from app.schemas.auth import UserRegisterRequest
from app.services.audit_service import add_audit_event


class RegistrationRejected(Exception):
    def __init__(self, message: str, status_code: int):
        self.message = message
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _code_hash(pending_id, code: str) -> str:
    if not settings.JWT_SECRET_KEY:
        raise RegistrationRejected("Email verification is not configured.", 503)
    return hmac.new(settings.JWT_SECRET_KEY.encode(), f"{pending_id}:{code}".encode(), hashlib.sha256).hexdigest()


def send_transactional_email(email: str, subject: str, body: str) -> None:
    if not settings.BREVO_API_KEY or not settings.BREVO_SENDER_EMAIL:
        raise RegistrationRejected("Email verification is not configured.", 503)
    try:
        payload = {
            "sender": {"email": settings.BREVO_SENDER_EMAIL, "name": settings.BREVO_SENDER_NAME},
            "to": [{"email": email}],
            "subject": subject,
            "textContent": str(body),
        }
        if isinstance(body, EmailContent):
            payload["htmlContent"] = body.html
        with httpx.Client(timeout=10) as client:
            response = client.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
                json=payload,
            )
        response.raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        raise RegistrationRejected("We could not send a verification email. Please try again later.", 503) from exc


def _send_code(email: str, code: str) -> None:
    send_transactional_email(
        email,
        "Your RiskSense AI verification code",
        registration_code_email(code),
    )


def begin(db: Session, request: UserRegisterRequest) -> PendingRegistration:
    if not settings.BREVO_API_KEY or not settings.BREVO_SENDER_EMAIL or not settings.JWT_SECRET_KEY:
        raise RegistrationRejected("Email verification is not configured.", 503)
    email = str(request.email).strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise RegistrationRejected("A user with this email already exists.", 409)
    now = _now()
    pending = db.scalar(select(PendingRegistration).where(PendingRegistration.email == email).with_for_update())
    if pending and pending.resend_at > now:
        raise RegistrationRejected("Please wait one minute before requesting another code.", 429)
    code = f"{secrets.randbelow(1_000_000):06d}"
    if pending is None:
        pending = PendingRegistration(id=uuid4(), email=email)
        db.add(pending)
    pending.password_hash = hash_password(request.password)
    pending.first_name = request.first_name.strip()
    pending.last_name = request.last_name.strip()
    pending.date_of_birth = request.date_of_birth
    pending.gender = request.gender
    pending.code_hash = _code_hash(pending.id, code)
    pending.attempts = 0
    pending.expires_at = now + timedelta(minutes=10)
    pending.resend_at = now + timedelta(minutes=1)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise RegistrationRejected("This email is already being registered. Please try again.", 409) from None
    _send_code(email, code)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise RegistrationRejected("This email is already being registered. Please try again.", 409) from None
    return pending


def resend(db: Session, email: str) -> PendingRegistration:
    pending = db.scalar(select(PendingRegistration).where(PendingRegistration.email == email.strip().lower()).with_for_update())
    if pending is None:
        raise RegistrationRejected("No pending registration was found. Please register again.", 404)
    now = _now()
    if pending.resend_at > now:
        raise RegistrationRejected("Please wait one minute before requesting another code.", 429)
    code = f"{secrets.randbelow(1_000_000):06d}"
    pending.code_hash = _code_hash(pending.id, code)
    pending.attempts = 0
    pending.expires_at = now + timedelta(minutes=10)
    pending.resend_at = now + timedelta(minutes=1)
    _send_code(pending.email, code)
    db.commit()
    return pending


def verify(db: Session, email: str, code: str) -> User:
    pending = db.scalar(select(PendingRegistration).where(PendingRegistration.email == email.strip().lower()).with_for_update())
    now = _now()
    if pending is None or pending.expires_at <= now or pending.attempts >= 5:
        raise RegistrationRejected("The code is invalid or expired. Request a new code.", 400)
    if not hmac.compare_digest(pending.code_hash, _code_hash(pending.id, code)):
        pending.attempts += 1
        db.commit()
        raise RegistrationRejected("The code is invalid or expired. Request a new code.", 400)
    try:
        user = User(email=pending.email, password_hash=pending.password_hash,
                    role=UserRole.PATIENT, is_active=True)
        db.add(user)
        db.flush()
        patient = Patient(user_id=user.id, first_name=pending.first_name,
                          last_name=pending.last_name, date_of_birth=pending.date_of_birth,
                          gender=pending.gender)
        db.add(patient)
        db.flush()
        add_audit_event(db, "REGISTER", user_id=user.id, resource_type="patient", resource_id=str(patient.id))
        db.delete(pending)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise RegistrationRejected("An account with this email already exists.", 409) from None
    db.refresh(user)
    return user
