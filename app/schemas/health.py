from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import date, datetime
from app.schemas.reproductive import ReproductiveFields, PregnancyStatus, BreastfeedingStatus


def validate_measurement_time(value: datetime | None):
    if value is not None and (value.tzinfo is None or value > datetime.now(value.tzinfo)):
        raise ValueError("body_measurement_at must be timezone-aware and not in the future.")
    return value


class HealthProfileCreateRequest(ReproductiveFields):
    body_measurement_at: datetime | None = None
    waist_circumference_cm: float | None = Field(default=None, gt=0, le=300, strict=True, allow_inf_nan=False)
    height_cm: float | None = Field(default=None, gt=0, le=300)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    blood_type: str | None = Field(default=None, max_length=10)
    smoking_status: str | None = Field(default=None, max_length=50)
    activity_level: str | None = Field(default=None, max_length=50)
    alcohol_status: str | None = Field(default=None, max_length=50)
    family_history_diabetes: bool | None = None
    family_history_heart_disease: bool | None = None
    family_history_hypertension: bool | None = None
    family_history: str | None = None
    existing_conditions: str | None = None
    current_medications: str | None = None

    _measurement_time = field_validator("body_measurement_at")(validate_measurement_time)


class HealthProfileUpdateRequest(ReproductiveFields):
    body_measurement_at: datetime | None = None
    waist_circumference_cm: float | None = Field(default=None, gt=0, le=300, strict=True, allow_inf_nan=False)
    height_cm: float | None = Field(default=None, gt=0, le=300)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    blood_type: str | None = Field(default=None, max_length=10)
    smoking_status: str | None = Field(default=None, max_length=50)
    activity_level: str | None = Field(default=None, max_length=50)
    alcohol_status: str | None = Field(default=None, max_length=50)
    family_history_diabetes: bool | None = None
    family_history_heart_disease: bool | None = None
    family_history_hypertension: bool | None = None
    family_history: str | None = None
    existing_conditions: str | None = None
    current_medications: str | None = None

    _measurement_time = field_validator("body_measurement_at")(validate_measurement_time)


class HealthProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    height_cm: float | None
    weight_kg: float | None
    waist_circumference_cm: float | None = None
    blood_type: str | None
    smoking_status: str | None
    activity_level: str | None
    alcohol_status: str | None
    family_history_diabetes: bool | None
    family_history_heart_disease: bool | None
    family_history_hypertension: bool | None
    family_history: str | None
    existing_conditions: str | None
    current_medications: str | None
    bmi: float | None = None
    pregnancy_status: PregnancyStatus | None = None
    estimated_due_date: date | None = None
    pregnancy_context_updated_at: datetime | None = None
    breastfeeding_status: BreastfeedingStatus | None = None
    infant_date_of_birth: date | None = None
    infant_premature: bool | None = None


class BodyMeasurementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    patient_id: UUID
    height_cm: float | None
    weight_kg: float | None
    waist_circumference_cm: float | None
    bmi: float | None = None
    source: str
    measured_at: datetime
