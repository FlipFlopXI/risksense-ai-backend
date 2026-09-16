from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_database, require_role
from app.models.user import User, UserRole
from app.schemas.users import PatientResponse, PatientUpdateRequest
from app.services.health_service import get_patient_by_user_id

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.get("/me", response_model=PatientResponse)
def me(user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    return patient


@router.patch("/me", response_model=PatientResponse)
def update_me(request: PatientUpdateRequest, user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    for field, value in request.model_dump(exclude_unset=True).items():
        if isinstance(value, str):
            value = value.strip()
        setattr(patient, field, value)
    db.commit()
    db.refresh(patient)
    return patient
