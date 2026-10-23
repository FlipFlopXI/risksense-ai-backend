from datetime import datetime
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContributingFactor(BaseModel):
    feature: str
    log_odds_contribution: float
    relative_magnitude: float
    direction: Literal["raises", "lowers", "neutral"]


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    patient_id: UUID
    model_id: UUID
    prediction_target: str
    risk_score: float | None
    risk_classification: str
    prediction_result: str | None
    explanation: str | None
    predicted_at: datetime
    model_version: str | None = None
    decision_threshold: float | None = None
    contributing_factors: list[ContributingFactor] = Field(default_factory=list)
    interpretation: str | None = None


class RiskAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Literal["heart_disease", "diabetes"]
    patient_id: UUID | None = None


class ReportGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prediction_id: UUID
    patient_id: UUID | None = None


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    patient_id: UUID
    prediction_id: UUID | None
    report_type: str
    title: str
    summary: str | None
    recommendations: str | None
    report_data: dict | None
    generated_at: datetime


class DashboardResponse(BaseModel):
    patient_first_name: str
    bmi: float | None
    bmi_measured_at: datetime | None
    latest_systolic_bp: float | None
    latest_diastolic_bp: float | None
    blood_pressure_recorded_at: datetime | None
    latest_glucose: float | None
    latest_glucose_unit: str | None
    glucose_measured_at: datetime | None
    prediction_count: int
    latest_predictions: list[PredictionResponse]
    drug_response_enquiries_today: int
    last_updated_at: datetime | None
