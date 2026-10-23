"""NHANES adult Diabetes v1: fixed trusted artifact, no runtime imputation of missing inputs."""
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
from threading import Lock
import warnings

import joblib
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sklearn.exceptions import InconsistentVersionWarning

from app.ml.common import LoadedModel, ModelInputError, ModelUnavailableError, predict_probability


TARGET = "diabetes_risk"
FEATURE_ORDER = ("age", "sex", "bmi", "waist_circumference", "systolic_bp", "diastolic_bp")
ARTIFACT_PATH = Path(__file__).resolve().parent / "risksense_diabetes_model_v1.pkl"
METADATA_PATH = ARTIFACT_PATH.with_name("risksense_diabetes_model_v1_metadata.json")
ARTIFACT_SHA256 = "efe8967a0e70d2ee0f63cab2b02d03ba91685a3b75a8d8d6c90918a8ff3c6496"
MINIMUM_AGE = 18
DISCLAIMER = (
    "This result is a risk estimate and is not a medical diagnosis. "
    "Diabetes v1 was trained on NHANES 2017–2018 adults using prevalent, "
    "self-reported diagnosed diabetes; it does not predict future diabetes onset."
)
_load_lock = Lock()


def validate_artifact(artifact: dict, metadata: dict, digest: str) -> LoadedModel:
    try:
        if digest != ARTIFACT_SHA256 or metadata["artifact_sha256"] != digest:
            raise ValueError
        if metadata["artifact_name"] != ARTIFACT_PATH.name:
            raise ValueError
        if artifact["model_version"] != metadata["model_version"] or artifact["model_version"] != "1.0.0":
            raise ValueError
        if artifact["prediction_target"] != metadata["prediction_target"] or artifact["prediction_target"] != TARGET:
            raise ValueError
        if artifact["feature_order"] != metadata["feature_order"] or tuple(artifact["feature_order"]) != FEATURE_ORDER:
            raise ValueError
        threshold = artifact["decision_threshold"]
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError
        if not math.isfinite(threshold) or not 0 < threshold < 1 or threshold != metadata["decision"]["threshold"]:
            raise ValueError
        population = artifact["validated_population"]
        documented_population = metadata["validated_population"]
        if population["minimum_age"] != MINIMUM_AGE or documented_population["minimum_age_years"] != MINIMUM_AGE:
            raise ValueError
        if population["maximum_age_in_training_data"] != documented_population["maximum_age_in_training_data"]:
            raise ValueError
        contract = metadata["feature_contract"]
        for name, unit in {"age": "completed years", "bmi": "kg/m^2", "waist_circumference": "cm",
                           "systolic_bp": "mmHg", "diastolic_bp": "mmHg"}.items():
            if contract[name]["unit"] != unit:
                raise ValueError
        if contract["sex"]["encoding"] != {"female": 0, "male": 1}:
            raise ValueError
        pipeline = artifact["pipeline"]
        if not callable(getattr(pipeline, "predict_proba", None)):
            raise ValueError
        if list(pipeline.classes_) != [0, 1] or list(pipeline.feature_names_in_) != list(FEATURE_ORDER):
            raise ValueError
        if type(pipeline.steps[-1][1]).__name__ != "LogisticRegression":
            raise ValueError
        return LoadedModel(pipeline, float(threshold), FEATURE_ORDER, artifact["model_version"], digest, metadata)
    except Exception:
        raise ModelUnavailableError("Diabetes model is unavailable.") from None


@lru_cache(maxsize=1)
def _load_model() -> LoadedModel:
    try:
        data = ARTIFACT_PATH.read_bytes()
        digest = sha256(data).hexdigest()
        if digest != ARTIFACT_SHA256:
            raise ValueError
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        with warnings.catch_warnings():
            warnings.simplefilter("error", InconsistentVersionWarning)
            artifact = joblib.load(BytesIO(data))
        return validate_artifact(artifact, metadata, digest)
    except Exception:
        raise ModelUnavailableError("Diabetes model is unavailable.") from None


def load_model() -> LoadedModel:
    with _load_lock:
        return _load_model()


class DiabetesFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    age: int = Field(ge=MINIMUM_AGE)
    sex: int = Field(ge=0, le=1)
    bmi: float = Field(gt=0)
    waist_circumference: float = Field(gt=0, le=300)
    systolic_bp: float = Field(gt=0, le=300)
    diastolic_bp: float = Field(gt=0, le=200)

    @model_validator(mode="after")
    def validate_bp(self):
        if self.diastolic_bp > self.systolic_bp:
            raise ValueError("Diastolic BP cannot exceed systolic BP.")
        return self


def build_features(*, age, sex, bmi, waist_circumference, systolic_bp, diastolic_bp) -> DiabetesFeatures:
    if type(age) is int and 0 <= age < MINIMUM_AGE:
        raise ModelInputError(["age"], message="Diabetes Risk Analysis v1 is not validated for patients under 18.")
    supplied = dict(age=age, sex=sex, bmi=bmi, waist_circumference=waist_circumference,
                    systolic_bp=systolic_bp, diastolic_bp=diastolic_bp)
    missing = [name for name, value in supplied.items() if value is None]
    if missing:
        raise ModelInputError(missing, missing=True)
    if not isinstance(sex, str) or sex.strip().lower() not in ("female", "male"):
        raise ModelInputError(["sex"], message="Diabetes v1 requires a supported sex value: female or male.")
    supplied["sex"] = {"female": 0, "male": 1}[sex.strip().lower()]
    try:
        return DiabetesFeatures(**supplied)
    except ValidationError as exc:
        fields = [str(e["loc"][0]) if e["loc"] else "blood_pressure" for e in exc.errors()]
        raise ModelInputError(fields) from None


def predict(features: DiabetesFeatures, model: LoadedModel) -> tuple[float, bool]:
    return predict_probability(features, model, FEATURE_ORDER, "Diabetes")
