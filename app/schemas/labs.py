from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.lab_result import LabTestType


class LabResultCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test_type: LabTestType
    value: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=30)
    source: str = Field(min_length=1, max_length=100)
    measured_at: datetime


class LabResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    patient_id: UUID
    test_type: LabTestType
    value: float
    unit: str
    source: str
    verification_status: str
    measured_at: datetime
    created_at: datetime
