"""Diabetes data selection and inference using the existing registry and history."""
from datetime import datetime, timezone
import math
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.common import ModelInputError, completed_age, explain_logistic_features
from app.ml.diabetes import runtime
from app.models.health_profile import HealthProfile
from app.models.patient import Patient
from app.models.prediction import Prediction
from app.models.vital import Vital
from app.services.risk_analysis_service import activate_model, persist_prediction, require_active_model

MODEL_ID = uuid5(NAMESPACE_URL, f"risksense:diabetes:{runtime.ARTIFACT_SHA256}")
MODEL_PATH = "app/ml/diabetes/risksense_diabetes_model_v1.pkl"


def activate_diabetes_model(db: Session, actor_id: UUID):
    loaded = runtime.load_model()
    return activate_model(
        db, actor_id, loaded=loaded, model_id=MODEL_ID, target=runtime.TARGET,
        model_path=MODEL_PATH, name="RiskSense AI Diabetes Model",
        dataset=loaded.metadata["source_dataset"], disclaimer=runtime.DISCLAIMER, lock_key=7241902302,
    )


def profile_bmi(profile: HealthProfile | None) -> float | None:
    if profile is None or profile.height_cm is None or profile.weight_kg is None:
        return None
    # These explicitly named canonical fields use cm/kg. Validate legacy rows too.
    for value, upper in ((profile.height_cm, 300), (profile.weight_kg, 500)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= upper:
            raise ModelInputError(["bmi"], message="BMI requires valid positive height_cm and weight_kg measurements.")
    try:
        return profile.bmi  # Reuse the canonical, two-decimal BMI property.
    except (ArithmeticError, ValueError):
        raise ModelInputError(["bmi"]) from None


def run_diabetes_analysis(db: Session, patient: Patient, actor_id: UUID) -> Prediction:
    record, loaded = require_active_model(db, runtime, MODEL_ID, MODEL_PATH)
    now = datetime.now(timezone.utc)
    age = completed_age(patient.date_of_birth, now.date())
    profile = db.scalar(select(HealthProfile).where(HealthProfile.patient_id == patient.id))
    # Require a complete pair from one measurement; never mix separate readings.
    vital = db.scalar(select(Vital).where(
        Vital.patient_id == patient.id, Vital.recorded_at <= now,
        Vital.blood_pressure_systolic.is_not(None), Vital.blood_pressure_diastolic.is_not(None),
    ).order_by(Vital.recorded_at.desc(), Vital.created_at.desc(), Vital.id.desc()).limit(1))
    features = runtime.build_features(
        age=age, sex=patient.gender, bmi=profile_bmi(profile),
        waist_circumference=profile.waist_circumference_cm if profile else None,
        systolic_bp=vital.blood_pressure_systolic if vital else None,
        diastolic_bp=vital.blood_pressure_diastolic if vital else None,
    )
    probability, elevated = runtime.predict(features, loaded)
    factors = explain_logistic_features(features, loaded, "Diabetes")
    profile_source = {"id": str(profile.id), "updated_at": profile.updated_at.isoformat()}
    bp_source = {"id": str(vital.id), "recorded_at": vital.recorded_at.isoformat(), "unit": "mmHg"}
    result = Prediction(
        patient_id=patient.id, model_id=record.id, prediction_target=runtime.TARGET,
        risk_score=probability, risk_classification="elevated" if elevated else "standard",
        prediction_result=("Elevated predicted diabetes risk" if elevated
                           else "Predicted diabetes risk below the model threshold"),
        explanation=runtime.DISCLAIMER, predicted_at=now,
        input_data={
            "features": features.model_dump(), "feature_order": list(loaded.feature_order),
            "model_version": loaded.version, "decision_threshold": loaded.threshold,
            "artifact_sha256": loaded.artifact_hash,
            "contributing_factors": factors,
            "sources": {
                "age": {"source": "patient.date_of_birth", "as_of": now.date().isoformat()},
                "sex": {"source": "patient.gender", "value": patient.gender},
                "bmi": {**profile_source, "source": "health_profile.bmi", "unit": "kg/m^2",
                        "height_cm": profile.height_cm, "weight_kg": profile.weight_kg},
                "waist_circumference": {**profile_source, "source": "health_profile.waist_circumference_cm",
                                        "value": profile.waist_circumference_cm, "unit": "cm"},
                "systolic_bp": bp_source, "diastolic_bp": bp_source,
            },
        },
    )
    return persist_prediction(db, result, actor_id)
