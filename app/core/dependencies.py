from collections.abc import Callable, Generator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.database import get_db
from app.models.user import User, UserRole
from app.services.auth_service import get_user_by_id
from app.models.patient import Patient
from app.services.entitlement_service import get_effective_entitlement
from app.services.audit_service import record_auth_event_best_effort


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)


def get_database() -> Generator[Session, None, None]:
    yield from get_db()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_database),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")

        if not subject:
            raise credentials_exception

        user_id = UUID(subject)

    except (InvalidTokenError, ValueError, TypeError):
        record_auth_event_best_effort(db, "INVALID_TOKEN", None, "failure")
        raise credentials_exception from None

    user = get_user_by_id(db, user_id)

    if not user:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_role(*allowed_roles: UserRole) -> Callable:
    def role_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_database),
    ) -> User:
        if current_user.role not in allowed_roles:
            record_auth_event_best_effort(db, "UNAUTHORIZED_ACCESS_ATTEMPT", current_user.id, "failure")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        return current_user

    return role_checker


def require_active_entitlement(
    current_user: User = Depends(require_role(UserRole.PATIENT)),
    db: Session = Depends(get_database),
):
    patient = db.scalar(select(Patient).where(Patient.user_id == current_user.id))
    if patient is None or get_effective_entitlement(db, patient.id) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="An active access entitlement is required.")
    return patient
