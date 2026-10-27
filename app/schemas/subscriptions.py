from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.subscription import (
    SubscriptionPlan,
    SubscriptionStatus,
)


class SubscriptionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: SubscriptionPlan
    clinician_risk_sense_id: str = Field(pattern=r"^RS-CLN-[0-9]{5}$")

    @field_validator("plan")
    @classmethod
    def no_free_subscription(cls, value: SubscriptionPlan) -> SubscriptionPlan:
        if value == SubscriptionPlan.FREE:
            raise ValueError("Choose a Standard or Premium subscription plan.")
        return value


class SubscriptionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: SubscriptionPlan | None = None

    @field_validator("plan")
    @classmethod
    def no_free_subscription(cls, value: SubscriptionPlan | None) -> SubscriptionPlan | None:
        if value == SubscriptionPlan.FREE:
            raise ValueError("Choose a Standard or Premium subscription plan.")
        return value


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    requested_clinician_risk_sense_id: str | None
    plan: SubscriptionPlan
    status: SubscriptionStatus
    started_at: datetime
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
