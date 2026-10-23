from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class MedicationFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    dose: str | None = Field(None, max_length=100)
    unit: str | None = Field(None, max_length=50)
    frequency: str | None = Field(None, max_length=100)
    route: str | None = Field(None, max_length=100)
    reason: str | None = Field(None, max_length=300)
    prescribed_by: str | None = Field(None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must not precede start date.")
        if any(value and not date(1900, 1, 1) <= value <= date(2100, 12, 31) for value in (self.start_date, self.end_date)):
            raise ValueError("Medication date is outside the supported range.")
        return self


class MedicationCreate(MedicationFields):
    display_name: str = Field(min_length=1, max_length=200)


class MedicationUpdate(MedicationFields):
    display_name: str | None = Field(None, min_length=1, max_length=200)


class MedicationResponse(MedicationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    patient_id: UUID
    drug_id: str | None
    created_at: datetime
    updated_at: datetime
