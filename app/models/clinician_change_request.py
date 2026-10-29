from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ClinicianChangeStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ClinicianChangeRequest(Base):
    __tablename__ = "clinician_change_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_clinician_change_status"),
        CheckConstraint("old_clinician_id <> new_clinician_id", name="ck_clinician_change_distinct"),
        Index("uq_clinician_change_pending_patient", "patient_id", unique=True,
              postgresql_where=text("status = 'pending'")),
        Index("ix_clinician_change_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    old_clinician_id: Mapped[UUID] = mapped_column(ForeignKey("clinicians.id", ondelete="RESTRICT"), nullable=False)
    new_clinician_id: Mapped[UUID] = mapped_column(ForeignKey("clinicians.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[ClinicianChangeStatus] = mapped_column(String(20), nullable=False, default=ClinicianChangeStatus.PENDING)
    reviewed_by_admin_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
