from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.health_profile import HealthProfile
from app.models.patient import Patient
from app.schemas.health import (
    HealthProfileCreateRequest,
    HealthProfileUpdateRequest,
)


def get_patient_by_user_id(
    db: Session,
    user_id,
) -> Patient | None:
    statement = select(Patient).where(
        Patient.user_id == user_id
    )

    return db.scalar(statement)


def get_health_profile(
    db: Session,
    patient_id,
) -> HealthProfile | None:
    statement = select(HealthProfile).where(
        HealthProfile.patient_id == patient_id
    )

    return db.scalar(statement)


def create_health_profile(
    db: Session,
    patient: Patient,
    request: HealthProfileCreateRequest,
) -> HealthProfile:
    existing_profile = get_health_profile(
        db,
        patient.id,
    )

    if existing_profile:
        raise ValueError(
            "Health profile already exists for this patient."
        )

    profile = HealthProfile(
        patient_id=patient.id,
        height_cm=request.height_cm,
        weight_kg=request.weight_kg,
        blood_type=request.blood_type,
        smoking_status=request.smoking_status,
        activity_level=request.activity_level,
        family_history=request.family_history,
        existing_conditions=request.existing_conditions,
        current_medications=request.current_medications,
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return profile


def update_health_profile(
    db: Session,
    profile: HealthProfile,
    request: HealthProfileUpdateRequest,
) -> HealthProfile:
    update_data = request.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)

    return profile