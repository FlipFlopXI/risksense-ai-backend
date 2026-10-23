from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user, require_role
from app.api.v1.drug_assistant import assistant_database
from app.models.user import User, UserRole
from app.schemas.patient_medication import MedicationCreate, MedicationUpdate, MedicationResponse
from app.services import patient_medication_service as service

router = APIRouter(prefix="/patient-medications", tags=["Patient Medications"])


@router.get("", response_model=list[MedicationResponse])
def medications(patient_id: UUID | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                user: User = Depends(get_current_user), db: Session = Depends(assistant_database)):
    return service.list_medications(db, user, patient_id, limit, offset)


@router.get("/{medication_id}", response_model=MedicationResponse)
def medication(medication_id: UUID, patient_id: UUID | None = None, user: User = Depends(get_current_user), db: Session = Depends(assistant_database)):
    return service.medication_for(db, user, medication_id, patient_id)


@router.post("", response_model=MedicationResponse, status_code=201)
def create(request: MedicationCreate, user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(assistant_database)):
    return service.create_medication(db, user, request)


@router.patch("/{medication_id}", response_model=MedicationResponse)
def update(medication_id: UUID, request: MedicationUpdate, user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(assistant_database)):
    return service.update_medication(db, user, medication_id, request)


@router.delete("/{medication_id}", response_model=MedicationResponse)
def deactivate(medication_id: UUID, user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(assistant_database)):
    return service.update_medication(db, user, medication_id, MedicationUpdate(is_active=False))
