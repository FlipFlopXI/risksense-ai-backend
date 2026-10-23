from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from fastapi import HTTPException
from pydantic import ValidationError
from app.schemas.reproductive import CONTEXT_FIELDS, ReproductiveFields

from app.models.health_profile import HealthProfile
from app.models.body_measurement import BodyMeasurement
from app.models.patient import Patient
from app.schemas.health import (
    HealthProfileCreateRequest,
    HealthProfileUpdateRequest,
)
from app.services.audit_service import add_audit_event


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
        waist_circumference_cm=request.waist_circumference_cm,
        blood_type=request.blood_type,
        smoking_status=request.smoking_status,
        activity_level=request.activity_level,
        alcohol_status=request.alcohol_status,
        family_history_diabetes=request.family_history_diabetes,
        family_history_heart_disease=request.family_history_heart_disease,
        family_history_hypertension=request.family_history_hypertension,
        family_history=request.family_history,
        existing_conditions=request.existing_conditions,
        current_medications=request.current_medications,
        **request.model_dump(include=CONTEXT_FIELDS),
    )

    db.add(profile)
    db.flush()
    if any(value is not None for value in (request.height_cm, request.weight_kg, request.waist_circumference_cm)):
        db.add(BodyMeasurement(
            patient_id=patient.id, height_cm=request.height_cm, weight_kg=request.weight_kg,
            waist_circumference_cm=request.waist_circumference_cm, source="health_profile",
            measured_at=request.body_measurement_at or datetime.now(timezone.utc),
        ))
    if any(getattr(profile, field) is not None for field in CONTEXT_FIELDS):
        profile.pregnancy_context_updated_at = datetime.now(timezone.utc)
        add_audit_event(db, "PREGNANCY_CONTEXT_UPDATED", user_id=patient.user_id, resource_type="health_profile", resource_id=str(profile.id))
    add_audit_event(db, "HEALTH_PROFILE_CREATED", user_id=patient.user_id, resource_type="health_profile", resource_id=str(profile.id))
    db.commit()
    db.refresh(profile)

    return profile


def update_health_profile(
    db: Session,
    profile: HealthProfile,
    request: HealthProfileUpdateRequest,
) -> HealthProfile:
    update_data = request.model_dump(exclude_unset=True)
    measurement_at = update_data.pop("body_measurement_at", None)
    if CONTEXT_FIELDS.intersection(update_data):
        merged = {field: update_data.get(field, getattr(profile, field)) for field in CONTEXT_FIELDS}
        try:
            ReproductiveFields.model_validate(merged)
        except ValidationError:
            raise HTTPException(422, detail={"code": "VALIDATION_ERROR", "message": "Reproductive context is inconsistent; check status and dates."}) from None
        profile.pregnancy_context_updated_at = datetime.now(timezone.utc)
        add_audit_event(db, "PREGNANCY_CONTEXT_UPDATED", user_id=profile.patient.user_id, resource_type="health_profile", resource_id=str(profile.id))

    for field, value in update_data.items():
        setattr(profile, field, value)

    body_fields = {field: update_data[field] for field in ("height_cm", "weight_kg", "waist_circumference_cm") if field in update_data}
    if any(value is not None for value in body_fields.values()):
        db.add(BodyMeasurement(patient_id=profile.patient_id, source="health_profile",
                               measured_at=measurement_at or datetime.now(timezone.utc), **body_fields))

    add_audit_event(db, "HEALTH_PROFILE_UPDATED", user_id=profile.patient.user_id, resource_type="health_profile", resource_id=str(profile.id))

    db.commit()
    db.refresh(profile)

    return profile
