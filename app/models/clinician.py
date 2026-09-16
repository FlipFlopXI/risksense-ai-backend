from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class ClinicianApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


class Clinician(Base):
    __tablename__ = "clinicians"
    __table_args__ = (
        CheckConstraint(
            "risk_sense_id ~ '^RS-CLN-[0-9]{5}$'",
            name="ck_clinicians_risk_sense_id_format",
        ),
        CheckConstraint(
            "approval_status IN ('pending', 'approved', 'suspended', 'rejected')",
            name="ck_clinicians_approval_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    risk_sense_id: Mapped[str] = mapped_column(
        String(12), unique=True, nullable=False, index=True
    )

    approval_status: Mapped[ClinicianApprovalStatus] = mapped_column(
        String(20), nullable=False, default=ClinicianApprovalStatus.PENDING, index=True
    )

    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    professional_title: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    license_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
    )

    specialization: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )

    institution: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="clinician",
    )
    patient_links = relationship("PatientClinician", back_populates="clinician")
    entitlements = relationship("AccessEntitlement", back_populates="clinician")
