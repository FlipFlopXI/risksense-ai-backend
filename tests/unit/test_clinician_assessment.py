"""Anonymous clinician assessment uses the validated in-memory feature contracts."""
import pytest
from pydantic import ValidationError

from app.ml.common import ModelInputError
from app.ml.diabetes import runtime as diabetes
from app.ml.heart_disease import runtime as heart
from app.schemas.clinician_assessment import ClinicalAssessmentRequest
from app.services.clinician_assessment_service import assess


def test_diabetes_demonstration_returns_transient_result():
    request = ClinicalAssessmentRequest(
        model="diabetes", age=45, sex="female", height_cm=170, weight_kg=75,
        waist_circumference_cm=90, systolic_bp=125, diastolic_bp=80,
    )
    result = assess(request, diabetes.load_model())
    assert result.persisted is False
    assert 0 <= result.risk_score <= 1
    assert result.model == "diabetes" and result.contributing_factors


def test_heart_demonstration_returns_transient_result():
    request = ClinicalAssessmentRequest(
        model="heart_disease", age=50, sex="male", systolic_bp=130,
        fasting_glucose=100, total_cholesterol=180,
    )
    result = assess(request, heart.load_model())
    assert result.persisted is False
    assert 0 <= result.risk_score <= 1
    assert result.model == "heart_disease" and result.contributing_factors


def test_assessment_does_not_accept_patient_identity_or_missing_features():
    with pytest.raises(ValidationError):
        ClinicalAssessmentRequest(model="diabetes", age=45, sex="female", patient_id="other")
    with pytest.raises(ModelInputError):
        assess(ClinicalAssessmentRequest(model="diabetes", age=45, sex="female"),
               diabetes.load_model())
