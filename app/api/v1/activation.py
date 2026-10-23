from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_database, require_role
from app.core.config import settings
from app.models.patient import Patient
from app.models.access_entitlement import EntitlementSource
from app.models.patient_clinician import PatientClinicianStatus
from app.models.user import User, UserRole
from app.schemas.access import ClinicianLookupResponse
from app.schemas.activation import ActivationCompleteRequest, ActivationContextResponse, ActivationExchangeRequest, ActivationExchangeResponse, ActivationIssueResponse, ActivationResult, AccessStatus
from app.services.activation_service import ActivationRejected, complete, exchange, issue, scoped_session, web_origin
from app.services.clinician_service import get_approved_clinician
from app.services.entitlement_service import get_effective_entitlement
from app.services.patient_clinician_service import get_patient_clinician
from app.services.audit_service import record_auth_event_best_effort

router = APIRouter(prefix="/access", tags=["Patient Activation"])
bearer = HTTPBearer()


def credential(auth: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    return auth.credentials


@router.post("/activation-session", response_model=ActivationIssueResponse)
def issue_activation_session(user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    if not settings.DEMO_ACTIVATION_ENABLED:
        raise HTTPException(status_code=503, detail="Demonstration activation is disabled.")
    try:
        web_origin()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Activation website is not configured.") from exc
    patient = db.scalar(select(Patient).where(Patient.user_id == user.id).with_for_update())
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    url, expires = issue(db, patient)
    return ActivationIssueResponse(activation_url=url, expires_at=expires, expires_in=max(0, int((expires - datetime.now(timezone.utc)).total_seconds())))


@router.post("/activation-session/exchange", response_model=ActivationExchangeResponse)
def exchange_activation_session(request: ActivationExchangeRequest, db: Session = Depends(get_database)):
    try:
        raw, row = exchange(db, request.token)
        return ActivationExchangeResponse(activation_credential=raw, expires_at=row.expires_at, email=row.patient.user.email)
    except ActivationRejected as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from None


@router.get("/activation/clinicians/lookup/{risk_sense_id}", response_model=ClinicianLookupResponse)
def lookup_activation_clinician(risk_sense_id: str, raw: str = Depends(credential), db: Session = Depends(get_database)):
    try:
        row = scoped_session(db, raw)
        if row.consumed_at:
            raise ActivationRejected("Activation already completed.", 409)
        clinician = get_approved_clinician(db, risk_sense_id)
        if clinician is None:
            raise ActivationRejected("Approved clinician not found.", 404)
        return clinician
    except ActivationRejected as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from None


@router.get("/activation/context", response_model=ActivationContextResponse)
def activation_context(raw: str = Depends(credential), db: Session = Depends(get_database)):
    try:
        row = scoped_session(db, raw)
        effective = get_effective_entitlement(db, row.patient_id) if row.consumed_at else None
        active = bool(effective and effective.id == row.entitlement_id)
        return ActivationContextResponse(email=row.patient.user.email, active=active, expires_at=row.expires_at)
    except ActivationRejected as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from None


@router.post("/activation/complete", response_model=ActivationResult)
def complete_activation(request: ActivationCompleteRequest, raw: str = Depends(credential), db: Session = Depends(get_database)):
    if not settings.DEMO_ACTIVATION_ENABLED:
        raise HTTPException(status_code=503, detail="Demonstration activation is disabled.")
    actor_id = None
    try:
        row = scoped_session(db, raw, lock=True)
        actor_id = row.patient.user_id
        entitlement = complete(db, row, request)
        source = entitlement.source.value if isinstance(entitlement.source, EntitlementSource) else entitlement.source
        return ActivationResult(active=True, status="active", access_method=source, clinician_linked=True)
    except ActivationRejected as exc:
        db.rollback()
        if actor_id is not None:
            record_auth_event_best_effort(db, "ACTIVATION_REJECTED", actor_id, "failure")
        raise HTTPException(status_code=exc.status, detail=exc.message) from None
    except ValueError as exc:
        db.rollback()
        if actor_id is not None:
            record_auth_event_best_effort(db, "ACTIVATION_REJECTED", actor_id, "failure")
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/status", response_model=AccessStatus)
def patient_access_status(user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = db.scalar(select(Patient).where(Patient.user_id == user.id))
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    entitlement = get_effective_entitlement(db, patient.id)
    if entitlement is None:
        return AccessStatus(active=False, status="inactive", access_method=None, clinician_linked=False)
    link = get_patient_clinician(db, patient.id, entitlement.clinician_id)
    source = entitlement.source.value if isinstance(entitlement.source, EntitlementSource) else entitlement.source
    linked = bool(link and link.status == PatientClinicianStatus.ACTIVE)
    return AccessStatus(active=linked, status="active" if linked else "inactive", access_method=source if linked else None, clinician_linked=linked)
