"""Patient opt-in and post-commit delivery of elevated model estimates."""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.patient import Patient
from app.models.patient_notification_preference import PatientNotificationPreference
from app.models.prediction import Prediction
from app.services.audit_service import add_audit_event
from app.services.email_templates import elevated_risk_email
from app.services.registration_verification import send_transactional_email


logger = logging.getLogger(__name__)


class ResultEmailUnavailable(Exception):
    pass

FEATURE_LABELS = {
    "age": "Age",
    "sex": "Sex",
    "bmi": "BMI",
    "waist_circumference": "Waist circumference",
    "systolic_bp": "Systolic blood pressure",
    "diastolic_bp": "Diastolic blood pressure",
    "total_cholesterol": "Total cholesterol",
    "fasting_blood_sugar_high": "Fasting glucose category",
}


def email_enabled(db: Session, patient_id: UUID) -> bool:
    preference = db.get(PatientNotificationPreference, patient_id)
    return bool(preference and preference.email_elevated_results)


def set_email_enabled(db: Session, patient_id: UUID, actor_id: UUID, enabled: bool) -> bool:
    if enabled and (not settings.BREVO_API_KEY or not settings.BREVO_SENDER_EMAIL):
        raise ResultEmailUnavailable("Email delivery is not configured. Please try again later.")
    statement = insert(PatientNotificationPreference).values(
        patient_id=patient_id, email_elevated_results=enabled,
    ).on_conflict_do_update(
        index_elements=[PatientNotificationPreference.patient_id],
        set_={"email_elevated_results": enabled, "updated_at": func.now()},
    )
    db.execute(statement)
    add_audit_event(
        db, "RISK_RESULT_EMAIL_PREFERENCE_UPDATED", user_id=actor_id,
        resource_type="patient", resource_id=str(patient_id),
        details={"email_elevated_results": enabled},
    )
    db.commit()
    return enabled


def _contributing_factors(prediction: Prediction) -> list[tuple[str, str]]:
    factors = []
    for item in prediction.contributing_factors:
        feature = item.get("feature")
        direction = item.get("direction")
        if feature not in FEATURE_LABELS or direction not in {"raises", "lowers"}:
            continue
        factors.append((FEATURE_LABELS[feature], direction))
        if len(factors) == 4:
            break
    return factors


def send_elevated_result_if_enabled(db: Session, prediction: Prediction) -> None:
    """Send after prediction commit; delivery failure never changes the saved result."""
    if (prediction.prediction_target not in {"heart_disease", "diabetes_risk"}
            or prediction.risk_classification != "elevated" or prediction.risk_score is None):
        return
    try:
        if not email_enabled(db, prediction.patient_id):
            return
        patient = db.get(Patient, prediction.patient_id)
        if patient is None or not patient.user.is_active:
            return
        previous = db.scalar(select(Prediction).where(
            Prediction.patient_id == prediction.patient_id,
            Prediction.prediction_target == prediction.prediction_target,
            Prediction.id != prediction.id,
            Prediction.risk_score.is_not(None),
            Prediction.predicted_at <= prediction.predicted_at,
        ).order_by(Prediction.predicted_at.desc(), Prediction.created_at.desc(), Prediction.id.desc()).limit(1))
        model_name = "Heart Disease" if prediction.prediction_target == "heart_disease" else "Diabetes"
        content = elevated_risk_email(
            model_name=model_name, score=prediction.risk_score,
            factors=_contributing_factors(prediction),
            previous_score=previous.risk_score if previous else None,
            model_version_changed=bool(previous and previous.model_version != prediction.model_version),
        )
        send_transactional_email(patient.user.email, f"Your RiskSense AI {model_name} result", content)
        add_audit_event(db, "RISK_RESULT_EMAIL_SENT", user_id=patient.user_id,
                        resource_type="prediction", resource_id=str(prediction.id))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Elevated result email delivery failed for prediction %s (%s)",
                       prediction.id, type(exc).__name__)
        try:
            add_audit_event(db, "RISK_RESULT_EMAIL_FAILED", user_id=None,
                            resource_type="prediction", resource_id=str(prediction.id), status="failure")
            db.commit()
        except Exception:
            db.rollback()
