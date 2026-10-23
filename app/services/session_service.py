from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID, uuid4

from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_refresh_token
from app.models.auth_session import AuthSession
from app.models.user import User
from app.services.audit_service import add_audit_event


class RefreshRejected(Exception):
    pass


def _digest(jti: str) -> str:
    return sha256(jti.encode("utf-8")).hexdigest()


def issue_session(db: Session, user: User) -> dict:
    session_id = uuid4()
    refresh, jti, expires = create_refresh_token(str(user.id), user.role.value, session_id)
    db.add(AuthSession(id=session_id, user_id=user.id, refresh_jti_hash=_digest(jti), expires_at=expires))
    add_audit_event(db, "AUTH_SESSION_CREATED", user_id=user.id, resource_type="auth_session", resource_id=str(session_id))
    db.commit()
    return {"access_token": create_access_token(str(user.id), user.role.value, session_id),
            "refresh_token": refresh, "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}


def refresh_session(db: Session, token: str) -> dict:
    try:
        payload = decode_refresh_token(token)
        session_id, user_id = UUID(payload["sid"]), UUID(payload["sub"])
    except (InvalidTokenError, ValueError, TypeError, KeyError):
        raise RefreshRejected from None
    row = db.scalar(select(AuthSession).where(AuthSession.id == session_id).with_for_update())
    now = datetime.now(timezone.utc)
    if (row is None or row.user_id != user_id or row.revoked_at is not None or row.expires_at <= now
            or row.refresh_jti_hash != _digest(payload["jti"]) or not row.user.is_active):
        raise RefreshRejected
    refresh, jti, expires = create_refresh_token(str(row.user.id), row.user.role.value, row.id)
    row.refresh_jti_hash, row.expires_at, row.last_used_at = _digest(jti), expires, now
    add_audit_event(db, "AUTH_SESSION_REFRESHED", user_id=row.user.id, resource_type="auth_session", resource_id=str(row.id))
    db.commit()
    return {"access_token": create_access_token(str(row.user.id), row.user.role.value, row.id),
            "refresh_token": refresh, "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}


def revoke_session(db: Session, token: str, actor: User | None = None) -> None:
    try:
        payload = decode_refresh_token(token)
        session_id, user_id = UUID(payload["sid"]), UUID(payload["sub"])
    except (InvalidTokenError, ValueError, TypeError, KeyError):
        raise RefreshRejected from None
    row = db.scalar(select(AuthSession).where(AuthSession.id == session_id).with_for_update())
    if row is None or row.user_id != user_id or row.refresh_jti_hash != _digest(payload["jti"]):
        raise RefreshRejected
    if actor is not None and actor.id != user_id:
        raise RefreshRejected
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        add_audit_event(db, "LOGOUT", user_id=user_id, resource_type="auth_session", resource_id=str(row.id))
        db.commit()
