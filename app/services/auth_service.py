from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.patient import Patient
from app.models.user import User, UserRole
from app.schemas.auth import UserRegisterRequest
from app.services.audit_service import add_audit_event


def get_user_by_email(db: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    return db.scalar(statement)


def get_user_by_id(db: Session, user_id) -> User | None:
    statement = select(User).where(User.id == user_id)
    return db.scalar(statement)


def register_patient(
    db: Session,
    request: UserRegisterRequest,
) -> User:
    email = str(request.email).strip().lower()

    existing_user = get_user_by_email(db, email)

    if existing_user:
        raise ValueError("A user with this email already exists.")

    user = User(
        email=email,
        password_hash=hash_password(request.password),
        role=UserRole.PATIENT,
        is_active=True,
    )

    db.add(user)
    db.flush()

    patient = Patient(
        user_id=user.id,
        first_name=request.first_name.strip(),
        last_name=request.last_name.strip(),
        date_of_birth=request.date_of_birth,
        gender=request.gender,
    )

    db.add(patient)
    db.flush()
    add_audit_event(db, "REGISTER", user_id=user.id, resource_type="patient", resource_id=str(patient.id))
    db.commit()

    db.refresh(user)

    return user


def authenticate_user(
    db: Session,
    email: str,
    password: str,
) -> User | None:
    email = email.strip().lower()

    user = get_user_by_email(db, email)

    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None

    if not user.is_active:
        return None

    if user.role == UserRole.CLINICIAN and user.clinician:
        user.clinician.last_login_at = datetime.now(timezone.utc)
        db.commit()

    return user

