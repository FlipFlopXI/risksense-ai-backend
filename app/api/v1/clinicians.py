from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_database, require_role
from app.models.clinician import Clinician, ClinicianApprovalStatus
from app.models.patient import Patient
from app.models.patient_clinician import PatientClinician, PatientClinicianStatus
from app.models.user import User, UserRole
from app.schemas.access import ClinicianLookupResponse
from app.schemas.users import PatientResponse
from app.schemas.health import HealthProfileResponse
from app.schemas.vitals import VitalResponse
from app.schemas.labs import LabResultResponse
from app.schemas.predictions import PredictionResponse
from app.models.health_profile import HealthProfile
from app.models.vital import Vital
from app.models.lab_result import LabResult
from app.models.prediction import Prediction
from app.services.clinician_service import get_approved_clinician
from app.services.patient_clinician_service import get_patient_clinician, unlink_patient_clinician

router = APIRouter(prefix="/clinicians", tags=["Clinicians"])


class ClinicalAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    age: int | None = None
    sex: str | None = None
    heart_rate: float | None = None
    systolic_bp: float | None = None
    diastolic_bp: float | None = None
    glucose: float | None = None


def current_clinician(user: User, db: Session) -> Clinician:
    clinician = db.scalar(select(Clinician).where(Clinician.user_id == user.id))
    if clinician is None:
        raise HTTPException(status_code=404, detail="Clinician profile not found.")
    if clinician.approval_status != ClinicianApprovalStatus.APPROVED:
        raise HTTPException(status_code=403, detail="Clinician account is not approved.")
    return clinician


def linked_patient_or_404(db: Session, clinician_id: UUID, patient_id: UUID) -> Patient:
    patient = db.scalar(select(Patient).join(PatientClinician).where(Patient.id == patient_id, PatientClinician.clinician_id == clinician_id, PatientClinician.status == PatientClinicianStatus.ACTIVE))
    if patient is None:
        raise HTTPException(status_code=404, detail="Linked patient not found.")
    return patient


@router.get("/lookup/{risk_sense_id}", response_model=ClinicianLookupResponse)
def lookup(risk_sense_id: str, user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    clinician = get_approved_clinician(db, risk_sense_id)
    if clinician is None:
        raise HTTPException(status_code=404, detail="Approved clinician not found.")
    return clinician


@router.get("/me", response_model=ClinicianLookupResponse)
def me(user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    return current_clinician(user, db)


@router.get("/patients", response_model=list[PatientResponse])
def linked_patients(search: str | None = None, limit: int = Query(50, ge=1, le=100), user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    clinician = current_clinician(user, db)
    query = select(Patient).join(PatientClinician).where(PatientClinician.clinician_id == clinician.id, PatientClinician.status == PatientClinicianStatus.ACTIVE)
    if search:
        term = f"%{search.strip()}%"
        query = query.where((Patient.first_name.ilike(term)) | (Patient.last_name.ilike(term)))
    return list(db.scalars(query.order_by(Patient.last_name, Patient.first_name).limit(limit)).all())


@router.get("/patients/{patient_id}", response_model=PatientResponse)
def linked_patient(patient_id: UUID, user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    clinician = current_clinician(user, db)
    return linked_patient_or_404(db, clinician.id, patient_id)


@router.get("/patients/{patient_id}/health-profile", response_model=HealthProfileResponse)
def linked_health_profile(patient_id: UUID, user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    clinician = current_clinician(user, db)
    linked_patient_or_404(db, clinician.id, patient_id)
    profile = db.scalar(select(HealthProfile).where(HealthProfile.patient_id == patient_id))
    if profile is None:
        raise HTTPException(status_code=404, detail="Health profile not found.")
    return profile


@router.get("/patients/{patient_id}/vitals", response_model=list[VitalResponse])
def linked_vitals(patient_id: UUID, limit: int = Query(50, ge=1, le=100), user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    clinician = current_clinician(user, db)
    linked_patient_or_404(db, clinician.id, patient_id)
    return list(db.scalars(select(Vital).where(Vital.patient_id == patient_id).order_by(Vital.recorded_at.desc()).limit(limit)).all())


@router.get("/patients/{patient_id}/labs", response_model=list[LabResultResponse])
def linked_labs(patient_id: UUID, limit: int = Query(50, ge=1, le=100), user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    clinician = current_clinician(user, db)
    linked_patient_or_404(db, clinician.id, patient_id)
    return list(db.scalars(select(LabResult).where(LabResult.patient_id == patient_id).order_by(LabResult.measured_at.desc()).limit(limit)).all())


@router.get("/patients/{patient_id}/predictions", response_model=list[PredictionResponse])
def linked_predictions(patient_id: UUID, limit: int = Query(50, ge=1, le=100), user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    clinician = current_clinician(user, db)
    linked_patient_or_404(db, clinician.id, patient_id)
    return list(db.scalars(select(Prediction).where(Prediction.patient_id == patient_id).order_by(Prediction.predicted_at.desc()).limit(limit)).all())


@router.post("/assessment")
def clinical_assessment(request: ClinicalAssessmentRequest, user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    current_clinician(user, db)
    raise HTTPException(status_code=503, detail="No validated ML model is available; no assessment was persisted.")


@router.delete("/patients/{patient_id}/link", status_code=204)
def unlink_patient(patient_id: UUID, user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    clinician = current_clinician(user, db)
    link = get_patient_clinician(db, patient_id, clinician.id)
    if link is None or link.status != PatientClinicianStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="Active patient link not found.")
    unlink_patient_clinician(db, link, user.id)
    db.commit()
