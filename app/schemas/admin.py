from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Literal

from app.models.clinician import ClinicianApprovalStatus
from app.models.user import UserRole


class AdminMetricsResponse(BaseModel):
    total_users: int
    clinician_count: int
    prediction_count: int
    audit_event_count: int


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    display_name: str | None = None


class AdminActionSummary(BaseModel):
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    performed_at: datetime


class AdminProfileResponse(AdminUserResponse):
    admin_id: UUID
    last_login_at: datetime | None = None
    last_action: AdminActionSummary | None = None


class ClinicianApprovalRequest(BaseModel):
    status: ClinicianApprovalStatus


class ClinicianProvisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    temporary_password: str = Field(min_length=12, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    professional_title: str | None = Field(default=None, max_length=100)
    license_number: str | None = Field(default=None, max_length=100)
    specialization: str | None = Field(default=None, max_length=150)
    institution: str | None = Field(default=None, max_length=200)
    gender: Literal["female", "male", "unspecified"] | None = None
