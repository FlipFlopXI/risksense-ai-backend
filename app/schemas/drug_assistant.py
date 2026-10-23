from datetime import datetime
from typing import Any, Literal
from uuid import UUID
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator

EvidenceStatus = Literal["SOURCE_SUPPORTED", "LIMITED_EVIDENCE", "INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE", "UNSUPPORTED_DRUG"]


def without_credentials(value: str) -> str:
    if re.search(r"(?i)\b(password|secret|api[_ -]?key|access[_ -]?token)\s*[:=]|\bBearer\s+\S+|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|postgres(?:ql)?(?:\+\w+)?://", value):
        raise ValueError("Do not include credentials or tokens in clinical messages.")
    return value


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    patient_id: UUID | None = None
    title: str | None = Field(None, min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def no_secrets(cls, value):
        return without_credentials(value) if value is not None else value


class SessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["CLOSED"]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID | None = None
    patient_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def no_secrets(cls, value):
        return without_credentials(value)


class DrugSummary(BaseModel):
    drug_id: str
    generic_name: str
    display_name: str


class ChatResponse(BaseModel):
    session_id: UUID
    message_id: UUID
    intent: str
    drug: DrugSummary | None
    drugs: list[DrugSummary]
    resolution_status: str | None
    patient_context_used: dict[str, Any]
    summary: str
    evidence_status: EvidenceStatus
    sources: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    safety_message: str
    urgent: bool
    urgent_category: str | None
    generated_at: datetime
    pregnancy_information: list[dict[str, Any]]
    lactation_information: list[dict[str, Any]]
    reproductive_information: list[dict[str, Any]]
    general_information: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    interactions: list[dict[str, Any]]
    monitoring_considerations: list[dict[str, Any]]
    clinician_discussion_points: list[str]
    response_validation_failed: bool = False


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    patient_id: UUID
    initiated_by_user_id: UUID | None
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    session_id: UUID
    sequence: int
    role: str
    content: str | None
    response: ChatResponse | None
    created_at: datetime


class DrugAssistantStatusResponse(BaseModel):
    runtime_status: str
    artifact_integrity_status: str
    catalogue_version: str
    catalogue_medication_count: int
    therapeutic_group_count: int
    intent_count: int
    policy_version: str
    evidence_provider_status: str
    reviewed_evidence_count: int
    review_required_operation_count: int
    ingestion_status_counts: dict[str, int]
    complete_count: int
    partial_count: int
    insufficient_count: int
    last_coverage_generation_time: datetime | None
    published_medication_count: int = 0
    coverage_by_topic: dict[str, int] = Field(default_factory=dict)
    coverage_by_source: dict[str, int] = Field(default_factory=dict)
    pending_review_record_count: int = 0
    dailymed_unresolved_product_count: int = 0
    retrieval_failure_count: int = 0
