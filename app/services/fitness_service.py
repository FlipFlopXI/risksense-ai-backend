from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.body_measurement import BodyMeasurement
from app.models.fitness import ActivityEntry, BodyCompositionEntry
from app.models.health_profile import HealthProfile
from app.models.patient import Patient
from app.schemas.fitness import ActivityCreate, ActivityDay, ActivitySummary, BodyCompositionCreate, BodySummary
from app.services.audit_service import add_audit_event
from app.services.nutrition_service import patient_for_user


def activity_summary(db: Session, patient: Patient, day: date) -> ActivitySummary:
    first = day - timedelta(days=6)
    rows = db.scalars(select(ActivityEntry).where(
        ActivityEntry.patient_id == patient.id,
        ActivityEntry.log_date >= first, ActivityEntry.log_date <= day,
    )).all()
    totals = {first + timedelta(days=i): ActivityDay(
        date=first + timedelta(days=i), steps=0, activity_minutes=0,
        activity_calories_kcal=0, distance_km=0) for i in range(7)}
    for row in rows:
        total = totals[row.log_date]
        total.steps += row.steps
        total.activity_minutes += row.activity_minutes
        total.activity_calories_kcal += row.activity_calories_kcal
        total.distance_km += row.distance_km
    return ActivitySummary(date=day, today=totals[day],
                           history=[totals[first + timedelta(days=i)] for i in range(7)])


def create_activity(db: Session, patient: Patient, user_id: UUID, request: ActivityCreate) -> ActivityEntry:
    entry = ActivityEntry(patient_id=patient.id, **request.model_dump())
    db.add(entry)
    db.flush()
    add_audit_event(db, "ACTIVITY_LOG_CREATED", user_id=user_id,
                    resource_type="activity_entry", resource_id=str(entry.id))
    db.commit()
    db.refresh(entry)
    return entry


def body_summary(db: Session, patient: Patient) -> BodySummary:
    profile = db.scalar(select(HealthProfile).where(HealthProfile.patient_id == patient.id))
    composition = db.scalar(select(BodyCompositionEntry).where(
        BodyCompositionEntry.patient_id == patient.id).order_by(
            BodyCompositionEntry.created_at.desc(), BodyCompositionEntry.id.desc()))
    from datetime import date
    dob = patient.date_of_birth
    today = date.today()
    age = (today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))) if dob else None
    pregnancy = profile.pregnancy_status if profile else None
    adult_reference = age is not None and age >= 20 and pregnancy not in {"PREGNANT", "POSSIBLY_PREGNANT"}
    return BodySummary(height_cm=profile.height_cm if profile else None,
                       weight_kg=profile.weight_kg if profile else None,
                       bmi=profile.bmi if profile else None, composition=composition,
                       adult_bmi_reference_applicable=adult_reference)


def update_weight(db: Session, patient: Patient, user_id: UUID, weight_kg: float) -> BodySummary:
    profile = db.scalar(select(HealthProfile).where(HealthProfile.patient_id == patient.id))
    if profile is None:
        raise HTTPException(404, "Complete your health profile before recording weight.")
    profile.weight_kg = weight_kg
    from datetime import datetime, timezone
    db.add(BodyMeasurement(patient_id=patient.id, weight_kg=weight_kg,
                           source="fitness", measured_at=datetime.now(timezone.utc)))
    add_audit_event(db, "WEIGHT_UPDATED", user_id=user_id,
                    resource_type="health_profile", resource_id=str(profile.id))
    db.commit()
    return body_summary(db, patient)


def create_composition(db: Session, patient: Patient, user_id: UUID,
                       request: BodyCompositionCreate) -> BodyCompositionEntry:
    profile = db.scalar(select(HealthProfile).where(HealthProfile.patient_id == patient.id))
    if profile is not None and profile.weight_kg is not None and request.skeletal_muscle_kg > profile.weight_kg:
        raise HTTPException(422, "Skeletal muscle cannot exceed the recorded weight.")
    entry = BodyCompositionEntry(patient_id=patient.id, **request.model_dump())
    db.add(entry)
    db.flush()
    add_audit_event(db, "BODY_COMPOSITION_RECORDED", user_id=user_id,
                    resource_type="body_composition", resource_id=str(entry.id))
    db.commit()
    db.refresh(entry)
    return entry
