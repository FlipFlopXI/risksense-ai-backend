from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_current_user,
    get_database,
)
from app.schemas.auth import (
    LogoutRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import (
    authenticate_user,
    register_patient,
)
from app.services.audit_service import record_auth_event_best_effort
from app.services.session_service import RefreshRejected, issue_session, refresh_session, revoke_session


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: UserRegisterRequest,
    db: Session = Depends(get_database),
):
    try:
        user = register_patient(db, request)
        return user
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_database),
):
    user = authenticate_user(
        db,
        form_data.username,
        form_data.password,
    )

    if not user:
        record_auth_event_best_effort(db, "LOGIN_FAILURE", None, "failure")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    record_auth_event_best_effort(db, "LOGIN_SUCCESS", user.id, "success")
    return TokenResponse.model_validate(issue_session(db, user))


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: RefreshTokenRequest, db: Session = Depends(get_database)):
    try:
        return TokenResponse.model_validate(refresh_session(db, request.refresh_token))
    except RefreshRejected:
        record_auth_event_best_effort(db, "REFRESH_TOKEN_REJECTED", None, "failure")
        raise HTTPException(status_code=401, detail="Invalid, expired, or revoked refresh token.",
                            headers={"WWW-Authenticate": "Bearer"}) from None


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: LogoutRequest, current_user=Depends(get_current_user), db: Session = Depends(get_database)):
    try:
        revoke_session(db, request.refresh_token, current_user)
    except RefreshRejected:
        raise HTTPException(status_code=401, detail="Invalid or revoked refresh token.") from None


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user=Depends(get_current_user),
):
    return current_user
