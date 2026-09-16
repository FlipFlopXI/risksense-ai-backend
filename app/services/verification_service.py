from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.access_entitlement import EntitlementSource
from app.models.insurance import Insurance, InsuranceVerificationStatus
from app.models.patient import Patient
from app.models.subscription import Subscription, SubscriptionStatus
from app.services.audit_service import add_audit_event
from app.services.clinician_service import get_approved_clinician
from app.services.entitlement_service import activate_entitlement
from app.services.patient_clinician_service import link_patient_clinician


def staged_activate_subscription(db: Session, patient: Patient, subscription: Subscription, clinician_risk_sense_id: str, actor_id: UUID, days: int = 30):
    clinician = get_approved_clinician(db, clinician_risk_sense_id)
    if clinician is None:
        raise ValueError("Approved clinician not found.")
    now = datetime.now(timezone.utc)
    base = subscription.expires_at if subscription.status == SubscriptionStatus.ACTIVE and subscription.expires_at and subscription.expires_at > now else now
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.started_at = now
    subscription.expires_at = base + timedelta(days=days)
    link_patient_clinician(db, patient.id, clinician.id, actor_id)
    entitlement = activate_entitlement(db, patient_id=patient.id, source=EntitlementSource.SUBSCRIPTION, clinician_id=clinician.id, subscription=subscription, insurance=None, verification_source="MOCK_PAYMENT", expires_at=subscription.expires_at, actor_id=actor_id)
    add_audit_event(db, "SUBSCRIPTION_ACTIVATION", user_id=actor_id, resource_type="subscription", resource_id=str(subscription.id), details={"verification_source": "MOCK_PAYMENT"})
    db.commit()
    db.refresh(entitlement)
    return entitlement


def staged_verify_insurance(db: Session, patient: Patient, insurance: Insurance, clinician_risk_sense_id: str, actor_id: UUID, coverage_expires_at: datetime | None = None):
    clinician = get_approved_clinician(db, clinician_risk_sense_id)
    if clinician is None:
        raise ValueError("Approved clinician not found.")
    now = datetime.now(timezone.utc)
    insurance.verification_status = InsuranceVerificationStatus.VERIFIED
    insurance.coverage_status = "verified"
    insurance.verification_source = "MOCK_INSURANCE"
    insurance.verified_at = now
    insurance.coverage_starts_at = now
    insurance.coverage_expires_at = coverage_expires_at
    link_patient_clinician(db, patient.id, clinician.id, actor_id)
    entitlement = activate_entitlement(db, patient_id=patient.id, source=EntitlementSource.INSURANCE, clinician_id=clinician.id, subscription=None, insurance=insurance, verification_source="MOCK_INSURANCE", expires_at=coverage_expires_at, actor_id=actor_id)
    add_audit_event(db, "INSURANCE_VERIFICATION", user_id=actor_id, resource_type="insurance", resource_id=str(insurance.id), details={"verification_source": "MOCK_INSURANCE"})
    db.commit()
    db.refresh(entitlement)
    return entitlement
