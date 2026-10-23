"""Database-independent artifact and clinical-input contract checks."""
from copy import deepcopy
from dataclasses import replace
from datetime import date
from hashlib import sha256
import json
from unittest.mock import Mock

import joblib
import numpy as np
import pytest
from pydantic import ValidationError

from app.ml.common import ModelInputError, ModelUnavailableError, completed_age
from app.ml.diabetes import runtime
from app.ml.heart_disease import runtime as heart
from app.schemas.health import HealthProfileUpdateRequest

VALUES = dict(age=50, sex="male", bmi=30.0, waist_circumference=100.0,
              systolic_bp=130.0, diastolic_bp=80.0)


def test_real_artifact_and_heart_regression():
    assert sha256(runtime.ARTIFACT_PATH.read_bytes()).hexdigest() == runtime.ARTIFACT_SHA256
    model = runtime.load_model()
    assert model.version == "1.0.0"
    assert model.threshold == 0.455
    assert model.feature_order == tuple(VALUES)
    probability, elevated = runtime.predict(runtime.build_features(**VALUES), model)
    assert 0 <= probability <= 1 and elevated == (probability >= model.threshold)
    assert heart.load_model().version == "1.0.0"


@pytest.mark.parametrize("field,value", [
    ("model_version", "2"), ("prediction_target", "future_diabetes"),
    ("feature_order", list(reversed(runtime.FEATURE_ORDER))),
    ("decision_threshold", float("nan")), ("decision_threshold", True),
    ("decision_threshold", 0.5), ("validated_population", {"minimum_age": 17}),
])
def test_artifact_contract_mismatch(field, value):
    artifact = joblib.load(runtime.ARTIFACT_PATH)
    artifact[field] = value
    metadata = json.loads(runtime.METADATA_PATH.read_text(encoding="utf-8"))
    with pytest.raises(ModelUnavailableError):
        runtime.validate_artifact(artifact, metadata, runtime.ARTIFACT_SHA256)


@pytest.mark.parametrize("field", ["artifact_sha256", "artifact_name", "feature_contract", "decision"])
def test_metadata_contract_mismatch(field):
    artifact = joblib.load(runtime.ARTIFACT_PATH)
    metadata = deepcopy(runtime.load_model().metadata)
    metadata[field] = "incompatible"
    with pytest.raises(ModelUnavailableError):
        runtime.validate_artifact(artifact, metadata, runtime.ARTIFACT_SHA256)


def test_hash_checked_before_deserialization(monkeypatch):
    path = Mock()
    path.read_bytes.return_value = b"untrusted"
    deserialize = Mock(side_effect=AssertionError("must not deserialize"))
    monkeypatch.setattr(runtime, "ARTIFACT_PATH", path)
    monkeypatch.setattr(runtime.joblib, "load", deserialize)
    with pytest.raises(ModelUnavailableError):
        runtime._load_model.__wrapped__()
    deserialize.assert_not_called()


@pytest.mark.parametrize("sex,encoded", [("female", 0), ("male", 1), (" Female ", 0), ("MALE", 1)])
def test_sex_encoding(sex, encoded):
    assert runtime.build_features(**{**VALUES, "sex": sex}).sex == encoded


@pytest.mark.parametrize("sex", ["unknown", "", 0, True])
def test_unsupported_sex(sex):
    with pytest.raises(ModelInputError) as error:
        runtime.build_features(**{**VALUES, "sex": sex})
    assert error.value.fields == ["sex"]
    assert "female or male" in error.value.message


@pytest.mark.parametrize("field", list(VALUES))
def test_missing_inputs(field):
    with pytest.raises(ModelInputError) as error:
        runtime.build_features(**{**VALUES, field: None})
    assert error.value.missing and error.value.fields == [field]


def test_completed_years_and_adult_boundary():
    assert completed_age(date(2008, 9, 17), date(2026, 9, 16)) == 17
    assert completed_age(date(2008, 9, 17), date(2026, 9, 17)) == 18
    assert completed_age(None, date(2026, 9, 17)) is None
    with pytest.raises(ModelInputError):
        completed_age(date(2027, 1, 1), date(2026, 9, 17))
    assert runtime.build_features(**{**VALUES, "age": 18}).age == 18
    with pytest.raises(ModelInputError) as error:
        runtime.build_features(**{**VALUES, "age": 17})
    assert "under 18" in error.value.message


@pytest.mark.parametrize("field,value", [("bmi", 0), ("bmi", float("inf")),
    ("waist_circumference", -1), ("waist_circumference", 301),
    ("waist_circumference", "100 cm"), ("systolic_bp", 0),
    ("diastolic_bp", 140), ("diastolic_bp", float("nan"))])
def test_invalid_measurements(field, value):
    with pytest.raises(ModelInputError):
        runtime.build_features(**{**VALUES, field: value})


@pytest.mark.parametrize("probability,expected", [(0.454, False), (0.455, True), (0.456, True)])
def test_exact_dataframe_and_threshold(probability, expected):
    pipeline = Mock()
    pipeline.predict_proba.return_value = np.array([[1 - probability, probability]])
    model = replace(runtime.load_model(), pipeline=pipeline)
    assert runtime.predict(runtime.build_features(**VALUES), model) == (probability, expected)
    frame = pipeline.predict_proba.call_args.args[0]
    assert list(frame.columns) == list(runtime.FEATURE_ORDER)
    assert frame.iloc[0].tolist() == [50, 1, 30, 100, 130, 80]
    pipeline.predict.assert_not_called()


@pytest.mark.parametrize("waist", [0, -1, 301, float("inf"), float("nan"), "100 cm", True])
def test_waist_api_validation(waist):
    with pytest.raises(ValidationError):
        HealthProfileUpdateRequest(waist_circumference_cm=waist)


def test_waist_api_optional_and_cm():
    assert HealthProfileUpdateRequest().waist_circumference_cm is None
    assert HealthProfileUpdateRequest(waist_circumference_cm=100).waist_circumference_cm == 100
