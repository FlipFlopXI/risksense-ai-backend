from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect, select
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
from app.schemas.clinician_assessment import ClinicalAssessmentRequest, ClinicalAssessmentResponse, ClinicianPredictionDetail, ClinicianProfileUpdate
from app.services.audit_service import add_audit_event
from app.services.clinician_assessment_service import assess
from app.services.clinician_dashboard_service import dashboard as clinician_dashboard, patient_summary
from app.ml.common import ModelInputError, ModelUnavailableError
from app.ml.diabetes import runtime as diabetes_runtime
from app.ml.heart_disease import runtime as heart_runtime
from app.services.diabetes_service import MODEL_ID as DIABETES_MODEL_ID, MODEL_PATH as DIABETES_MODEL_PATH
from app.services.risk_analysis_service import MODEL_ID as HEART_MODEL_ID, MODEL_PATH as HEART_MODEL_PATH, ModelInactiveError, require_active_model

router = APIRouter(prefix="/clinicians", tags=["Clinicians"])


def current_clinician(user: User, db: Session) -> Clinician:
    clinician = db.scalar(select(Clinician).where(Clinician.user_id == user.id))
    if clinician is None:
        raise HTTPException(status_code=404, detail="Clinician profile not found.")
    if clinician.approval_status != ClinicianApprovalStatus.APPROVED:
        raise HTTPException(status_code=403, detail="Clinician account is not approved.")
    return clinician


def _has_clinician_gender_column(db: Session) -> bool:
    return any(column["name"] == "gender" for column in inspect(db.get_bind()).get_columns("clinicians"))


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


@router.get("/profile")
def profile(user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    clinician = current_clinician(user, db)
    return {
        "risk_sense_id": clinician.risk_sense_id,
        "first_name": clinician.first_name, "last_name": clinician.last_name,
        "professional_title": clinician.professional_title,
        "specialization": clinician.specialization, "institution": clinician.institution,
        "license_number": clinician.license_number, "email": user.email,
        "last_login_at": clinician.last_login_at,
        "gender": clinician.gender if _has_clinician_gender_column(db) else None,
        "approval_status": clinician.approval_status,
    }


@router.patch("/profile")
def update_profile_gender(request: ClinicianProfileUpdate, user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    clinician = current_clinician(user, db)
    if not _has_clinician_gender_column(db):
        raise HTTPException(status_code=503, detail="Clinician profile gender is unavailable until the pending database migration is applied.")
    clinician.gender = request.gender
    add_audit_event(db, "CLINICIAN_PROFILE_UPDATED", user_id=user.id,
                    resource_type="clinician", resource_id=str(clinician.id))
    db.commit()
    return profile(user, db)


@router.get("/dashboard")
def dashboard(user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    clinician = current_clinician(user, db)
    return clinician_dashboard(db, clinician.id)


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


@router.get("/patients/{patient_id}/summary")
def linked_patient_summary(patient_id: UUID, user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    clinician = current_clinician(user, db)
    patient = linked_patient_or_404(db, clinician.id, patient_id)
    return patient_summary(db, patient)


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


@router.get("/patients/{patient_id}/predictions/{prediction_id}", response_model=ClinicianPredictionDetail)
def linked_prediction(patient_id: UUID, prediction_id: UUID, user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    clinician = current_clinician(user, db)
    linked_patient_or_404(db, clinician.id, patient_id)
    prediction = db.scalar(select(Prediction).where(Prediction.id == prediction_id, Prediction.patient_id == patient_id))
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found.")
    return ClinicianPredictionDetail(
        prediction=PredictionResponse.model_validate(prediction),
        input_snapshot=prediction.input_data,
    )


@router.post("/assessment", response_model=ClinicalAssessmentResponse)
def clinical_assessment(request: ClinicalAssessmentRequest, user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    current_clinician(user, db)
    runtime = diabetes_runtime if request.model == "diabetes" else heart_runtime
    try:
        expected_id, expected_path = ((DIABETES_MODEL_ID, DIABETES_MODEL_PATH)
                                      if request.model == "diabetes" else (HEART_MODEL_ID, HEART_MODEL_PATH))
        _, loaded = require_active_model(db, runtime, expected_id, expected_path)
        return assess(request, loaded)
    except ModelInactiveError:
        raise HTTPException(status_code=503, detail={
            "code": "MODEL_INACTIVE", "message": "The selected model is not active.",
        }) from None
    except ModelInputError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "MODEL_INPUT_INCOMPLETE" if exc.missing else "VALIDATION_ERROR",
            "fields": exc.fields, "message": exc.message or "Required assessment inputs are missing or invalid.",
        }) from None
    except ModelUnavailableError:
        raise HTTPException(status_code=503, detail="The selected model is unavailable.") from None


@router.delete("/patients/{patient_id}/link", status_code=204)
def unlink_patient(patient_id: UUID, user: User = Depends(require_role(UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    clinician = current_clinician(user, db)
    link = get_patient_clinician(db, patient_id, clinician.id)
    if link is None or link.status != PatientClinicianStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="Active patient link not found.")
    unlink_patient_clinician(db, link, user.id)
    db.commit()
