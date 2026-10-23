import math
from uuid import uuid4

import pytest

from app.ml.common import explain_logistic_features
from app.ml.diabetes import runtime as diabetes
from app.ml.heart_disease import runtime as heart
from app.models.prediction import Prediction
from app.schemas.predictions import PredictionResponse


@pytest.mark.parametrize("model_runtime,features", [
    (diabetes, lambda: diabetes.build_features(
        age=45, sex="female", bmi=29.1, waist_circumference=91.0,
        systolic_bp=132.0, diastolic_bp=82.0)),
    (heart, lambda: heart.build_features(
        age=45, sex="female", systolic_bp=132.0,
        total_cholesterol=195.0, cholesterol_unit="mg/dL",
        fasting_glucose=110.0, glucose_unit="mg/dL")),
])
def test_feature_contributions_reconstruct_model_logit(model_runtime, features):
    loaded = model_runtime.load_model()
    factors = explain_logistic_features(features(), loaded, "Test")
    assert {item["feature"] for item in factors} == set(loaded.feature_order)
    assert math.isclose(sum(item["relative_magnitude"] for item in factors), 1.0)
    assert all(0 <= item["relative_magnitude"] <= 1 for item in factors)
    assert all((item["log_odds_contribution"] > 0) == (item["direction"] == "raises")
               for item in factors if item["log_odds_contribution"] != 0)
    assert all(factors[index]["relative_magnitude"] >= factors[index + 1]["relative_magnitude"]
               for index in range(len(factors) - 1))


def test_prediction_response_uses_the_same_factors_as_interpretation():
    factors = explain_logistic_features(
        diabetes.build_features(age=45, sex="female", bmi=29.1,
            waist_circumference=91.0, systolic_bp=132.0, diastolic_bp=82.0),
        diabetes.load_model(), "Diabetes")
    prediction = Prediction(
        id=uuid4(), patient_id=uuid4(), model_id=uuid4(),
        prediction_target="diabetes_risk", risk_score=0.5,
        risk_classification="elevated", predicted_at="2026-09-22T00:00:00Z",
        input_data={"contributing_factors": factors},
    )
    response = PredictionResponse.model_validate(prediction)
    assert len(response.contributing_factors) == len(diabetes.FEATURE_ORDER)
    top_raising = next(item.feature for item in response.contributing_factors
                       if item.direction == "raises")
    assert response.interpretation is not None
    labels = {"age": "Age", "sex": "Sex", "bmi": "BMI",
              "waist_circumference": "Waist circumference",
              "systolic_bp": "Systolic blood pressure",
              "diastolic_bp": "Diastolic blood pressure"}
    assert labels[top_raising] in response.interpretation
