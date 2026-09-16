from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class PatientClinicianStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class PatientClinician(Base):
    __tablename__ = "patient_clinicians"
    __table_args__ = (
        UniqueConstraint("patient_id", "clinician_id", name="uq_patient_clinician"),
        CheckConstraint("unlinked_at IS NULL OR unlinked_at >= linked_at", name="ck_patient_clinicians_dates"),
        CheckConstraint("status IN ('active', 'inactive')", name="ck_patient_clinicians_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    clinician_id: Mapped[UUID] = mapped_column(ForeignKey("clinicians.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[PatientClinicianStatus] = mapped_column(String(20), nullable=False, default=PatientClinicianStatus.ACTIVE, index=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    patient = relationship("Patient", back_populates="clinician_links")
    clinician = relationship("Clinician", back_populates="patient_links")
