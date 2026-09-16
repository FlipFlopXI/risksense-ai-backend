from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.insurance import Insurance
from app.models.insurance import InsuranceVerificationStatus
from app.models.patient import Patient
from app.schemas.insurance import (
    InsuranceCreateRequest,
    InsuranceUpdateRequest,
)
from app.services.audit_service import add_audit_event


def get_patient_by_user_id(
    db: Session,
    user_id: UUID,
) -> Patient | None:
    statement = select(Patient).where(
        Patient.user_id == user_id
    )
    return db.scalar(statement)


def get_insurance(
    db: Session,
    patient_id: UUID,
) -> Insurance | None:
    statement = select(Insurance).where(
        Insurance.patient_id == patient_id
    )
    return db.scalar(statement)


def create_insurance(
    db: Session,
    patient: Patient,
    request: InsuranceCreateRequest,
) -> Insurance:
    existing_insurance = get_insurance(
        db,
        patient.id,
    )

    if existing_insurance:
        raise ValueError(
            "Insurance information already exists for this patient."
        )

    insurance = Insurance(
        patient_id=patient.id,
        requested_clinician_risk_sense_id=request.clinician_risk_sense_id,
        provider_name=request.provider_name.strip(),
        policy_number=(
            request.policy_number.strip()
            if request.policy_number
            else None
        ),
        coverage_status="pending",
        verification_status=InsuranceVerificationStatus.PENDING,
        membership_number=(
            request.membership_number.strip()
            if request.membership_number
            else None
        ),
        plan_name=(
            request.plan_name.strip()
            if request.plan_name
            else None
        ),
    )

    db.add(insurance)
    db.flush()
    add_audit_event(db, "INSURANCE_DETAILS_SUBMITTED", user_id=patient.user_id, resource_type="insurance", resource_id=str(insurance.id))
    db.commit()
    db.refresh(insurance)

    return insurance


def update_insurance(
    db: Session,
    insurance: Insurance,
    request: InsuranceUpdateRequest,
) -> Insurance:
    update_data = request.model_dump(
        exclude_unset=True
    )

    if update_data:
        insurance.coverage_status = "pending"
        insurance.verification_status = InsuranceVerificationStatus.PENDING
        insurance.verification_source = None
        insurance.verified_at = None
        insurance.coverage_starts_at = None
        insurance.coverage_expires_at = None
        add_audit_event(db, "INSURANCE_DETAILS_SUBMITTED", user_id=insurance.patient.user_id, resource_type="insurance", resource_id=str(insurance.id), details={"change": "details_updated"})

    for field, value in update_data.items():
        if isinstance(value, str):
            value = value.strip()

        setattr(insurance, field, value)

    db.commit()
    db.refresh(insurance)

    return insurance
