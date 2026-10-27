from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActivityCreate(BaseModel):
    log_date: date
    steps: int = Field(ge=0, le=100000)
    activity_minutes: int = Field(ge=0, le=1440)
    activity_calories_kcal: float = Field(ge=0, le=10000, allow_inf_nan=False)
    distance_km: float = Field(ge=0, le=500, allow_inf_nan=False)

    @model_validator(mode="after")
    def nonempty(self):
        if not any((self.steps, self.activity_minutes, self.activity_calories_kcal, self.distance_km)):
            raise ValueError("Enter at least one activity measurement.")
        return self


class ActivityResponse(ActivityCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime


class ActivityDay(BaseModel):
    date: date
    steps: int
    activity_minutes: int
    activity_calories_kcal: float
    distance_km: float


class ActivitySummary(BaseModel):
    date: date
    today: ActivityDay
    history: list[ActivityDay]


class WeightUpdate(BaseModel):
    weight_kg: float = Field(gt=0, le=500, allow_inf_nan=False)


class BodyCompositionCreate(BaseModel):
    skeletal_muscle_kg: float = Field(gt=0, le=250, allow_inf_nan=False)
    body_fat_percent: float = Field(ge=0, le=100, allow_inf_nan=False)


class BodyCompositionResponse(BodyCompositionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime


class BodySummary(BaseModel):
    height_cm: float | None
    weight_kg: float | None
    bmi: float | None
    composition: BodyCompositionResponse | None
    adult_bmi_reference_applicable: bool
