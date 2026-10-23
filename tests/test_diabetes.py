"""Canonical profile BMI checks; no database connection required."""
import pytest

import app.db.models  # Register ORM relationships before constructing a profile.
from app.ml.common import ModelInputError
from app.models.health_profile import HealthProfile
from app.services.diabetes_service import profile_bmi


@pytest.mark.parametrize("height,weight,expected", [(180, 97.2, 30), (178, 80, 25.25)])
def test_uses_canonical_bmi(height, weight, expected):
    profile = HealthProfile(height_cm=height, weight_kg=weight)
    assert profile_bmi(profile) == profile.bmi == expected


@pytest.mark.parametrize("height,weight", [(0, 80), (-178, 80), (178, 0), (301, 80),
                                         (178, 501), (float("nan"), 80), (178, float("inf"))])
def test_invalid_legacy_body_measurements_rejected(height, weight):
    with pytest.raises(ModelInputError) as error:
        profile_bmi(HealthProfile(height_cm=height, weight_kg=weight))
    assert error.value.fields == ["bmi"]


def test_missing_body_measurements_remain_missing():
    assert profile_bmi(None) is None
    assert profile_bmi(HealthProfile(height_cm=None, weight_kg=80)) is None
    assert profile_bmi(HealthProfile(height_cm=178, weight_kg=None)) is None
