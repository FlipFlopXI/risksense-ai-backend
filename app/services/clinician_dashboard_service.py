"""Read-only summaries restricted to one clinician's active patient links."""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.drug_chat import DrugChatMessage, DrugChatSession
from app.models.health_profile import HealthProfile
from app.models.lab_result import LabResult
from app.models.patient import Patient
from app.models.patient_clinician import PatientClinician, PatientClinicianStatus
from app.models.prediction import Prediction
from app.models.vital import Vital
from app.schemas.predictions import PredictionResponse


def _prediction(row: Prediction) -> dict:
    return PredictionResponse.model_validate(row).model_dump(mode="json")


def _patient(row: Patient) -> dict:
    return {
        "id": str(row.id), "first_name": row.first_name, "last_name": row.last_name,
        "date_of_birth": row.date_of_birth.isoformat() if row.date_of_birth else None,
        "gender": row.gender, "ethnicity": row.ethnicity,
    }


def dashboard(db: Session, clinician_id: UUID) -> dict:
    patients = list(db.scalars(select(Patient).join(PatientClinician).where(
        PatientClinician.clinician_id == clinician_id,
        PatientClinician.status == PatientClinicianStatus.ACTIVE,
    ).order_by(Patient.last_name, Patient.first_name)).all())
    ids = [patient.id for patient in patients]
    predictions = (list(db.scalars(select(Prediction).where(Prediction.patient_id.in_(ids))
                        .order_by(Prediction.predicted_at.desc())).all()) if ids else [])
    by_patient: dict[UUID, list[Prediction]] = {patient.id: [] for patient in patients}
    for prediction in predictions:
        by_patient[prediction.patient_id].append(prediction)
    today = datetime.now(timezone.utc).date()
    cases = []
    alerts = []
    overviews = []
    for patient in patients:
        latest_by_target = {}
        for prediction in by_patient[patient.id]:
            latest_by_target.setdefault(prediction.prediction_target, prediction)
        elevated = [row for row in latest_by_target.values()
                    if row.risk_classification.lower() == "elevated"]
        overviews.append({
            "patient": _patient(patient),
            "latest_prediction": _prediction(by_patient[patient.id][0]) if by_patient[patient.id] else None,
            "latest_diabetes": _prediction(latest_by_target["diabetes_risk"]) if "diabetes_risk" in latest_by_target else None,
            "latest_heart": _prediction(latest_by_target["heart_disease"]) if "heart_disease" in latest_by_target else None,
            "high_alert": bool(elevated),
        })
        for prediction in by_patient[patient.id][:1]:
            case = {"patient": _patient(patient), "prediction": _prediction(prediction)}
            cases.append(case)
        if elevated:
            alert = max(elevated, key=lambda row: row.predicted_at)
            alerts.append({"patient": _patient(patient), "prediction": _prediction(alert)})
    cases.sort(key=lambda item: item["prediction"]["predicted_at"], reverse=True)
    alerts.sort(key=lambda item: item["prediction"]["predicted_at"], reverse=True)
    enquiries = (db.scalar(select(func.count(DrugChatMessage.id)).join(
        DrugChatSession, DrugChatMessage.session_id == DrugChatSession.id).where(
        DrugChatSession.patient_id.in_(ids), DrugChatMessage.role == "user")) or 0) if ids else 0
    return {
        "total_patients": len(patients), "high_risk_alerts": len(alerts),
        "predictions_today": sum(item.predicted_at.date() == today for item in predictions),
        "recent_cases": cases[:5], "alerts": alerts, "patients": overviews,
        "drug_enquiries": enquiries,
    }


def patient_summary(db: Session, patient: Patient) -> dict:
    profile = db.scalar(select(HealthProfile).where(HealthProfile.patient_id == patient.id))
    heart_vital = db.scalar(select(Vital).where(
        Vital.patient_id == patient.id, Vital.heart_rate.is_not(None))
        .order_by(Vital.recorded_at.desc()).limit(1))
    bp_vital = db.scalar(select(Vital).where(
        Vital.patient_id == patient.id,
        Vital.blood_pressure_systolic.is_not(None),
        Vital.blood_pressure_diastolic.is_not(None))
        .order_by(Vital.recorded_at.desc()).limit(1))
    labs = list(db.scalars(select(LabResult).where(LabResult.patient_id == patient.id)
                           .order_by(LabResult.measured_at.desc())).all())
    latest_labs = {}
    for lab in labs:
        key = lab.test_type.value if hasattr(lab.test_type, "value") else str(lab.test_type)
        latest_labs.setdefault(key, {"value": lab.value, "unit": lab.unit,
                                     "measured_at": lab.measured_at.isoformat()})
    predictions = list(db.scalars(select(Prediction).where(Prediction.patient_id == patient.id)
                                  .order_by(Prediction.predicted_at.desc())).all())
    latest = {}
    for item in predictions:
        latest.setdefault(item.prediction_target, _prediction(item))
    enquiries = db.scalar(select(func.count(DrugChatMessage.id)).join(
        DrugChatSession, DrugChatMessage.session_id == DrugChatSession.id).where(
        DrugChatSession.patient_id == patient.id, DrugChatMessage.role == "user")) or 0
    timestamps = [profile.updated_at] if profile and profile.updated_at else []
    timestamps += [item.recorded_at for item in (heart_vital, bp_vital) if item]
    timestamps += [datetime.fromisoformat(item["measured_at"]) for item in latest_labs.values()]
    return {
        "patient": _patient(patient),
        "profile": {"bmi": profile.bmi, "height_cm": profile.height_cm,
                    "weight_kg": profile.weight_kg} if profile else None,
        "latest_vital": {"heart_rate": heart_vital.heart_rate if heart_vital else None,
                         "heart_rate_recorded_at": heart_vital.recorded_at.isoformat() if heart_vital else None,
                         "blood_pressure_systolic": bp_vital.blood_pressure_systolic if bp_vital else None,
                         "blood_pressure_diastolic": bp_vital.blood_pressure_diastolic if bp_vital else None,
                         "blood_pressure_recorded_at": bp_vital.recorded_at.isoformat() if bp_vital else None},
        "latest_labs": latest_labs, "latest_predictions": latest,
        "drug_enquiry_count": enquiries,
        "clinical_data_updated_at": max(timestamps).isoformat() if timestamps else None,
    }
