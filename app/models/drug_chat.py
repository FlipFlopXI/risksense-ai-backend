from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class DrugChatSession(Base):
    __tablename__ = "drug_chat_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','CLOSED')", name="ck_drug_session_status"),
        CheckConstraint("next_sequence >= 0", name="ck_drug_session_sequence"),
        Index("ix_drug_sessions_patient_updated", "patient_id", "updated_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    initiated_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(10), default="OPEN", nullable=False)
    state: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    next_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DrugChatMessage(Base):
    __tablename__ = "drug_chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="ck_drug_message_role"),
        CheckConstraint("sequence > 0", name="ck_drug_message_sequence"),
        UniqueConstraint("session_id", "sequence", name="uq_drug_message_sequence"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("drug_chat_sessions.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    response: Mapped[dict | None] = mapped_column(JSONB)
    intent: Mapped[str] = mapped_column(String(60), nullable=False)
    resolved_drug_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    evidence_status: Mapped[str] = mapped_column(String(30), nullable=False)
    patient_context: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    source_provenance: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    safety_classification: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
