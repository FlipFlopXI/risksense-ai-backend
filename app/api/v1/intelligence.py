from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import get_database, require_role
from app.models.health_profile import HealthProfile
from app.models.lab_result import LabResult, LabTestType
from app.models.patient import Patient
from app.models.prediction import Prediction
from app.models.report import Report
from app.models.user import User, UserRole
from app.models.vital import Vital
from app.schemas.predictions import DashboardResponse, PredictionResponse, ReportResponse
from app.services.health_service import get_patient_by_user_id

router = APIRouter(tags=["Patient Intelligence"])


def patient_for(user: User, db: Session) -> Patient:
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    return patient


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
