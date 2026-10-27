import pytest
from pydantic import ValidationError
from types import SimpleNamespace

from app.schemas.onboarding import OnboardingDetails
from app.api.v1.patients import onboarding_complete


VALID = {
    "height_cm": 178, "weight_kg": 80, "waist_circumference_cm": None,
    "smoking_status": "Never", "activity_level": "Moderate", "alcohol_status": "None",
    "family_history_diabetes": None, "family_history_heart_disease": False,
    "family_history_hypertension": True, "has_chronic_condition": False,
    "chronic_conditions": None, "chronic_medications": None,
}


def test_unknown_family_history_is_preserved():
    request = OnboardingDetails.model_validate(VALID)
    assert request.family_history_diabetes is None


@pytest.mark.parametrize("change", [
    {"height_cm": 0}, {"weight_kg": 900}, {"smoking_status": "sometimes"},
    {"chronic_medications": "Medication without chronic condition"},
    {"has_chronic_condition": True},
])
def test_invalid_or_inconsistent_onboarding_rejected(change):
    with pytest.raises(ValidationError):
        OnboardingDetails.model_validate({**VALID, **change})


def test_chronic_medication_optional_when_condition_reported():
    request = OnboardingDetails.model_validate({**VALID, "has_chronic_condition": True,
                                                "chronic_conditions": "Patient-reported condition"})
    assert request.chronic_medications is None


def test_onboarding_status_requires_core_recorded_values():
    profile = SimpleNamespace(height_cm=178, weight_kg=80, smoking_status="Never",
                              activity_level="Moderate", alcohol_status=None)
    assert onboarding_complete(None) is False
    assert onboarding_complete(profile) is False
    profile.alcohol_status = "None"
    assert onboarding_complete(profile) is True
