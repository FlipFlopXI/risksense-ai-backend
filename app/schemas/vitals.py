from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

    @model_validator(mode="after")
    def validate_measurements(self):
        values = (
            self.heart_rate,
            self.oxygen_saturation,
            self.temperature,
            self.blood_pressure_systolic,
            self.blood_pressure_diastolic,
        )
        if all(value is None for value in values):
            raise ValueError("At least one vital measurement is required.")
        if (
            self.blood_pressure_systolic is not None
            and self.blood_pressure_diastolic is not None
            and self.blood_pressure_diastolic > self.blood_pressure_systolic
        ):
            raise ValueError("Diastolic blood pressure cannot exceed systolic blood pressure.")
        if self.recorded_at is not None:
            recorded = self.recorded_at
            if recorded.tzinfo is None:
                raise ValueError("recorded_at must include a timezone.")
            if recorded > datetime.now(recorded.tzinfo):
                raise ValueError("recorded_at cannot be in the future.")
        return self


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
