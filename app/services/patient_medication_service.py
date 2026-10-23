from uuid import UUID
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.ml.drug_assistant.runtime import load_runtime, normalize
from app.models.patient_medication import PatientMedication
from app.models.user import User
from app.schemas.patient_medication import MedicationCreate, MedicationUpdate
from app.services.clinical_access_service import authorize_patient
from app.services.audit_service import add_audit_event


def catalogue_id(name: str) -> str | None:
    ids = load_runtime().aliases.get(normalize(name), ())
    return ids[0] if len(ids) == 1 else None


def list_medications(db: Session, user: User, patient_id: UUID | None, limit: int, offset: int):
    patient = authorize_patient(db, user, patient_id)
    return list(db.scalars(select(PatientMedication).where(PatientMedication.patient_id == patient.id)
                          .order_by(PatientMedication.created_at.desc(), PatientMedication.id).offset(offset).limit(limit)))


def medication_for(db: Session, user: User, medication_id: UUID, patient_id: UUID | None = None, lock: bool = False):
    patient = authorize_patient(db, user, patient_id)
    query = select(PatientMedication).where(PatientMedication.id == medication_id, PatientMedication.patient_id == patient.id)
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise HTTPException(404, detail="Medication record not found.")
    return row


def create_medication(db: Session, user: User, request: MedicationCreate):
    patient = authorize_patient(db, user, None)
    row = PatientMedication(patient_id=patient.id, drug_id=catalogue_id(request.display_name), **request.model_dump())
    db.add(row)
    db.flush()
    add_audit_event(db, "PATIENT_MEDICATION_CREATED", user_id=user.id, resource_type="patient_medication", resource_id=str(row.id))
    db.commit()
    db.refresh(row)
    return row


def update_medication(db: Session, user: User, medication_id: UUID, request: MedicationUpdate):
    row = medication_for(db, user, medication_id, lock=True)
    merged = {field: getattr(row, field) for field in MedicationCreate.model_fields}
    previous = dict(merged)
    merged.update(request.model_dump(exclude_unset=True))
    try:
        valid = MedicationCreate.model_validate(merged)
    except ValidationError:
        raise HTTPException(422, detail={"code": "VALIDATION_ERROR", "message": "Medication name, dates or fields are invalid."}) from None
    new_id = catalogue_id(valid.display_name)
    if previous == valid.model_dump() and row.drug_id == new_id:
        return row
    for field, value in valid.model_dump().items():
        setattr(row, field, value)
    row.drug_id = new_id
    event = "PATIENT_MEDICATION_DEACTIVATED" if previous["is_active"] and not row.is_active else "PATIENT_MEDICATION_UPDATED"
    add_audit_event(db, event, user_id=user.id, resource_type="patient_medication", resource_id=str(row.id))
    db.commit()
    db.refresh(row)
    return row
