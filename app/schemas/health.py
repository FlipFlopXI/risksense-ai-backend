from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HealthProfileCreateRequest(BaseModel):
    height_cm: float | None = Field(default=None, gt=0, le=300)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    blood_type: str | None = Field(default=None, max_length=10)
    smoking_status: str | None = Field(default=None, max_length=50)
    activity_level: str | None = Field(default=None, max_length=50)
    family_history: str | None = None
    existing_conditions: str | None = None
    current_medications: str | None = None


class HealthProfileUpdateRequest(BaseModel):
    height_cm: float | None = Field(default=None, gt=0, le=300)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    blood_type: str | None = Field(default=None, max_length=10)
    smoking_status: str | None = Field(default=None, max_length=50)
    activity_level: str | None = Field(default=None, max_length=50)
    family_history: str | None = None
    existing_conditions: str | None = None
    current_medications: str | None = None


class HealthProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    height_cm: float | None
    weight_kg: float | None
    blood_type: str | None
    smoking_status: str | None
    activity_level: str | None
    family_history: str | None
    existing_conditions: str | None
    current_medications: str | None