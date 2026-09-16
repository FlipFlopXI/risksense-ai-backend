from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.access_entitlement import EntitlementSource, EntitlementStatus
from app.models.clinician import ClinicianApprovalStatus
from app.models.patient_clinician import PatientClinicianStatus


class ClinicianLookupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    risk_sense_id: str
    first_name: str
    last_name: str
    professional_title: str | None
    specialization: str | None
    institution: str | None
    approval_status: ClinicianApprovalStatus


class PatientClinicianResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    patient_id: UUID
    clinician_id: UUID
    status: PatientClinicianStatus
    linked_at: datetime
    unlinked_at: datetime | None


class EntitlementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    patient_id: UUID
    source: EntitlementSource
    status: EntitlementStatus
    reference_number: str
    verification_source: str | None
    verified_at: datetime | None
    expires_at: datetime | None


class LinkClinicianRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_sense_id: str = Field(pattern=r"^RS-CLN-[0-9]{5}$")
