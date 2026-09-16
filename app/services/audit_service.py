from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def add_audit_event(
    db: Session,
    action: str,
    *,
    user_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    status: str = "success",
    details: dict | None = None,
    error_message: str | None = None,
) -> AuditLog:
    event = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        details=details,
        error_message=error_message,
    )
    db.add(event)
    return event


def record_auth_event_best_effort(db: Session, action: str, user_id: UUID | None, status: str) -> None:
    try:
        add_audit_event(db, action, user_id=user_id, resource_type="authentication", status=status)
        db.commit()
    except Exception:
        db.rollback()
