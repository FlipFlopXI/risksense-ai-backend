from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.subscription import (
    SubscriptionPlan,
    SubscriptionStatus,
)


class SubscriptionCreateRequest(BaseModel):
    plan: SubscriptionPlan = SubscriptionPlan.FREE


class SubscriptionUpdateRequest(BaseModel):
    plan: SubscriptionPlan | None = None
    status: SubscriptionStatus | None = None
    expires_at: datetime | None = None


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    plan: SubscriptionPlan
    status: SubscriptionStatus
    started_at: datetime
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime