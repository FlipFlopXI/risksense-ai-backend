from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_database, require_role
from app.models.access_entitlement import AccessEntitlement
from app.models.insurance import Insurance
from app.models.patient import Patient
from app.models.subscription import Subscription
from app.models.user import User, UserRole
from app.schemas.access import EntitlementResponse
from app.services.health_service import get_patient_by_user_id
from app.services.verification_service import staged_activate_subscription, staged_verify_insurance

router = APIRouter(prefix="/access", tags=["Access"])


class MockSubscriptionCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: UUID
    days: int = Field(default=30, ge=1, le=366)


class MockInsuranceCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: UUID
    coverage_expires_at: datetime | None = None


@router.get("/entitlements", response_model=list[EntitlementResponse])
def entitlements(user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    return list(db.scalars(select(AccessEntitlement).where(AccessEntitlement.patient_id == patient.id).order_by(AccessEntitlement.created_at.desc())).all())


@router.post("/mock/subscription/complete", response_model=EntitlementResponse)
def complete_subscription(request: MockSubscriptionCompletion, admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    patient = db.get(Patient, request.patient_id)
    subscription = db.scalar(select(Subscription).where(Subscription.patient_id == request.patient_id))
    if patient is None or subscription is None or not subscription.requested_clinician_risk_sense_id:
        raise HTTPException(status_code=404, detail="Pending subscription activation not found.")
    try:
        return staged_activate_subscription(db, patient, subscription, subscription.requested_clinician_risk_sense_id, admin.id, request.days)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/mock/insurance/complete", response_model=EntitlementResponse)
def complete_insurance(request: MockInsuranceCompletion, admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_database)):
    patient = db.get(Patient, request.patient_id)
    insurance = db.scalar(select(Insurance).where(Insurance.patient_id == request.patient_id))
    if patient is None or insurance is None or not insurance.requested_clinician_risk_sense_id:
        raise HTTPException(status_code=404, detail="Pending insurance verification not found.")
    try:
        return staged_verify_insurance(db, patient, insurance, insurance.requested_clinician_risk_sense_id, admin.id, request.coverage_expires_at)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
