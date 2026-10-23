"""Shared resource authorization for the new clinical features."""
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.api.v1.clinicians import current_clinician, linked_patient_or_404
from app.models.patient import Patient
from app.models.user import User, UserRole
from app.services.health_service import get_patient_by_user_id
from app.services.entitlement_service import get_effective_entitlement
from app.services.audit_service import record_auth_event_best_effort


def authorize_patient(db: Session, user: User, patient_id: UUID | None, *, chat: bool = False) -> Patient:
    try:
        if not user.is_active:
            raise HTTPException(401, detail="User account is inactive.")
        if user.role == UserRole.PATIENT:
            patient = get_patient_by_user_id(db, user.id)
            if patient is None or (patient_id is not None and patient_id != patient.id):
                raise HTTPException(404, detail="Patient resource not found.")
        elif user.role == UserRole.CLINICIAN:
            clinician = current_clinician(user, db)
            if patient_id is None:
                raise HTTPException(422, detail="patient_id is required for clinician access.")
            patient = linked_patient_or_404(db, clinician.id, patient_id)
            if not patient.user.is_active:
                raise HTTPException(404, detail="Patient resource not found.")
        else:
            raise HTTPException(403, detail="This role does not grant clinical access.")
        # The assistant artifact explicitly requires effective entitlement for patient-specific chat.
        if chat and get_effective_entitlement(db, patient.id) is None:
            raise HTTPException(403, detail="An active access entitlement is required.")
        return patient
    except HTTPException:
        record_auth_event_best_effort(db, "DRUG_CHAT_ACCESS_DENIED" if chat else "UNAUTHORIZED_ACCESS_ATTEMPT", user.id, "failure")
        raise
