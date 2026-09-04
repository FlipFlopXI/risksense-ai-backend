from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.insurance import Insurance
from app.models.patient import Patient
from app.schemas.insurance import (
    InsuranceCreateRequest,
    InsuranceUpdateRequest,
)


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
        provider_name=request.provider_name.strip(),
        policy_number=(
            request.policy_number.strip()
            if request.policy_number
            else None
        ),
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

    for field, value in update_data.items():
        if isinstance(value, str):
            value = value.strip()

        setattr(insurance, field, value)

    db.commit()
    db.refresh(insurance)

    return insurance