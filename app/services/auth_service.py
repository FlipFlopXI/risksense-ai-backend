from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.patient import Patient
from app.models.user import User, UserRole
from app.schemas.auth import UserRegisterRequest


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
    )

    db.add(patient)
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

    return user

