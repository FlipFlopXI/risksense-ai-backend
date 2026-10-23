"""Transient clinician demonstration assessment; no patient identity is accepted."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.predictions import PredictionResponse


class ClinicianProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gender: Literal["female", "male", "unspecified"]


class ClinicalAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    model: Literal["diabetes", "heart_disease"]
    age: int = Field(ge=0, le=120)
    sex: Literal["female", "male"]
    ethnicity: str | None = Field(default=None, max_length=100)
    height_cm: float | None = Field(default=None, gt=0, le=300)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    waist_circumference_cm: float | None = Field(default=None, gt=0, le=300)
    systolic_bp: float | None = Field(default=None, gt=0, le=300)
    diastolic_bp: float | None = Field(default=None, gt=0, le=200)
    fasting_glucose: float | None = Field(default=None, gt=0)
    total_cholesterol: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def check_bp(self):
        if (self.systolic_bp is not None and self.diastolic_bp is not None
                and self.diastolic_bp > self.systolic_bp):
            raise ValueError("Diastolic BP cannot exceed systolic BP.")
        return self


class ClinicalAssessmentResponse(BaseModel):
    model: Literal["diabetes", "heart_disease"]
    risk_score: float
    risk_classification: str
    interpretation: str
    contributing_factors: list[dict]
    model_version: str
    decision_threshold: float
    disclaimer: str
    persisted: Literal[False] = False


class ClinicianPredictionDetail(BaseModel):
    prediction: PredictionResponse
    input_snapshot: dict | None
