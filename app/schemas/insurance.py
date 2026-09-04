from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InsuranceCreateRequest(BaseModel):
    provider_name: str = Field(
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


class InsuranceUpdateRequest(BaseModel):
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
    provider_name: str
    policy_number: str | None
    membership_number: str | None
    plan_name: str | None
    coverage_status: str
    created_at: datetime
    updated_at: datetime