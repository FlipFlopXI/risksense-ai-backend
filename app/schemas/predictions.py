from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
    bmi: float | None
    latest_systolic_bp: float | None
    latest_diastolic_bp: float | None
    latest_glucose: float | None
    prediction_count: int
    latest_predictions: list[PredictionResponse]
