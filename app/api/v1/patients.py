from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.dependencies import get_database, require_role
from app.models.user import User, UserRole
from app.schemas.users import PatientResponse, PatientUpdateRequest
from app.services.health_service import get_patient_by_user_id
from app.models.patient_clinician import PatientClinician, PatientClinicianStatus
from app.models.clinician import Clinician, ClinicianApprovalStatus
from app.schemas.access import MyClinicianResponse

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


@router.get("/me/clinician", response_model=MyClinicianResponse)
def my_clinician(user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    row = db.execute(select(PatientClinician, Clinician).join(
        Clinician, Clinician.id == PatientClinician.clinician_id
    ).where(PatientClinician.patient_id == patient.id,
            PatientClinician.status == PatientClinicianStatus.ACTIVE,
            Clinician.approval_status == ClinicianApprovalStatus.APPROVED)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Active clinician relationship not found.")
    link, clinician = row
    return MyClinicianResponse(
        relationship_id=link.id, relationship_status=link.status, linked_at=link.linked_at,
        risk_sense_id=clinician.risk_sense_id,
        display_name=f"{clinician.first_name} {clinician.last_name}",
        professional_title=clinician.professional_title, specialization=clinician.specialization,
        institution=clinician.institution,
    )
