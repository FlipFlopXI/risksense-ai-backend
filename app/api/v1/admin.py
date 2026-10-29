from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.dependencies import get_database, require_role
from app.models.audit import AuditLog
from app.models.clinician import Clinician, ClinicianApprovalStatus
from app.models.prediction import Prediction
from app.models.model import Model
from app.models.user import User, UserRole
from app.models.patient import Patient
from app.schemas.admin import AdminActionSummary, AdminMetricsResponse, AdminProfileResponse, AdminUserResponse, ClinicianApprovalRequest, ClinicianProvisionRequest
from app.schemas.access import ClinicianLookupResponse
from app.schemas.clinician_change import ClinicianChangeDecision, ClinicianChangeResponse
from app.services import clinician_change_service
from app.services.audit_service import add_audit_event
from app.services.auth_service import get_user_by_email
from app.services.clinician_service import generate_risk_sense_id
from app.core.security import hash_password
from app.ml.heart_disease.runtime import ModelUnavailableError
from app.services.risk_analysis_service import activate_heart_model
from app.services.model_metrics_service import verified_holdout_accuracy
from app.services.diabetes_service import activate_diabetes_model
from app.schemas.drug_assistant import DrugAssistantStatusResponse
from app.ml.drug_assistant.runtime import load_runtime
from app.ml.drug_assistant.evidence_store import load_published_store
from app.ml.drug_assistant.evidence_pipeline import COVERAGE_PATH, QUEUE_PATH
from app.ml.drug_assistant.evidence_normalization import NORMALIZATION_REPORT
import json
from collections import Counter

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/clinician-change-requests", response_model=list[ClinicianChangeResponse])
def pending_clinician_changes(admin: User = Depends(require_role(UserRole.ADMIN)),
                              db: Session = Depends(get_database)):
    return [clinician_change_service.response(db, row)
            for row in clinician_change_service.pending_requests(db)]


@router.post("/clinician-change-requests/{request_id}/decision", response_model=ClinicianChangeResponse)
def decide_clinician_change(request_id: UUID, request: ClinicianChangeDecision,
                            admin: User = Depends(require_role(UserRole.ADMIN)),
                            db: Session = Depends(get_database)):
    row = clinician_change_service.decide(db, request_id, admin.id, request.decision)
    return clinician_change_service.response(db, row)


@router.get("/me", response_model=AdminProfileResponse)
def admin_me(admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    last_login_at = db.scalar(
        select(AuditLog.created_at).where(
            AuditLog.user_id == admin.id,
            AuditLog.action == "LOGIN_SUCCESS",
        ).order_by(AuditLog.created_at.desc()).limit(1)
    )
    last_action = db.scalar(
        select(AuditLog).where(
            AuditLog.user_id == admin.id,
            AuditLog.action.notin_((
                "LOGIN_SUCCESS", "LOGIN_FAILURE", "LOGOUT",
                "AUTH_SESSION_CREATED", "AUTH_SESSION_REFRESHED",
            )),
        ).order_by(AuditLog.created_at.desc()).limit(1)
    )
    return AdminProfileResponse(
        id=admin.id, admin_id=admin.id, email=admin.email, role=admin.role,
        is_active=admin.is_active, created_at=admin.created_at,
        last_login_at=last_login_at,
        last_action=(AdminActionSummary(
            action=last_action.action,
            resource_type=last_action.resource_type,
            resource_id=last_action.resource_id,
            performed_at=last_action.created_at,
        ) if last_action else None),
    )


@router.get("/metrics", response_model=AdminMetricsResponse)
def metrics(admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    return AdminMetricsResponse(
        total_users=db.scalar(select(func.count(User.id))) or 0,
        clinician_count=db.scalar(select(func.count(Clinician.id))) or 0,
        prediction_count=db.scalar(select(func.count(Prediction.id))) or 0,
        audit_event_count=db.scalar(select(func.count(AuditLog.id))) or 0,
    )


@router.get("/users", response_model=list[AdminUserResponse])
def users(search: str | None = None, role: UserRole | None = None, is_active: bool | None = None,
          oldest_first: bool = False, limit: int = Query(100, ge=1, le=200),
          offset: int = Query(0, ge=0), admin: User = Depends(require_role(UserRole.ADMIN)),
          db: Session = Depends(get_database)):
    # Exclude the signed-in administrator before filtering and pagination.
    query = select(User).where(User.id != admin.id)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.outerjoin(Patient, Patient.user_id == User.id).outerjoin(
            Clinician, Clinician.user_id == User.id).where(or_(
                User.email.ilike(pattern), User.id.cast(String).ilike(pattern),
                Patient.first_name.ilike(pattern), Patient.last_name.ilike(pattern),
                Clinician.first_name.ilike(pattern), Clinician.last_name.ilike(pattern),
            ))
    if role:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    query = query.order_by(User.created_at.asc() if oldest_first else User.created_at.desc())
    rows = list(db.scalars(query.offset(offset).limit(limit)).all())
    patient_names = {row.user_id: f"{row.first_name} {row.last_name}"
                     for row in db.scalars(select(Patient).where(Patient.user_id.in_([u.id for u in rows]))).all()} if rows else {}
    # Select only existing identity columns: a pending clinician-profile migration
    # must not break the admin user list just to display names.
    clinician_names = {user_id: f"{first_name} {last_name}"
                       for user_id, first_name, last_name in db.execute(select(
                           Clinician.user_id, Clinician.first_name, Clinician.last_name,
                       ).where(Clinician.user_id.in_([u.id for u in rows]))).all()} if rows else {}
    return [AdminUserResponse.model_validate(user).model_copy(update={
        "display_name": patient_names.get(user.id) or clinician_names.get(user.id) or
                        ("System Administrator" if user.role == UserRole.ADMIN else None),
    }) for user in rows]


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
        gender=request.gender or "unspecified",
    )
    db.add(clinician)
    db.flush()
    add_audit_event(db, "CLINICIAN_PROVISIONED", user_id=admin.id, resource_type="clinician", resource_id=str(clinician.id))
    db.commit()
    db.refresh(clinician)
    return clinician


@router.get("/audit/actions", response_model=list[str])
def audit_actions(admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    return list(db.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action)).all())


@router.get("/audit", response_model=list[dict])
def audit(action: str | None = None, status: str | None = None, resource_type: str | None = None,
          oldest_first: bool = False, limit: int = Query(100, ge=1, le=500),
          offset: int = Query(0, ge=0), admin: User = Depends(require_role(UserRole.ADMIN)),
          db: Session = Depends(get_database)):
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if status:
        query = query.where(AuditLog.status == status)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    query = query.order_by(AuditLog.created_at.asc() if oldest_first else AuditLog.created_at.desc())
    events = db.scalars(query.offset(offset).limit(limit)).all()
    actors = {u.id: u.email for u in db.scalars(select(User).where(
        User.id.in_([e.user_id for e in events if e.user_id is not None]))).all()} if events else {}
    return [{"id": str(e.id), "user_id": str(e.user_id) if e.user_id else None,
             "user_email": actors.get(e.user_id), "action": e.action,
             "resource_type": e.resource_type, "resource_id": e.resource_id,
             "status": e.status, "ip_address": e.ip_address,
             "created_at": e.created_at.isoformat()} for e in events]


@router.get("/models", response_model=list[dict])
def models(admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    records = db.scalars(select(Model).order_by(Model.created_at.desc())).all()
    result = []
    for item in records:
        accuracy, accuracy_source = verified_holdout_accuracy(item)
        result.append({"id": str(item.id), "name": item.name, "version": item.version,
             "prediction_target": item.prediction_target, "algorithm": item.algorithm,
             "description": item.description, "dataset_name": item.dataset_name,
             "accuracy": accuracy, "accuracy_source": accuracy_source,
             "precision_score": item.precision_score,
             "recall_score": item.recall_score, "f1_score": item.f1_score,
             "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
             "is_active": item.is_active})
    return result


@router.post("/models/{model_id}/resume")
def resume_model(model_id: UUID, admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model record not found.")
    if model.prediction_target == "diabetes_risk":
        from app.services.diabetes_service import MODEL_ID
        if model.id != MODEL_ID:
            raise HTTPException(status_code=409, detail="This version cannot be resumed by the current runtime.")
        return activate_diabetes(admin, db)
    if model.prediction_target == "heart_disease":
        from app.services.risk_analysis_service import MODEL_ID
        if model.id != MODEL_ID:
            raise HTTPException(status_code=409, detail="This version cannot be resumed by the current runtime.")
        return activate_heart_disease(admin, db)
    raise HTTPException(status_code=409, detail="This model has no verified activation workflow.")


@router.post("/models/{model_id}/suspend")
def suspend_model(model_id: UUID, admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model record not found.")
    model.is_active = False
    add_audit_event(db, "MODEL_SUSPENDED", user_id=admin.id, resource_type="ml_model", resource_id=str(model.id))
    db.commit()
    return {"id": str(model.id), "is_active": False}


@router.post("/models/heart-disease/activate")
def activate_heart_disease(admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    try:
        model = activate_heart_model(db, admin.id)
        return {"id": str(model.id), "version": model.version, "prediction_target": model.prediction_target, "is_active": model.is_active}
    except (ModelUnavailableError, SQLAlchemyError):
        db.rollback()
        raise HTTPException(status_code=503, detail="Heart Disease model activation is unavailable; check server configuration.") from None


@router.post("/models/diabetes/activate")
def activate_diabetes(admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    try:
        model = activate_diabetes_model(db, admin.id)
        return {"id": str(model.id), "version": model.version, "prediction_target": model.prediction_target, "is_active": model.is_active}
    except (ModelUnavailableError, SQLAlchemyError):
        db.rollback()
        raise HTTPException(status_code=503, detail="Diabetes model activation is unavailable; check server configuration.") from None


@router.get("/drug-assistant/status", response_model=DrugAssistantStatusResponse)
def drug_assistant_status(admin: User = Depends(require_role(UserRole.ADMIN))):
    try:
        runtime = load_runtime()
        store = load_published_store()
        coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
        queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        normalization = json.loads(NORMALIZATION_REPORT.read_text(encoding="utf-8"))
        ingestion = Counter(item["status"] for item in queue["operations"])
        overall = Counter(item["overall_coverage_status"] for item in coverage["records"])
        return DrugAssistantStatusResponse(
            runtime_status="AVAILABLE", artifact_integrity_status="VERIFIED",
            catalogue_version=runtime.model["knowledge_version"],
            catalogue_medication_count=len(runtime.drugs),
            therapeutic_group_count=len({item["therapeutic_group"] for item in runtime.drugs.values()}),
            intent_count=len(runtime.model["supported_intents"]), policy_version=runtime.policy["policy_version"],
            evidence_provider_status="AVAILABLE", reviewed_evidence_count=len(store.records),
            review_required_operation_count=sum(ingestion[state] for state in ("SUCCESS", "PARTIAL", "REQUIRES_REVIEW")),
            ingestion_status_counts=dict(ingestion), complete_count=overall["COMPLETE"],
            partial_count=sum(overall[key] for key in ("SUBSTANTIAL", "PARTIAL", "MINIMAL")),
            insufficient_count=overall["INSUFFICIENT"],
            last_coverage_generation_time=coverage.get("generated_at"),
            published_medication_count=len({item["drug_id"] for item in store.records}),
            coverage_by_topic=dict(Counter(item["topic"] for item in store.records)),
            coverage_by_source=dict(Counter(item["source_organisation"] for item in store.records)),
            pending_review_record_count=normalization.get("review", {}).get("REVIEW_REQUIRED", 0),
            dailymed_unresolved_product_count=sum(item["source_family"] == "DAILYMED" and item["status"] == "PARTIAL" for item in queue["operations"]),
            retrieval_failure_count=ingestion["FAILED"],
        )
    except Exception:
        raise HTTPException(status_code=503, detail="Drug Assistant operational status is unavailable.") from None
