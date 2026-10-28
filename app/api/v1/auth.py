from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from fastapi.security import OAuth2PasswordRequestForm
from uuid import UUID
from jwt import InvalidTokenError
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
    PasswordChangeRequest,
    AuthSessionResponse,
    RegistrationEmailRequest,
    RegistrationVerifyRequest,
    RegistrationPendingResponse,
    PasswordRecoveryRequest,
    PasswordRecoveryCompleteRequest,
    PasswordRecoveryResponse,
)
from app.services.auth_service import authenticate_user
from app.services.registration_verification import RegistrationRejected, begin, resend, verify
from app.services.password_recovery_service import RecoveryRejected, start as start_recovery, complete as complete_recovery
from app.services.audit_service import record_auth_event_best_effort
from app.models.audit import AuditLog
from app.models.user import UserRole
from app.services.session_service import RefreshRejected, issue_session, refresh_session, revoke_session
from app.services.session_service import PasswordRejected, change_password, list_active_sessions, revoke_session_by_id
from app.core.dependencies import oauth2_scheme
from app.core.security import decode_access_token


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=RegistrationPendingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def register(
    request: UserRegisterRequest,
    db: Session = Depends(get_database),
):
    try:
        pending = begin(db, request)
        return RegistrationPendingResponse(email=pending.email)
    except RegistrationRejected as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc


@router.post("/register/resend", response_model=RegistrationPendingResponse)
def resend_registration(request: RegistrationEmailRequest, db: Session = Depends(get_database)):
    try:
        pending = resend(db, str(request.email))
        return RegistrationPendingResponse(email=pending.email)
    except RegistrationRejected as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/register/verify", response_model=UserResponse, status_code=201)
def verify_registration(request: RegistrationVerifyRequest, db: Session = Depends(get_database)):
    try:
        return verify(db, str(request.email), request.code)
    except RegistrationRejected as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/password-recovery/start", response_model=PasswordRecoveryResponse, status_code=202)
def request_password_recovery(request: PasswordRecoveryRequest, db: Session = Depends(get_database)):
    try:
        start_recovery(db, str(request.email))
        return PasswordRecoveryResponse(message="If this account can be recovered, a code has been sent to its email address.")
    except RecoveryRejected as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/password-recovery/complete", status_code=204)
def finish_password_recovery(request: PasswordRecoveryCompleteRequest, db: Session = Depends(get_database)):
    try:
        complete_recovery(db, str(request.email), request.code)
    except RecoveryRejected as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    risk_sense_client: str | None = Header(default=None, alias="X-RiskSense-Client"),
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
    issued = issue_session(db, user,
                           wearable=risk_sense_client == "wearable" and user.role == UserRole.PATIENT)
    return TokenResponse.model_validate(issued)


@router.get("/wearable-presence")
def wearable_presence(current_user=Depends(get_current_user),
                      token: str = Depends(oauth2_scheme),
                      db: Session = Depends(get_database)):
    """Report whether another active session identified itself as the wearable."""
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Patient account required.")
    current_id = _current_session_id(token)
    session_ids = [row.id for row in list_active_sessions(db, current_user)
                   if row.id != current_id]
    if not session_ids:
        return {"connected": False}
    marked = db.scalar(select(AuditLog.id).where(
        AuditLog.user_id == current_user.id,
        AuditLog.action == "WEARABLE_SESSION_STARTED",
        AuditLog.resource_type == "auth_session",
        AuditLog.resource_id.in_([str(value) for value in session_ids]),
    ).limit(1))
    return {"connected": marked is not None}


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


def _current_session_id(token: str) -> UUID | None:
    try:
        raw = decode_access_token(token).get("sid")
        return UUID(raw) if raw else None
    except (InvalidTokenError, ValueError, TypeError):
        return None


@router.patch("/password", status_code=status.HTTP_204_NO_CONTENT)
def update_password(request: PasswordChangeRequest,
                    current_user=Depends(get_current_user),
                    token: str = Depends(oauth2_scheme),
                    db: Session = Depends(get_database)):
    try:
        change_password(db, current_user, request.current_password,
                        request.new_password, _current_session_id(token))
    except PasswordRejected:
        raise HTTPException(status_code=400,
                            detail="Current password is incorrect or the new password is unchanged.") from None


@router.get("/sessions", response_model=list[AuthSessionResponse])
def sessions(current_user=Depends(get_current_user),
             token: str = Depends(oauth2_scheme),
             db: Session = Depends(get_database)):
    current_id = _current_session_id(token)
    return [AuthSessionResponse(id=row.id, created_at=row.created_at,
                                last_used_at=row.last_used_at,
                                expires_at=row.expires_at,
                                is_current=row.id == current_id)
            for row in list_active_sessions(db, current_user)]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: UUID, current_user=Depends(get_current_user),
                   db: Session = Depends(get_database)):
    if not revoke_session_by_id(db, current_user, session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
