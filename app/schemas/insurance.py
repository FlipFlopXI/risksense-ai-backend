from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InsuranceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_name: str = Field(
        min_length=1,
        max_length=150,
    )
    clinician_risk_sense_id: str = Field(pattern=r"^RS-CLN-[0-9]{5}$")
    policy_number: str | None = Field(
        default=None,
        max_length=100,
    )
    membership_number: str | None = Field(
        default=None,
        max_length=100,
    )
    plan_name: str | None = Field(
        default=None,
        max_length=150,
    )


class InsuranceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )
    policy_number: str | None = Field(
        default=None,
        max_length=100,
    )
    membership_number: str | None = Field(
        default=None,
        max_length=100,
    )
    plan_name: str | None = Field(
        default=None,
        max_length=150,
    )


class InsuranceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    requested_clinician_risk_sense_id: str | None
    provider_name: str
    policy_number: str | None
    membership_number: str | None
    plan_name: str | None
    coverage_status: str
    verification_status: str
    verification_source: str | None
    verified_at: datetime | None
    coverage_starts_at: datetime | None
    coverage_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
