"""Fixed, trusted Heart Disease artifact and its five-feature runtime contract."""
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path
from threading import Lock
from typing import Any
import warnings

import joblib
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sklearn.exceptions import InconsistentVersionWarning


FEATURE_ORDER = (
    "age", "sex", "systolic_bp", "total_cholesterol", "fasting_blood_sugar_high",
)
TARGET = "heart_disease"
ARTIFACT_PATH = Path(__file__).resolve().parent / "risksense_heart_disease_model_v1.pkl"
METADATA_PATH = ARTIFACT_PATH.with_name("risksense_heart_disease_model_v1_metadata.json")
ARTIFACT_SHA256 = "8aa3839216060029bdd7fa133febfad5d0db00625c41f8f571d2979d04a90453"
DISCLAIMER = "This result is a risk estimate and is not a medical diagnosis."
_load_lock = Lock()


class ModelUnavailableError(Exception):
    """Only a fixed, safe message is exposed by the API."""


class ModelInputError(Exception):
    def __init__(self, fields: list[str], *, missing: bool = False):
        self.fields = fields
        self.missing = missing
        super().__init__("Required model inputs are missing or invalid.")


@dataclass(frozen=True)
class LoadedModel:
    pipeline: Any
    threshold: float
    feature_order: tuple[str, ...]
    version: str
    artifact_hash: str
    metadata: dict


def validate_artifact(artifact: dict, metadata: dict, digest: str) -> LoadedModel:
    """Validate runtime configuration against metadata; never repair a mismatch."""
    try:
        if not isinstance(artifact, dict) or not isinstance(metadata, dict):
            raise ValueError
        if {key: value for key, value in artifact.items() if key != "pipeline"} != metadata:
            raise ValueError
        if tuple(artifact["feature_order"]) != FEATURE_ORDER:
            raise ValueError
        # The supplied model predicts presence in the Cleveland dataset; the API
        # names this screening target heart_disease, not a prospective prognosis.
        if artifact["target"] != "heart_disease_presence":
            raise ValueError
        if artifact["algorithm"] != "LogisticRegression" or artifact["model_type"] != "Heart Disease":
            raise ValueError
        threshold = artifact["decision_threshold"]
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError
        if not math.isfinite(threshold) or not 0 < threshold < 1:
            raise ValueError
        if not isinstance(artifact["version"], str) or not artifact["version"]:
            raise ValueError
        pipeline = artifact["pipeline"]
        if not callable(getattr(pipeline, "predict_proba", None)):
            raise ValueError
        if list(pipeline.classes_) != [0, 1]:
            raise ValueError
        if list(pipeline.feature_names_in_) != list(FEATURE_ORDER):
            raise ValueError
        return LoadedModel(pipeline, float(threshold), FEATURE_ORDER, artifact["version"], digest, metadata)
    except Exception:
        raise ModelUnavailableError("Heart Disease model is unavailable.") from None


@lru_cache(maxsize=1)
def _load_model() -> LoadedModel:
    try:
        # Deserialize exactly the bytes whose digest was checked, never a path
        # supplied by a caller or stored in a mutable database record.
        from io import BytesIO

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
        raise ModelUnavailableError("Heart Disease model is unavailable.") from None


def load_model() -> LoadedModel:
    # lru_cache alone may deserialize twice on simultaneous first requests.
    with _load_lock:
        return _load_model()


class HeartFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    age: int = Field(ge=0)
    sex: int = Field(ge=0, le=1)
    systolic_bp: float = Field(gt=0, le=300)  # Existing Vital schema bound.
    total_cholesterol: float = Field(gt=0)
    fasting_blood_sugar_high: int = Field(ge=0, le=1)


def lab_mg_dl(value: float, unit: str, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ModelInputError([field])
    if not math.isfinite(value) or value <= 0 or unit not in ("mg/dL", "mmol/L"):
        raise ModelInputError([field])
    # Explicit analyte-specific factors; sources and precision documented in README.
    factors = {"total_cholesterol": Decimal("38.67"), "fasting_glucose": Decimal("18.018")}
    converted = Decimal(str(value))
    if unit == "mmol/L":
        converted *= factors[field]
    result = float(converted)
    if not math.isfinite(result) or result <= 0:
        raise ModelInputError([field])
    return result


def build_features(*, age, sex, systolic_bp, total_cholesterol, cholesterol_unit,
                   fasting_glucose, glucose_unit) -> HeartFeatures:
    supplied = {"age": age, "sex": sex, "systolic_bp": systolic_bp,
                "total_cholesterol": total_cholesterol, "fasting_glucose": fasting_glucose}
    missing = [key for key, value in supplied.items() if value is None]
    if missing:
        raise ModelInputError(missing, missing=True)
    if not isinstance(sex, str) or sex.strip().lower() not in ("female", "male"):
        raise ModelInputError(["sex"])
    cholesterol = lab_mg_dl(total_cholesterol, cholesterol_unit, "total_cholesterol")
    glucose = lab_mg_dl(fasting_glucose, glucose_unit, "fasting_glucose")
    try:
        return HeartFeatures(age=age, sex={"female": 0, "male": 1}[sex.strip().lower()],
                             systolic_bp=systolic_bp, total_cholesterol=cholesterol,
                             fasting_blood_sugar_high=int(glucose > 120))
    except ValidationError as exc:
        raise ModelInputError([str(error["loc"][0]) for error in exc.errors()]) from None


def predict(features: HeartFeatures, model: LoadedModel) -> tuple[float, bool]:
    try:
        if model.feature_order != FEATURE_ORDER:
            raise ValueError
        values = features.model_dump()
        frame = pd.DataFrame([[values[name] for name in model.feature_order]], columns=model.feature_order)
        probabilities = model.pipeline.predict_proba(frame)
        if probabilities.shape != (1, 2):
            raise ValueError
        probability = float(probabilities[0, 1])
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError
        return probability, probability >= model.threshold
    except Exception:
        raise ModelUnavailableError("Heart Disease inference is unavailable.") from None
