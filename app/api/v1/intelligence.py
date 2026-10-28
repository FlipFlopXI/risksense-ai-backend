from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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
from app.models.body_measurement import BodyMeasurement
from app.models.drug_chat import DrugChatMessage, DrugChatSession
from app.schemas.predictions import DashboardResponse, PredictionResponse, ReportGenerateRequest, ReportResponse, RiskAnalysisRequest
from app.services.health_service import get_patient_by_user_id
from app.api.v1.clinicians import current_clinician, linked_patient_or_404
from app.ml.common import ModelInputError, ModelUnavailableError
from app.services.entitlement_service import get_effective_entitlement
from app.services.audit_service import add_audit_event, record_auth_event_best_effort
from app.services.risk_analysis_service import ModelInactiveError, run_heart_analysis
from app.services.diabetes_service import run_diabetes_analysis
from app.services.clinical_access_service import authorize_patient
from app.services.report_service import create_report, render_report_pdf

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
    label = "Heart Disease" if request.model == "heart_disease" else "Diabetes"
    try:
        runner = run_heart_analysis if request.model == "heart_disease" else run_diabetes_analysis
        if request.model == "heart_disease":
            return runner(db, patient, user.id,
                          fasting_glucose=request.fasting_glucose,
                          total_cholesterol=request.total_cholesterol)
        return runner(db, patient, user.id)
    except ModelInputError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail={
            "code": "MODEL_INPUT_INCOMPLETE" if exc.missing else "VALIDATION_ERROR",
            "status": "insufficient_data" if exc.missing else "invalid_data",
            "model": request.model,
            "missing_fields" if exc.missing else "invalid_fields": exc.fields,
            "message": exc.message or (f"Additional health information is required before {label} risk can be calculated."
                        if exc.missing else f"Required {label} inputs are invalid or use unsupported units."),
        }) from None
    except ModelInactiveError:
        db.rollback()
        raise HTTPException(status_code=503, detail={"code": "MODEL_INACTIVE", "message": f"{label} model is inactive."}) from None
    except (ModelUnavailableError, SQLAlchemyError):
        db.rollback()
        raise HTTPException(status_code=503, detail={"code": "MODEL_UNAVAILABLE", "message": f"{label} analysis is temporarily unavailable."}) from None


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


@router.post("/reports", response_model=ReportResponse, status_code=201)
def generate_report(request: ReportGenerateRequest, user: User = Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN)),
                    db: Session = Depends(get_database)):
    patient = authorize_patient(db, user, request.patient_id, chat=False)
    try:
        return create_report(db, patient, request.prediction_id, user.id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Prediction not found.") from None


@router.get("/reports", response_model=list[ReportResponse])
def reports(patient_id: UUID | None = None, limit: int = Query(50, ge=1, le=100),
            user: User = Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    patient = authorize_patient(db, user, patient_id, chat=False)
    return list(db.scalars(select(Report).where(Report.patient_id == patient.id).order_by(Report.generated_at.desc()).limit(limit)).all())


@router.get("/reports/{report_id}", response_model=ReportResponse)
def report(report_id: UUID, user: User = Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    result = db.get(Report, report_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    authorize_patient(db, user, result.patient_id, chat=False)
    return result


@router.get("/reports/{report_id}/pdf", response_class=Response)
def report_pdf(report_id: UUID, user: User = Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN)),
               db: Session = Depends(get_database)):
    result = db.get(Report, report_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    authorize_patient(db, user, result.patient_id, chat=False)
    pdf = render_report_pdf(result)
    add_audit_event(db, "REPORT_DOWNLOADED", user_id=user.id, resource_type="report", resource_id=str(result.id))
    db.commit()
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="risksense-report-{result.id}.pdf"'})


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = patient_for(user, db)
    profile = db.scalar(select(HealthProfile).where(HealthProfile.patient_id == patient.id))
    body = db.scalar(select(BodyMeasurement).where(BodyMeasurement.patient_id == patient.id).order_by(BodyMeasurement.measured_at.desc()).limit(1))
    vital = db.scalar(select(Vital).where(Vital.patient_id == patient.id, Vital.blood_pressure_systolic.is_not(None), Vital.blood_pressure_diastolic.is_not(None)).order_by(Vital.recorded_at.desc()).limit(1))
    glucose = db.scalar(select(LabResult).where(LabResult.patient_id == patient.id, LabResult.test_type.in_((LabTestType.GLUCOSE, LabTestType.FASTING_GLUCOSE))).order_by(LabResult.measured_at.desc()).limit(1))
    latest = []
    for target in ("diabetes_risk", "heart_disease"):
        item = db.scalar(select(Prediction).where(Prediction.patient_id == patient.id, Prediction.prediction_target == target).order_by(Prediction.predicted_at.desc()).limit(1))
        if item is not None:
            latest.append(item)
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    enquiry_count = db.scalar(select(func.count(DrugChatMessage.id)).join(DrugChatSession, DrugChatMessage.session_id == DrugChatSession.id).where(DrugChatSession.patient_id == patient.id, DrugChatMessage.role == "user", DrugChatMessage.created_at >= today_start)) or 0
    timestamps = [item.predicted_at for item in latest]
    timestamps += [value for value in (body.measured_at if body else None, vital.recorded_at if vital else None, glucose.measured_at if glucose else None) if value is not None]
    return DashboardResponse(
        patient_first_name=patient.first_name,
        bmi=profile.bmi if profile else None,
        bmi_measured_at=body.measured_at if body else (profile.updated_at if profile else None),
        latest_systolic_bp=vital.blood_pressure_systolic if vital else None,
        latest_diastolic_bp=vital.blood_pressure_diastolic if vital else None,
        blood_pressure_recorded_at=vital.recorded_at if vital else None,
        latest_glucose=glucose.value if glucose else None,
        latest_glucose_unit=glucose.unit if glucose else None,
        glucose_measured_at=glucose.measured_at if glucose else None,
        prediction_count=db.scalar(select(func.count(Prediction.id)).where(Prediction.patient_id == patient.id, Prediction.predicted_at >= month_start)) or 0,
        latest_predictions=latest,
        drug_response_enquiries_today=enquiry_count,
        last_updated_at=max(timestamps) if timestamps else None,
    )


@router.get("/health/trends")
def health_trends(limit: int = Query(50, ge=1, le=200), user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = patient_for(user, db)
    vitals = db.scalars(select(Vital).where(Vital.patient_id == patient.id).order_by(Vital.recorded_at.desc()).limit(limit)).all()
    labs = db.scalars(select(LabResult).where(
        LabResult.patient_id == patient.id,
        LabResult.test_type.in_((LabTestType.FASTING_GLUCOSE, LabTestType.TOTAL_CHOLESTEROL)),
    ).order_by(LabResult.measured_at.desc()).limit(limit * 2)).all()
    body = list(reversed(list(db.scalars(select(BodyMeasurement).where(BodyMeasurement.patient_id == patient.id)
                                         .order_by(BodyMeasurement.measured_at.desc(), BodyMeasurement.id.desc()).limit(limit)).all())))
    last_height = None
    body_points = []
    for item in body:
        if item.height_cm is not None:
            last_height = item.height_cm
        bmi = round(item.weight_kg / ((last_height / 100) ** 2), 2) if item.weight_kg is not None and last_height else None
        body_points.append({"id": str(item.id), "measured_at": item.measured_at, "height_cm": item.height_cm,
                            "weight_kg": item.weight_kg, "waist_circumference_cm": item.waist_circumference_cm,
                            "bmi": bmi, "bmi_height_source": "latest_recorded_height_at_or_before_measurement" if bmi is not None else None})
    return {
        "blood_pressure": [
            {"recorded_at": item.recorded_at, "systolic": item.blood_pressure_systolic, "diastolic": item.blood_pressure_diastolic}
            for item in vitals
            if item.blood_pressure_systolic is not None or item.blood_pressure_diastolic is not None
        ],
        "heart_rate": [{"recorded_at": item.recorded_at, "value": item.heart_rate, "unit": "bpm"} for item in vitals if item.heart_rate is not None],
        "fasting_glucose": [{"measured_at": item.measured_at, "value": item.value, "unit": item.unit} for item in labs if item.test_type == LabTestType.FASTING_GLUCOSE],
        "total_cholesterol": [{"measured_at": item.measured_at, "value": item.value, "unit": item.unit} for item in labs if item.test_type == LabTestType.TOTAL_CHOLESTEROL],
        "body_measurements": body_points,
    }
