from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.subscription import SubscriptionPlan


class ActivationIssueResponse(BaseModel):
    activation_url: str
    expires_at: datetime
    expires_in: int


class ActivationExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=40, max_length=200)


class ActivationExchangeResponse(BaseModel):
    activation_credential: str
    expires_at: datetime
    email: str


class ActivationContextResponse(BaseModel):
    email: str
    active: bool
    expires_at: datetime


class ActivationCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["subscription", "insurance"]
    clinician_risk_sense_id: str = Field(pattern=r"^RS-CLN-[0-9]{5}$")
    plan: SubscriptionPlan | None = None
    provider_name: str | None = Field(default=None, min_length=1, max_length=150)
    policy_number: str | None = Field(default=None, max_length=100)
    membership_number: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def exactly_one_method(self):
        if self.method == "subscription":
            if self.plan is None or any((self.provider_name, self.policy_number, self.membership_number)):
                raise ValueError("A subscription plan and no insurance details are required.")
        elif self.provider_name is None or not self.provider_name.strip() or self.plan is not None:
            raise ValueError("An insurance provider and no subscription plan are required.")
        return self


class ActivationResult(BaseModel):
    active: bool
    status: Literal["active"]
    access_method: Literal["subscription", "insurance"]
    clinician_linked: bool


class AccessStatus(BaseModel):
    active: bool
    status: Literal["active", "inactive"]
    access_method: Literal["subscription", "insurance"] | None
    clinician_linked: bool
