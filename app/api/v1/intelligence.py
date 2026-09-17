from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.dependencies import get_database, require_role
from app.models.health_profile import HealthProfile
from app.models.lab_result import LabResult, LabTestType
from app.models.patient import Patient
from app.models.prediction import Prediction
from app.models.report import Report
from app.models.user import User, UserRole
from app.models.vital import Vital
from app.schemas.predictions import DashboardResponse, PredictionResponse, ReportResponse, RiskAnalysisRequest
from app.services.health_service import get_patient_by_user_id
from app.api.v1.clinicians import current_clinician, linked_patient_or_404
from app.ml.heart_disease.runtime import ModelInputError, ModelUnavailableError
from app.services.entitlement_service import get_effective_entitlement
from app.services.audit_service import record_auth_event_best_effort
from app.services.risk_analysis_service import ModelInactiveError, run_heart_analysis

router = APIRouter(tags=["Patient Intelligence"])


def patient_for(user: User, db: Session) -> Patient:
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    return patient


@router.post("/risk-analysis", response_model=PredictionResponse, status_code=201)
def risk_analysis(request: RiskAnalysisRequest,
                  user: User = Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN)),
                  db: Session = Depends(get_database)):
    if user.role == UserRole.PATIENT:
        patient = patient_for(user, db)
        if request.patient_id is not None and request.patient_id != patient.id:
            record_auth_event_best_effort(db, "UNAUTHORIZED_ACCESS_ATTEMPT", user.id, "failure")
            raise HTTPException(status_code=404, detail="Patient profile not found.")
        if get_effective_entitlement(db, patient.id) is None:
            raise HTTPException(status_code=403, detail="An active access entitlement is required.")
    else:
        clinician = current_clinician(user, db)
        if request.patient_id is None:
            raise HTTPException(status_code=422, detail="patient_id is required for clinician analysis.")
        patient = linked_patient_or_404(db, clinician.id, request.patient_id)
        if not patient.user.is_active:
            raise HTTPException(status_code=403, detail="Patient account is inactive.")
    try:
        return run_heart_analysis(db, patient, user.id)
    except ModelInputError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail={
            "code": "MODEL_INPUT_INCOMPLETE" if exc.missing else "VALIDATION_ERROR",
            "status": "insufficient_data" if exc.missing else "invalid_data",
            "model": request.model,
            "missing_fields" if exc.missing else "invalid_fields": exc.fields,
            "message": ("Additional health information is required before Heart Disease risk can be calculated."
                        if exc.missing else "Required Heart Disease inputs are invalid or use unsupported units."),
        }) from None
    except ModelInactiveError:
        db.rollback()
        raise HTTPException(status_code=503, detail={"code": "MODEL_INACTIVE", "message": "Heart Disease model is inactive."}) from None
    except (ModelUnavailableError, SQLAlchemyError):
        db.rollback()
        raise HTTPException(status_code=503, detail={"code": "MODEL_UNAVAILABLE", "message": "Heart Disease analysis is temporarily unavailable."}) from None


@router.get("/predictions", response_model=list[PredictionResponse])
def predictions(limit: int = Query(50, ge=1, le=100), user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = patient_for(user, db)
    return list(db.scalars(select(Prediction).where(Prediction.patient_id == patient.id).order_by(Prediction.predicted_at.desc()).limit(limit)).all())


@router.get("/predictions/{prediction_id}", response_model=PredictionResponse)
def prediction(prediction_id: UUID, user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = patient_for(user, db)
    result = db.scalar(select(Prediction).where(Prediction.id == prediction_id, Prediction.patient_id == patient.id))
    if result is None:
        raise HTTPException(status_code=404, detail="Prediction not found.")
    return result


@router.get("/reports", response_model=list[ReportResponse])
def reports(limit: int = Query(50, ge=1, le=100), user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = patient_for(user, db)
    return list(db.scalars(select(Report).where(Report.patient_id == patient.id).order_by(Report.generated_at.desc()).limit(limit)).all())


@router.get("/reports/{report_id}", response_model=ReportResponse)
def report(report_id: UUID, user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = patient_for(user, db)
    result = db.scalar(select(Report).where(Report.id == report_id, Report.patient_id == patient.id))
    if result is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return result


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = patient_for(user, db)
    profile = db.scalar(select(HealthProfile).where(HealthProfile.patient_id == patient.id))
    vital = db.scalar(select(Vital).where(Vital.patient_id == patient.id).order_by(Vital.recorded_at.desc()).limit(1))
    glucose = db.scalar(select(LabResult).where(LabResult.patient_id == patient.id, LabResult.test_type == LabTestType.GLUCOSE).order_by(LabResult.measured_at.desc()).limit(1))
    latest = list(db.scalars(select(Prediction).where(Prediction.patient_id == patient.id).order_by(Prediction.predicted_at.desc()).limit(5)).all())
    return DashboardResponse(
        bmi=profile.bmi if profile else None,
        latest_systolic_bp=vital.blood_pressure_systolic if vital else None,
        latest_diastolic_bp=vital.blood_pressure_diastolic if vital else None,
        latest_glucose=glucose.value if glucose else None,
        prediction_count=db.scalar(select(func.count(Prediction.id)).where(Prediction.patient_id == patient.id)) or 0,
        latest_predictions=latest,
    )


@router.get("/health/trends")
def health_trends(limit: int = Query(50, ge=1, le=200), user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = patient_for(user, db)
    vitals = db.scalars(select(Vital).where(Vital.patient_id == patient.id).order_by(Vital.recorded_at.desc()).limit(limit)).all()
    glucose = db.scalars(select(LabResult).where(LabResult.patient_id == patient.id, LabResult.test_type == LabTestType.GLUCOSE).order_by(LabResult.measured_at.desc()).limit(limit)).all()
    profile = db.scalar(select(HealthProfile).where(HealthProfile.patient_id == patient.id))
    return {
        "blood_pressure": [
            {"recorded_at": item.recorded_at, "systolic": item.blood_pressure_systolic, "diastolic": item.blood_pressure_diastolic}
            for item in vitals
            if item.blood_pressure_systolic is not None or item.blood_pressure_diastolic is not None
        ],
        "glucose": [{"measured_at": item.measured_at, "value": item.value, "unit": item.unit} for item in glucose],
        "current_bmi": profile.bmi if profile else None,
    }
