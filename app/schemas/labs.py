from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.lab_result import LabTestType


class LabResultCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test_type: LabTestType
    value: float = Field(ge=0, allow_inf_nan=False, strict=True)
    unit: str = Field(min_length=1, max_length=30)
    source: str = Field(min_length=1, max_length=100)
    measured_at: datetime

    @model_validator(mode="after")
    def validate_heart_disease_labs(self):
        if self.test_type in (LabTestType.FASTING_GLUCOSE, LabTestType.TOTAL_CHOLESTEROL):
            if self.value <= 0:
                raise ValueError("This laboratory measurement must be positive.")
            self.unit = self.unit.strip()
            if self.unit not in ("mg/dL", "mmol/L"):
                raise ValueError("Use an explicit mg/dL or mmol/L unit for this test.")
        return self


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
