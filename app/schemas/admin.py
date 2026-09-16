from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

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
