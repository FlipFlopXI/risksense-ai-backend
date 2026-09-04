from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VitalCreateRequest(BaseModel):
    heart_rate: float | None = Field(
        default=None,
        gt=0,
        le=300,
    )

    oxygen_saturation: float | None = Field(
        default=None,
        gt=0,
        le=100,
    )

    temperature: float | None = Field(
        default=None,
        gt=0,
        le=50,
    )

    blood_pressure_systolic: float | None = Field(
        default=None,
        gt=0,
        le=300,
    )

    blood_pressure_diastolic: float | None = Field(
        default=None,
        gt=0,
        le=200,
    )

    recorded_at: datetime | None = None


class VitalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID

    heart_rate: float | None
    oxygen_saturation: float | None
    temperature: float | None
    blood_pressure_systolic: float | None
    blood_pressure_diastolic: float | None

    recorded_at: datetime
    created_at: datetime


class VitalBatchCreateRequest(BaseModel):
    vitals: list[VitalCreateRequest] = Field(
        min_length=1,
        max_length=100,
    )


class VitalBatchResponse(BaseModel):
    vitals: list[VitalResponse]
    count: int