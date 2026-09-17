"""Heart Disease inference using existing patient, registry and prediction records."""
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ml.heart_disease import runtime
from app.models.lab_result import LabResult, LabTestType
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
    # Serialize registration across workers without adding a duplicate registry.
    db.execute(text("SELECT pg_advisory_xact_lock(7241902301)"))
    active = db.scalars(select(Model).where(
        Model.prediction_target == runtime.TARGET, Model.is_active.is_(True),
    )).all()
    if any(row.id != MODEL_ID for row in active):
        raise runtime.ModelUnavailableError("A different Heart Disease version is active.")
    record = db.get(Model, MODEL_ID)
    if record is None:
        record = Model(
            id=MODEL_ID, name=loaded.metadata["model_name"], version=loaded.version,
            prediction_target=runtime.TARGET, algorithm="LogisticRegression",
            dataset_name=loaded.metadata["dataset"], model_path=MODEL_PATH,
            description=runtime.DISCLAIMER, is_active=True,
        )
        db.add(record)
    else:
        _validate_registry(record, loaded)
        record.is_active = True
    db.flush()
    add_audit_event(db, "MODEL_ACTIVATED", user_id=actor_id, resource_type="ml_model",
                    resource_id=str(record.id), details={"target": runtime.TARGET, "version": loaded.version})
    db.commit()
    db.refresh(record)
    return record


def _validate_registry(record: Model, loaded: runtime.LoadedModel) -> None:
    if (record.id != MODEL_ID or record.version != loaded.version
            or record.prediction_target != runtime.TARGET
            or record.algorithm != "LogisticRegression" or record.model_path != MODEL_PATH):
        raise runtime.ModelUnavailableError("Heart Disease registry configuration is incompatible.")


def _latest_lab(db: Session, patient_id: UUID, test_type: LabTestType, now: datetime):
    return db.scalar(select(LabResult).where(
        LabResult.patient_id == patient_id, LabResult.test_type == test_type,
        LabResult.measured_at <= now,
    ).order_by(LabResult.measured_at.desc(), LabResult.created_at.desc(), LabResult.id.desc()).limit(1))


def _lab_snapshot(lab: LabResult) -> dict:
    return {"id": str(lab.id), "value": lab.value, "unit": lab.unit,
            "source": lab.source, "verification_status": lab.verification_status,
            "measured_at": lab.measured_at.isoformat()}


def run_heart_analysis(db: Session, patient: Patient, actor_id: UUID) -> Prediction:
    records = db.scalars(select(Model).where(
        Model.prediction_target == runtime.TARGET, Model.is_active.is_(True),
    ).with_for_update()).all()
    if not records:
        raise ModelInactiveError
    if len(records) != 1:
        raise runtime.ModelUnavailableError("Ambiguous active model configuration.")
    loaded = runtime.load_model()
    record = records[0]
    _validate_registry(record, loaded)
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
    cholesterol = _latest_lab(db, patient.id, LabTestType.TOTAL_CHOLESTEROL, now)
    glucose = _latest_lab(db, patient.id, LabTestType.FASTING_GLUCOSE, now)
    features = runtime.build_features(
        age=age, sex=patient.gender,
        systolic_bp=vital.blood_pressure_systolic if vital else None,
        total_cholesterol=cholesterol.value if cholesterol else None,
        cholesterol_unit=cholesterol.unit if cholesterol else None,
        fasting_glucose=glucose.value if glucose else None,
        glucose_unit=glucose.unit if glucose else None,
    )
    probability, elevated = runtime.predict(features, loaded)
    result = Prediction(
        patient_id=patient.id, model_id=record.id, prediction_target=runtime.TARGET,
        risk_score=probability, risk_classification="elevated" if elevated else "not_elevated",
        prediction_result=("Elevated predicted heart-disease risk" if elevated
                           else "Predicted heart-disease risk below the model threshold"),
        explanation=runtime.DISCLAIMER, predicted_at=now,
        input_data={
            "features": features.model_dump(), "feature_order": list(loaded.feature_order),
            "model_version": loaded.version, "decision_threshold": loaded.threshold,
            "artifact_sha256": loaded.artifact_hash,
            "sources": {
                "age": {"source": "patient.date_of_birth", "as_of": now.date().isoformat()},
                "sex": {"source": "patient.gender", "value": patient.gender},
                "systolic_bp": {"id": str(vital.id), "recorded_at": vital.recorded_at.isoformat(), "unit": "mmHg"},
                "total_cholesterol": _lab_snapshot(cholesterol),
                "fasting_glucose": _lab_snapshot(glucose),
            },
        },
    )
    db.add(result)
    db.flush()
    add_audit_event(db, "PREDICTION_CREATED", user_id=actor_id, resource_type="prediction",
                    resource_id=str(result.id), details={"target": runtime.TARGET, "model_id": str(record.id)})
    db.commit()
    db.refresh(result)
    return result
