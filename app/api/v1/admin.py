from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import get_database, require_role
from app.models.audit import AuditLog
from app.models.clinician import Clinician, ClinicianApprovalStatus
from app.models.prediction import Prediction
from app.models.model import Model
from app.models.user import User, UserRole
from app.schemas.admin import AdminMetricsResponse, AdminUserResponse, ClinicianApprovalRequest, ClinicianProvisionRequest
from app.schemas.access import ClinicianLookupResponse
from app.services.audit_service import add_audit_event
from app.services.auth_service import get_user_by_email
from app.services.clinician_service import generate_risk_sense_id
from app.core.security import hash_password

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/me", response_model=AdminUserResponse)
def admin_me(admin: User = Depends(require_role(UserRole.ADMIN))):
    return admin


@router.get("/metrics", response_model=AdminMetricsResponse)
def metrics(admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    return AdminMetricsResponse(
        total_users=db.scalar(select(func.count(User.id))) or 0,
        clinician_count=db.scalar(select(func.count(Clinician.id))) or 0,
        prediction_count=db.scalar(select(func.count(Prediction.id))) or 0,
        audit_event_count=db.scalar(select(func.count(AuditLog.id))) or 0,
    )


@router.get("/users", response_model=list[AdminUserResponse])
def users(search: str | None = None, role: UserRole | None = None, limit: int = Query(100, ge=1, le=200), admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    query = select(User)
    if search:
        query = query.where(User.email.ilike(f"%{search.strip()}%"))
    if role:
        query = query.where(User.role == role)
    return list(db.scalars(query.order_by(User.created_at.desc()).limit(limit)).all())


def set_user_active(db: Session, target_id: UUID, active: bool, admin: User):
    target = db.get(User, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.id == admin.id and not active:
        raise HTTPException(status_code=409, detail="Administrators cannot suspend their own account.")
    target.is_active = active
    add_audit_event(db, "USER_REACTIVATED" if active else "USER_SUSPENDED", user_id=admin.id, resource_type="user", resource_id=str(target.id))
    db.commit()
    db.refresh(target)
    return target


@router.post("/users/{user_id}/suspend", response_model=AdminUserResponse)
def suspend(user_id: UUID, admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    return set_user_active(db, user_id, False, admin)


@router.post("/users/{user_id}/restore", response_model=AdminUserResponse)
def restore(user_id: UUID, admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    return set_user_active(db, user_id, True, admin)


@router.patch("/clinicians/{clinician_id}/approval", response_model=ClinicianLookupResponse)
def approve_clinician(clinician_id: UUID, request: ClinicianApprovalRequest, admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    clinician = db.get(Clinician, clinician_id)
    if clinician is None:
        raise HTTPException(status_code=404, detail="Clinician not found.")
    clinician.approval_status = request.status
    clinician.approved_at = datetime.now(timezone.utc) if request.status == ClinicianApprovalStatus.APPROVED else None
    add_audit_event(db, f"CLINICIAN_{request.status.value.upper()}", user_id=admin.id, resource_type="clinician", resource_id=str(clinician.id))
    db.commit()
    db.refresh(clinician)
    return clinician


@router.post("/clinicians", response_model=ClinicianLookupResponse, status_code=201)
def provision_clinician(request: ClinicianProvisionRequest, admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    email = str(request.email).strip().lower()
    if get_user_by_email(db, email):
        raise HTTPException(status_code=409, detail="A user with this email already exists.")
    user = User(email=email, password_hash=hash_password(request.temporary_password), role=UserRole.CLINICIAN, is_active=True)
    db.add(user)
    db.flush()
    clinician = Clinician(
        user_id=user.id,
        risk_sense_id=generate_risk_sense_id(db),
        approval_status=ClinicianApprovalStatus.PENDING,
        first_name=request.first_name.strip(),
        last_name=request.last_name.strip(),
        professional_title=request.professional_title,
        license_number=request.license_number,
        specialization=request.specialization,
        institution=request.institution,
    )
    db.add(clinician)
    db.flush()
    add_audit_event(db, "CLINICIAN_PROVISIONED", user_id=admin.id, resource_type="clinician", resource_id=str(clinician.id))
    db.commit()
    db.refresh(clinician)
    return clinician


@router.get("/audit", response_model=list[dict])
def audit(action: str | None = None, limit: int = Query(100, ge=1, le=500), admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    events = db.scalars(query.order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return [{"id": str(e.id), "user_id": str(e.user_id) if e.user_id else None, "action": e.action, "resource_type": e.resource_type, "resource_id": e.resource_id, "status": e.status, "created_at": e.created_at.isoformat()} for e in events]


@router.get("/models", response_model=list[dict])
def models(admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    records = db.scalars(select(Model).order_by(Model.created_at.desc())).all()
    return [{"id": str(item.id), "name": item.name, "version": item.version, "prediction_target": item.prediction_target, "algorithm": item.algorithm, "is_active": item.is_active} for item in records]


@router.post("/models/{model_id}/suspend")
def suspend_model(model_id: UUID, admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model record not found.")
    model.is_active = False
    add_audit_event(db, "MODEL_SUSPENDED", user_id=admin.id, resource_type="ml_model", resource_id=str(model.id))
    db.commit()
    return {"id": str(model.id), "is_active": False}
