from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.vital import Vital
from app.schemas.vitals import VitalCreateRequest
from app.services.audit_service import add_audit_event


def get_patient_by_user_id(
    db: Session,
    user_id,
) -> Patient | None:
    statement = select(Patient).where(
        Patient.user_id == user_id
    )

    return db.scalar(statement)


def create_vital(
    db: Session,
    patient: Patient,
    request: VitalCreateRequest,
) -> Vital:
    recorded_at = request.recorded_at or datetime.now(timezone.utc)

    vital = Vital(
        patient_id=patient.id,
        heart_rate=request.heart_rate,
        oxygen_saturation=request.oxygen_saturation,
        temperature=request.temperature,
        blood_pressure_systolic=request.blood_pressure_systolic,
        blood_pressure_diastolic=request.blood_pressure_diastolic,
        recorded_at=recorded_at,
    )

    db.add(vital)
    db.flush()
    add_audit_event(db, "VITAL_CREATED", user_id=patient.user_id, resource_type="vital", resource_id=str(vital.id))
    db.commit()
    db.refresh(vital)

    return vital


def get_patient_vitals(
    db: Session,
    patient_id,
    limit: int = 50,
) -> list[Vital]:
    statement = (
        select(Vital)
        .where(Vital.patient_id == patient_id)
        .order_by(Vital.recorded_at.desc())
        .limit(limit)
    )

    return list(db.scalars(statement).all())


def get_latest_vital(
    db: Session,
    patient_id,
) -> Vital | None:
    statement = (
        select(Vital)
        .where(Vital.patient_id == patient_id)
        .order_by(Vital.recorded_at.desc())
        .limit(1)
    )

    return db.scalar(statement)


def create_vital_batch(
    db: Session,
    patient: Patient,
    requests: list[VitalCreateRequest],
) -> list[Vital]:
    vitals = []

    for request in requests:
        recorded_at = request.recorded_at or datetime.now(timezone.utc)

        vital = Vital(
            patient_id=patient.id,
            heart_rate=request.heart_rate,
            oxygen_saturation=request.oxygen_saturation,
            temperature=request.temperature,
            blood_pressure_systolic=request.blood_pressure_systolic,
            blood_pressure_diastolic=request.blood_pressure_diastolic,
            recorded_at=recorded_at,
        )

        vitals.append(vital)

    db.add_all(vitals)
    db.flush()
    for vital in vitals:
        add_audit_event(db, "VITAL_CREATED", user_id=patient.user_id, resource_type="vital", resource_id=str(vital.id), details={"batch": True})
    db.commit()

    for vital in vitals:
        db.refresh(vital)

    return vitals
