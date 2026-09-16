from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patient_clinician import PatientClinician, PatientClinicianStatus
from app.services.audit_service import add_audit_event


def get_patient_clinician(db: Session, patient_id: UUID, clinician_id: UUID) -> PatientClinician | None:
    return db.scalar(select(PatientClinician).where(PatientClinician.patient_id == patient_id, PatientClinician.clinician_id == clinician_id))


def link_patient_clinician(db: Session, patient_id: UUID, clinician_id: UUID, actor_id: UUID | None = None) -> PatientClinician:
    link = get_patient_clinician(db, patient_id, clinician_id)
    now = datetime.now(timezone.utc)
    if link:
        link.status = PatientClinicianStatus.ACTIVE
        link.linked_at = now
        link.unlinked_at = None
    else:
        link = PatientClinician(patient_id=patient_id, clinician_id=clinician_id, status=PatientClinicianStatus.ACTIVE, linked_at=now)
        db.add(link)
    db.flush()
    add_audit_event(db, "CLINICIAN_LINKED", user_id=actor_id, resource_type="patient_clinician", resource_id=str(link.id))
    return link


def unlink_patient_clinician(db: Session, link: PatientClinician, actor_id: UUID | None = None) -> PatientClinician:
    link.status = PatientClinicianStatus.INACTIVE
    link.unlinked_at = datetime.now(timezone.utc)
    add_audit_event(db, "CLINICIAN_UNLINKED", user_id=actor_id, resource_type="patient_clinician", resource_id=str(link.id))
    return link


def clinician_can_access_patient(db: Session, clinician_id: UUID, patient_id: UUID) -> bool:
    return db.scalar(select(PatientClinician.id).where(PatientClinician.patient_id == patient_id, PatientClinician.clinician_id == clinician_id, PatientClinician.status == PatientClinicianStatus.ACTIVE)) is not None
