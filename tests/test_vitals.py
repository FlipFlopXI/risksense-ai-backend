from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas.vitals import VitalCreateRequest


def test_empty_vital_is_rejected():
    with pytest.raises(ValidationError):
        VitalCreateRequest()


def test_invalid_blood_pressure_is_rejected():
    with pytest.raises(ValidationError):
        VitalCreateRequest(blood_pressure_systolic=80, blood_pressure_diastolic=100)


def test_future_measurement_is_rejected():
    with pytest.raises(ValidationError):
        VitalCreateRequest(heart_rate=70, recorded_at=datetime.now(timezone.utc) + timedelta(days=1))
