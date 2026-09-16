from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.access_entitlement import AccessEntitlement, EntitlementSource, EntitlementStatus
from app.models.insurance import Insurance, InsuranceVerificationStatus
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.clinician import ClinicianApprovalStatus
from app.services.audit_service import add_audit_event


def get_effective_entitlement(db: Session, patient_id: UUID) -> AccessEntitlement | None:
    now = datetime.now(timezone.utc)
    candidates = db.scalars(
        select(AccessEntitlement).where(
            AccessEntitlement.patient_id == patient_id,
            AccessEntitlement.status == EntitlementStatus.ACTIVE,
            AccessEntitlement.verified_at.is_not(None),
            or_(AccessEntitlement.expires_at.is_(None), AccessEntitlement.expires_at > now),
        )
    ).all()
    for entitlement in candidates:
        if (
            entitlement.clinician is None
            or entitlement.clinician.approval_status != ClinicianApprovalStatus.APPROVED
            or not entitlement.clinician.user.is_active
        ):
            continue
        if entitlement.source == EntitlementSource.SUBSCRIPTION:
            source = entitlement.subscription
            if source and source.status == SubscriptionStatus.ACTIVE and (
                source.expires_at is None or source.expires_at > now
            ):
                return entitlement
        elif entitlement.source == EntitlementSource.INSURANCE:
            source = entitlement.insurance
            if source and source.verification_status == InsuranceVerificationStatus.VERIFIED and (
                source.coverage_expires_at is None or source.coverage_expires_at > now
            ):
                return entitlement
    return None


def activate_entitlement(
    db: Session,
    *,
    patient_id: UUID,
    source: EntitlementSource,
    clinician_id: UUID,
    verification_source: str,
    expires_at: datetime | None,
    actor_id: UUID | None,
    subscription: Subscription | None = None,
    insurance: Insurance | None = None,
) -> AccessEntitlement:
    if not verification_source.startswith(("MOCK_", "STAGED_")):
        raise ValueError("Only explicitly staged verification is supported.")
    entitlement = db.scalar(
        select(AccessEntitlement).where(
            AccessEntitlement.patient_id == patient_id,
            AccessEntitlement.source == source,
            AccessEntitlement.status.in_((EntitlementStatus.PENDING, EntitlementStatus.ACTIVE)),
        )
    )
    if entitlement is None:
        entitlement = AccessEntitlement(
            patient_id=patient_id,
            source=source,
            reference_number=f"RS-ENT-{uuid4().hex[:16].upper()}",
        )
        db.add(entitlement)
    entitlement.status = EntitlementStatus.ACTIVE
    entitlement.clinician_id = clinician_id
    entitlement.subscription_id = subscription.id if subscription else None
    entitlement.insurance_id = insurance.id if insurance else None
    entitlement.verification_source = verification_source
    entitlement.verified_at = datetime.now(timezone.utc)
    entitlement.expires_at = expires_at
    db.flush()
    add_audit_event(
        db,
        "ENTITLEMENT_ACTIVATED",
        user_id=actor_id,
        resource_type="access_entitlement",
        resource_id=str(entitlement.id),
        details={"source": source.value, "verification_source": verification_source},
    )
    return entitlement
