"""Heart Disease inference using existing patient, registry and prediction records."""
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ml.heart_disease import runtime
from app.ml.common import explain_logistic_features
from app.models.model import Model
from app.models.patient import Patient
from app.models.prediction import Prediction
from app.models.vital import Vital
from app.services.audit_service import add_audit_event


MODEL_ID = uuid5(NAMESPACE_URL, f"risksense:heart_disease:{runtime.ARTIFACT_SHA256}")
MODEL_PATH = "app/ml/heart_disease/risksense_heart_disease_model_v1.pkl"


class ModelInactiveError(Exception):
    pass


def activate_heart_model(db: Session, actor_id: UUID) -> Model:
    loaded = runtime.load_model()
    return activate_model(
        db, actor_id, loaded=loaded, model_id=MODEL_ID, target=runtime.TARGET,
        model_path=MODEL_PATH, name=loaded.metadata["model_name"],
        dataset=loaded.metadata["dataset"], disclaimer=runtime.DISCLAIMER, lock_key=7241902301,
    )


def activate_model(db: Session, actor_id: UUID, *, loaded, model_id: UUID, target: str,
                   model_path: str, name: str, dataset: str, disclaimer: str, lock_key: int) -> Model:
    # Serialize registration across workers without adding a duplicate registry.
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    active = db.scalars(select(Model).where(
        Model.prediction_target == target, Model.is_active.is_(True),
    )).all()
    if any(row.id != model_id for row in active):
        raise runtime.ModelUnavailableError("A different version of this target is active.")
    record = db.get(Model, model_id)
    if record is None:
        record = Model(
            id=model_id, name=name, version=loaded.version,
            prediction_target=target, algorithm="LogisticRegression",
            dataset_name=dataset, model_path=model_path,
            description=disclaimer, is_active=True,
        )
        db.add(record)
    else:
        _validate_registry(record, loaded, model_id, target, model_path)
        record.is_active = True
    db.flush()
    add_audit_event(db, "MODEL_ACTIVATED", user_id=actor_id, resource_type="ml_model",
                    resource_id=str(record.id), details={"target": target, "version": loaded.version})
    db.commit()
    db.refresh(record)
    return record


def _validate_registry(record: Model, loaded: runtime.LoadedModel, model_id=MODEL_ID,
                       target=runtime.TARGET, model_path=MODEL_PATH) -> None:
    if (record.id != model_id or record.version != loaded.version
            or record.prediction_target != target
            or record.algorithm != "LogisticRegression" or record.model_path != model_path):
        raise runtime.ModelUnavailableError("Model registry configuration is incompatible.")


def require_active_model(db: Session, model_runtime, model_id: UUID, model_path: str):
    records = db.scalars(select(Model).where(
        Model.prediction_target == model_runtime.TARGET, Model.is_active.is_(True),
    ).with_for_update()).all()
    if not records:
        raise ModelInactiveError
    if len(records) != 1:
        raise runtime.ModelUnavailableError("Ambiguous active model configuration.")
    loaded = model_runtime.load_model()
    _validate_registry(records[0], loaded, model_id, model_runtime.TARGET, model_path)
    return records[0], loaded


def run_heart_analysis(db: Session, patient: Patient, actor_id: UUID, *,
                       fasting_glucose: float | None = None,
                       total_cholesterol: float | None = None) -> Prediction:
    record, loaded = require_active_model(db, runtime, MODEL_ID, MODEL_PATH)
    now = datetime.now(timezone.utc)
    age = None
    if patient.date_of_birth is not None:
        today = now.date()
        born = patient.date_of_birth
        if born > today:
            raise runtime.ModelInputError(["age"])
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    vital = db.scalar(select(Vital).where(
        Vital.patient_id == patient.id, Vital.blood_pressure_systolic.is_not(None),
        Vital.recorded_at <= now,
    ).order_by(Vital.recorded_at.desc(), Vital.created_at.desc(), Vital.id.desc()).limit(1))
    # Laboratory values are scoped to this request. Historical lab rows are
    # never silently substituted into a new risk analysis.
    features = runtime.build_features(
        age=age, sex=patient.gender,
        systolic_bp=vital.blood_pressure_systolic if vital else None,
        total_cholesterol=total_cholesterol,
        cholesterol_unit="mg/dL" if total_cholesterol is not None else None,
        fasting_glucose=fasting_glucose,
        glucose_unit="mg/dL" if fasting_glucose is not None else None,
    )
    probability, elevated = runtime.predict(features, loaded)
    factors = explain_logistic_features(features, loaded, "Heart Disease")
    result = Prediction(
        patient_id=patient.id, model_id=record.id, prediction_target=runtime.TARGET,
        risk_score=probability, risk_classification="elevated" if elevated else "not_elevated",
        prediction_result=("Elevated predicted heart-disease risk" if elevated
                           else "Predicted heart-disease risk below the model threshold"),
        explanation=(runtime.DISCLAIMER + (" Missing laboratory readings were imputed from training data; this estimate has additional uncertainty."
                     if fasting_glucose is None or total_cholesterol is None else "")), predicted_at=now,
        input_data={
            "features": features.model_dump(), "feature_order": list(loaded.feature_order),
            "model_version": loaded.version, "decision_threshold": loaded.threshold,
            "artifact_sha256": loaded.artifact_hash,
            "contributing_factors": factors,
            "sources": {
                "age": {"source": "patient.date_of_birth", "as_of": now.date().isoformat()},
                "sex": {"source": "patient.gender", "value": patient.gender},
                "systolic_bp": {"id": str(vital.id), "recorded_at": vital.recorded_at.isoformat(), "unit": "mmHg"},
                "total_cholesterol": {"source": "analysis_request", "unit": "mg/dL", "value": total_cholesterol,
                                      "entered_at": now.isoformat()} if total_cholesterol is not None else {"source": "missing; training_median_imputed"},
                "fasting_glucose": {"source": "analysis_request", "unit": "mg/dL", "value": fasting_glucose,
                                    "entered_at": now.isoformat()} if fasting_glucose is not None else {"source": "missing; training_median_imputed"},
            },
        },
    )
    return persist_prediction(db, result, actor_id)


def persist_prediction(db: Session, result: Prediction, actor_id: UUID) -> Prediction:
    db.add(result)
    db.flush()
    add_audit_event(db, "PREDICTION_CREATED", user_id=actor_id, resource_type="prediction",
                    resource_id=str(result.id), details={"target": result.prediction_target, "model_id": str(result.model_id)})
    db.commit()
    db.refresh(result)
    return result
