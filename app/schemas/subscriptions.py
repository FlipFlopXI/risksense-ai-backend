from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.subscription import (
    SubscriptionPlan,
    SubscriptionStatus,
)


class SubscriptionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: SubscriptionPlan = SubscriptionPlan.FREE
    clinician_risk_sense_id: str = Field(pattern=r"^RS-CLN-[0-9]{5}$")


class SubscriptionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: SubscriptionPlan | None = None


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
