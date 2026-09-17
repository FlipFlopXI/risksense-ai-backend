"""Synthetic inputs only; no real patient records or external model services."""
from dataclasses import replace
import json
from unittest.mock import Mock

import joblib
import numpy as np
import pytest
from pydantic import ValidationError

from app.ml.heart_disease import runtime
from app.schemas.labs import LabResultCreateRequest


def inputs(**overrides):
    values = dict(age=50, sex="male", systolic_bp=130.0, total_cholesterol=200.0,
                  cholesterol_unit="mg/dL", fasting_glucose=120.0, glucose_unit="mg/dL")
    return values | overrides


def test_real_artifact_contract_and_inference():
    assert runtime.ARTIFACT_PATH.is_file()
    model = runtime.load_model()
    assert model.version == "1.0.0"
    assert model.threshold == 0.23
    assert model.metadata["target"] == "heart_disease_presence"
    assert model.feature_order == ("age", "sex", "systolic_bp", "total_cholesterol", "fasting_blood_sugar_high")
    assert model.pipeline is not None
    probability, flag = runtime.predict(runtime.build_features(**inputs()), model)
    assert 0 <= probability <= 1
    assert flag == (probability >= model.threshold)


def test_cached_load_and_paths_independent_of_working_directory(monkeypatch, tmp_path):
    runtime._load_model.cache_clear()
    loader = Mock(wraps=joblib.load)
    monkeypatch.setattr(runtime.joblib, "load", loader)
    monkeypatch.chdir(tmp_path)
    first = runtime.load_model()
    assert runtime.load_model() is first
    assert loader.call_count == 1


@pytest.mark.parametrize("key,value", [
    ("feature_order", list(reversed(runtime.FEATURE_ORDER))),
    ("decision_threshold", 0.5), ("target", "diabetes"), ("version", "other"),
    ("feature_details", {}), ("pipeline", None),
])
def test_artifact_metadata_mismatch_or_invalid_pipeline_rejected(key, value):
    artifact = joblib.load(runtime.ARTIFACT_PATH)
    metadata = json.loads(runtime.METADATA_PATH.read_text())
    artifact[key] = value
    with pytest.raises(runtime.ModelUnavailableError):
        runtime.validate_artifact(artifact, metadata, runtime.ARTIFACT_SHA256)


@pytest.mark.parametrize("key", ["pipeline", "feature_order", "decision_threshold", "target"])
def test_missing_artifact_keys_rejected(key):
    artifact = joblib.load(runtime.ARTIFACT_PATH)
    metadata = json.loads(runtime.METADATA_PATH.read_text())
    del artifact[key]
    with pytest.raises(runtime.ModelUnavailableError):
        runtime.validate_artifact(artifact, metadata, runtime.ARTIFACT_SHA256)


def test_hash_failure_prevents_deserialization(monkeypatch):
    runtime._load_model.cache_clear()
    loader = Mock(side_effect=AssertionError("must not deserialize"))
    monkeypatch.setattr(runtime, "ARTIFACT_SHA256", "0" * 64)
    monkeypatch.setattr(runtime.joblib, "load", loader)
    with pytest.raises(runtime.ModelUnavailableError):
        runtime.load_model()
    loader.assert_not_called()


@pytest.mark.parametrize("probability,expected", [(0.229, False), (0.23, True), (0.30, True), (0.499, True)])
def test_custom_threshold_and_exact_dataframe(probability, expected):
    pipeline = Mock()
    pipeline.predict_proba.return_value = np.array([[1-probability, probability]])
    model = replace(runtime.load_model(), pipeline=pipeline)
    score, flag = runtime.predict(runtime.build_features(**inputs()), model)
    assert score == probability and flag is expected
    frame = pipeline.predict_proba.call_args.args[0]
    assert frame.shape == (1, 5)
    assert list(frame.columns) == list(runtime.FEATURE_ORDER)
    assert frame.iloc[0].tolist() == [50, 1, 130, 200, 0]
    pipeline.predict.assert_not_called()


@pytest.mark.parametrize("probability", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_model_probability_fails_safely(probability):
    pipeline = Mock()
    pipeline.predict_proba.return_value = np.array([[0, probability]])
    with pytest.raises(runtime.ModelUnavailableError):
        runtime.predict(runtime.build_features(**inputs()), replace(runtime.load_model(), pipeline=pipeline))


@pytest.mark.parametrize("field", ["age", "sex", "systolic_bp", "total_cholesterol", "fasting_glucose"])
def test_missing_input_remains_missing(field):
    with pytest.raises(runtime.ModelInputError) as error:
        runtime.build_features(**inputs(**{field: None}))
    assert error.value.missing
    assert error.value.fields == [field]


@pytest.mark.parametrize("field,value", [
    ("age", -1), ("age", "50"), ("age", True), ("age", float("nan")),
    ("sex", "unknown"), ("sex", "nonbinary"), ("sex", 1),
    ("systolic_bp", -1), ("systolic_bp", 301), ("systolic_bp", "130"),
    ("systolic_bp", float("inf")), ("total_cholesterol", -1),
    ("total_cholesterol", float("nan")), ("total_cholesterol", "200"),
    ("fasting_glucose", 0), ("fasting_glucose", float("inf")),
    ("fasting_glucose", True), ("cholesterol_unit", "unknown"), ("glucose_unit", None),
])
def test_invalid_inputs_rejected(field, value):
    with pytest.raises(runtime.ModelInputError) as error:
        runtime.build_features(**inputs(**{field: value}))
    assert not error.value.missing


@pytest.mark.parametrize("sex,expected", [("female", 0), ("Male", 1), (" FEMALE ", 0)])
def test_model_specific_sex_mapping(sex, expected):
    assert runtime.build_features(**inputs(sex=sex)).sex == expected


@pytest.mark.parametrize("glucose,unit,expected", [
    (119.99, "mg/dL", 0), (120, "mg/dL", 0), (120.001, "mg/dL", 1),
    (6.66, "mmol/L", 0), (6.67, "mmol/L", 1),
])
def test_fasting_boundary_and_unit_conversion(glucose, unit, expected):
    features = runtime.build_features(**inputs(fasting_glucose=glucose, glucose_unit=unit))
    assert features.fasting_blood_sugar_high == expected
    assert runtime.lab_mg_dl(7, "mmol/L", "fasting_glucose") == pytest.approx(126.126)


def test_cholesterol_unit_conversion():
    features = runtime.build_features(**inputs(total_cholesterol=5, cholesterol_unit="mmol/L"))
    assert features.total_cholesterol == pytest.approx(193.35)
    assert runtime.lab_mg_dl(200, "mg/dL", "total_cholesterol") == 200


@pytest.mark.parametrize("value,unit", [(float("inf"), "mg/dL"), (float("nan"), "mg/dL"),
                                         ("120", "mg/dL"), (0, "mg/dL"), (120, "unknown")])
def test_lab_api_schema_rejects_invalid_measurements(value, unit):
    with pytest.raises(ValidationError):
        LabResultCreateRequest(test_type="fasting_glucose", value=value, unit=unit,
                               source="synthetic test", measured_at="2026-01-01T00:00:00Z")
