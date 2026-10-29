"""Email-challenged password recovery. No password is returned to the client."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets
import string
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.services.email_templates import recovery_code_email, replacement_password_email
from app.models.auth_session import AuthSession
from app.models.clinician import Clinician
from app.models.password_reset_challenge import PasswordResetChallenge
from app.models.patient import Patient
from app.models.user import User, UserRole
from app.services.audit_service import add_audit_event
from app.services.registration_verification import RegistrationRejected, send_transactional_email


class RecoveryRejected(Exception):
    def __init__(self, message: str, status_code: int):
        self.message = message
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(challenge_id, code: str) -> str:
    if not settings.JWT_SECRET_KEY:
        raise RecoveryRejected("Password recovery is not configured.", 503)
    return hmac.new(settings.JWT_SECRET_KEY.encode(), f"password-reset:{challenge_id}:{code}".encode(), hashlib.sha256).hexdigest()


def generate_temporary_password(name: str) -> str:
    # The recognizable fragment is never the only source of entropy.
    fragment = re.sub(r"[^A-Za-z]", "", name)[:4].capitalize() or "Risk"
    random_part = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    digits = f"{secrets.randbelow(10000):04d}"
    symbol = secrets.choice("!@#$%&*")
    return f"{fragment}{random_part}{digits}{symbol}"


def _first_name(db: Session, user: User) -> str:
    if user.role == UserRole.PATIENT:
        name = db.scalar(select(Patient.first_name).where(Patient.user_id == user.id))
    elif user.role == UserRole.CLINICIAN:
        name = db.scalar(select(Clinician.first_name).where(Clinician.user_id == user.id))
    else:
        name = user.email.split("@", 1)[0]
    return name or "Risk"


def _send(email: str, subject: str, body: str) -> None:
    try:
        send_transactional_email(email, subject, body)
    except RegistrationRejected as exc:
        raise RecoveryRejected("We could not send the email. Please try again later.", 503) from exc


def start(db: Session, email: str) -> None:
    if not settings.BREVO_API_KEY or not settings.BREVO_SENDER_EMAIL or not settings.JWT_SECRET_KEY:
        raise RecoveryRejected("Password recovery is not configured.", 503)
    user = db.scalar(select(User).where(User.email == email.strip().lower()).with_for_update())
    if user is None or not user.is_active:
        return
    now = _now()
    challenge = db.scalar(select(PasswordResetChallenge).where(
        PasswordResetChallenge.user_id == user.id).with_for_update())
    if challenge is not None and challenge.resend_at > now:
        return
    code = f"{secrets.randbelow(1_000_000):06d}"
    if challenge is None:
        challenge = PasswordResetChallenge(id=uuid4(), user_id=user.id)
        db.add(challenge)
    challenge.code_hash = _digest(challenge.id, code)
    challenge.attempts = 0
    challenge.expires_at = now + timedelta(minutes=10)
    challenge.resend_at = now + timedelta(minutes=1)
    db.flush()
    _send(user.email, "RiskSense AI password recovery code",
          recovery_code_email(code))
    add_audit_event(db, "PASSWORD_RECOVERY_CODE_SENT", user_id=user.id,
                    resource_type="user", resource_id=str(user.id))
    db.commit()


def complete(db: Session, email: str, code: str) -> None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()).with_for_update())
    if user is None or not user.is_active:
        raise RecoveryRejected("Invalid or expired recovery code.", 400)
    challenge = db.scalar(select(PasswordResetChallenge).where(
        PasswordResetChallenge.user_id == user.id).with_for_update())
    now = _now()
    if challenge is None or challenge.expires_at <= now or challenge.attempts >= 5:
        raise RecoveryRejected("Invalid or expired recovery code.", 400)
    if not hmac.compare_digest(challenge.code_hash, _digest(challenge.id, code)):
        challenge.attempts += 1
        db.commit()
        raise RecoveryRejected("Invalid or expired recovery code.", 400)
    password = generate_temporary_password(_first_name(db, user))
    password_hash = hash_password(password)
    _send(user.email, "Your RiskSense AI replacement password",
          replacement_password_email(password))
    user.password_hash = password_hash
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id,
                                        AuthSession.revoked_at.is_(None)).values(revoked_at=now))
    db.delete(challenge)
    add_audit_event(db, "PASSWORD_RESET", user_id=user.id,
                    resource_type="user", resource_id=str(user.id))
    db.commit()
