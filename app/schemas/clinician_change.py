from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ClinicianChangeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_sense_id: str = Field(pattern=r"^RS-CLN-[0-9]{5}$")


class ClinicianIdentity(BaseModel):
    risk_sense_id: str
    display_name: str
    institution: str | None


class ClinicianChangeResponse(BaseModel):
    id: UUID
    status: str
    created_at: datetime
    patient_id: UUID
    patient_name: str
    patient_email: str
    old_clinician: ClinicianIdentity
    new_clinician: ClinicianIdentity


class ClinicianChangeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern="^(approve|reject)$")
