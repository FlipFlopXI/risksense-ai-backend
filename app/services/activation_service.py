from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from urllib.parse import quote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.activation_session import ActivationSession
from app.models.access_entitlement import AccessEntitlement, EntitlementSource, EntitlementStatus
from app.models.insurance import Insurance, InsuranceVerificationStatus
from app.models.patient import Patient
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import UserRole
from app.schemas.activation import ActivationCompleteRequest
from app.services.audit_service import add_audit_event
from app.services.clinician_service import get_approved_clinician
from app.services.entitlement_service import get_effective_entitlement
from app.services.verification_service import staged_activate_subscription, staged_verify_insurance


class ActivationRejected(Exception):
    def __init__(self, message: str, status: int = 400):
        self.message, self.status = message, status


def digest(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def web_origin() -> str:
    url = settings.WEBAPP_BASE_URL
    parsed = urlparse(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("WEBAPP_BASE_URL must be a plain origin.")
    if parsed.scheme == "https" and parsed.netloc:
        return url.rstrip("/")
    if settings.ENVIRONMENT != "production" and parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"):
        return url.rstrip("/")
    raise ValueError("WEBAPP_BASE_URL must use HTTPS outside local development.")


def issue(db: Session, patient: Patient) -> tuple[str, datetime]:
    # Invalidate earlier unused handoff links for the same patient.
    for old in db.scalars(select(ActivationSession).where(ActivationSession.patient_id == patient.id, ActivationSession.consumed_at.is_(None), ActivationSession.revoked_at.is_(None)).with_for_update()):
        old.revoked_at = now_utc()
    raw = secrets.token_urlsafe(48)
    expires = now_utc() + timedelta(minutes=15)
    row = ActivationSession(patient_id=patient.id, handoff_hash=digest(raw), expires_at=expires)
    db.add(row)
    db.flush()
    add_audit_event(db, "ACTIVATION_SESSION_ISSUED", user_id=patient.user_id, resource_type="activation_session", resource_id=str(row.id))
    db.commit()
    return f"{web_origin()}/register/complete#token={quote(raw, safe='')}", expires


def exchange(db: Session, raw: str) -> tuple[str, ActivationSession]:
    row = db.scalar(select(ActivationSession).where(ActivationSession.handoff_hash == digest(raw)).with_for_update())
    if not row or row.revoked_at or row.exchanged_at or row.consumed_at or row.expires_at <= now_utc():
        raise ActivationRejected("This activation link is invalid, expired, or already used.", 401)
    if not row.patient or not row.patient.user.is_active or row.patient.user.role != UserRole.PATIENT:
        raise ActivationRejected("Patient account is unavailable.", 403)
    credential = secrets.token_urlsafe(48)
    row.credential_hash = digest(credential)
    row.exchanged_at = now_utc()
    add_audit_event(db, "ACTIVATION_SESSION_EXCHANGED", user_id=row.patient.user_id, resource_type="activation_session", resource_id=str(row.id))
    db.commit()
    return credential, row


def scoped_session(db: Session, raw: str, *, lock: bool = False) -> ActivationSession:
    query = select(ActivationSession).where(ActivationSession.credential_hash == digest(raw))
    row = db.scalar(query.with_for_update() if lock else query)
    if not row or not row.exchanged_at or row.revoked_at or row.expires_at <= now_utc():
        raise ActivationRejected("Your activation session has expired. Start again from the app or sign in.", 401)
    if not row.patient or not row.patient.user.is_active or row.patient.user.role != UserRole.PATIENT:
        raise ActivationRejected("Patient account is unavailable.", 403)
    return row


def complete(db: Session, row: ActivationSession, request: ActivationCompleteRequest) -> AccessEntitlement:
    if row.consumed_at:
        if row.entitlement_id:
            entitlement = db.get(AccessEntitlement, row.entitlement_id)
            if entitlement and entitlement.patient_id == row.patient_id and entitlement.status == EntitlementStatus.ACTIVE:
                return entitlement
        raise ActivationRejected("This activation session has already been used.", 409)

    patient = row.patient
    if get_effective_entitlement(db, patient.id):
        raise ActivationRejected("RiskSense access is already active for this account.", 409)
    clinician = get_approved_clinician(db, request.clinician_risk_sense_id)
    if clinician is None:
        raise ActivationRejected("Approved clinician not found.", 404)
    subscription = db.scalar(select(Subscription).where(Subscription.patient_id == patient.id).with_for_update())
    insurance = db.scalar(select(Insurance).where(Insurance.patient_id == patient.id).with_for_update())
    if request.method == "subscription":
        if insurance and insurance.verification_status in (InsuranceVerificationStatus.PENDING, InsuranceVerificationStatus.VERIFIED):
            raise ActivationRejected("An insurance request already exists for this account.", 409)
        if subscription is None:
            subscription = Subscription(patient_id=patient.id, plan=request.plan, requested_clinician_risk_sense_id=request.clinician_risk_sense_id, status=SubscriptionStatus.PENDING)
            db.add(subscription)
            db.flush()
            add_audit_event(db, "SUBSCRIPTION_REQUESTED", user_id=patient.user_id, resource_type="subscription", resource_id=str(subscription.id), details={"plan": request.plan.value})
        elif subscription.status != SubscriptionStatus.PENDING or subscription.plan != request.plan or subscription.requested_clinician_risk_sense_id != request.clinician_risk_sense_id:
            raise ActivationRejected("Existing subscription request differs from this activation.", 409)
        entitlement = staged_activate_subscription(db, patient, subscription, request.clinician_risk_sense_id, patient.user_id, commit=False)
    else:
        if subscription and subscription.status in (SubscriptionStatus.PENDING, SubscriptionStatus.ACTIVE):
            raise ActivationRejected("A subscription request already exists for this account.", 409)
        if insurance is None:
            insurance = Insurance(patient_id=patient.id, provider_name=request.provider_name.strip(), policy_number=request.policy_number, membership_number=request.membership_number, requested_clinician_risk_sense_id=request.clinician_risk_sense_id, coverage_status="pending", verification_status=InsuranceVerificationStatus.PENDING)
            db.add(insurance)
            db.flush()
            add_audit_event(db, "INSURANCE_DETAILS_SUBMITTED", user_id=patient.user_id, resource_type="insurance", resource_id=str(insurance.id))
        elif (insurance.verification_status != InsuranceVerificationStatus.PENDING
              or insurance.provider_name != request.provider_name.strip()
              or insurance.policy_number != request.policy_number
              or insurance.membership_number != request.membership_number
              or insurance.requested_clinician_risk_sense_id != request.clinician_risk_sense_id):
            raise ActivationRejected("Existing insurance request differs from this activation.", 409)
        entitlement = staged_verify_insurance(db, patient, insurance, request.clinician_risk_sense_id, patient.user_id, commit=False)
    row.consumed_at = now_utc()
    row.entitlement_id = entitlement.id
    add_audit_event(db, "PATIENT_ACTIVATION_COMPLETED", user_id=patient.user_id, resource_type="activation_session", resource_id=str(row.id), details={"method": request.method, "mode": "demo"})
    db.commit()
    db.refresh(entitlement)
    return entitlement
