"""Optional patient-reported context; never inferred from demographics."""
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from pydantic import BaseModel, field_validator, model_validator

PregnancyStatus = Literal["NOT_PREGNANT", "PREGNANT", "POSSIBLY_PREGNANT", "TRYING_TO_CONCEIVE", "POSTPARTUM", "PREFER_NOT_TO_SAY", "UNKNOWN"]
BreastfeedingStatus = Literal["YES", "NO", "PREFER_NOT_TO_SAY", "UNKNOWN"]
CONTEXT_FIELDS = frozenset({"pregnancy_status", "estimated_due_date", "breastfeeding_status", "infant_date_of_birth", "infant_premature"})


class ReproductiveFields(BaseModel):
    pregnancy_status: PregnancyStatus | None = None
    estimated_due_date: date | None = None
    breastfeeding_status: BreastfeedingStatus | None = None
    infant_date_of_birth: date | None = None
    infant_premature: bool | None = None

    @field_validator("estimated_due_date", "infant_date_of_birth")
    @classmethod
    def validate_dates(cls, value: date | None, info):
        if value is None:
            return value
        today = datetime.now(timezone.utc).date()
        if value < date(1900, 1, 1):
            raise ValueError("Date is outside the supported range.")
        if info.field_name == "infant_date_of_birth" and value > today:
            raise ValueError("Infant date of birth cannot be in the future.")
        if info.field_name == "estimated_due_date" and value > today + timedelta(days=366):
            raise ValueError("Estimated due date cannot be more than a year ahead.")
        return value

    @model_validator(mode="after")
    def validate_context(self):
        if self.estimated_due_date is not None and self.pregnancy_status in {"NOT_PREGNANT", "TRYING_TO_CONCEIVE", "PREFER_NOT_TO_SAY", "UNKNOWN"}:
            raise ValueError("Clear the estimated due date when changing to this pregnancy status.")
        return self
