from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class InsuranceVerificationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Insurance(Base):
    __tablename__ = "insurance"
    __table_args__ = (
        CheckConstraint("verification_status IN ('pending', 'verified', 'rejected', 'expired')", name="ck_insurance_verification_status"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    patient_id: Mapped[UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    requested_clinician_risk_sense_id: Mapped[Optional[str]] = mapped_column(String(12))

    provider_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    policy_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    membership_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    plan_name: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )

    coverage_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
    )

    verification_status: Mapped[InsuranceVerificationStatus] = mapped_column(
        String(20), nullable=False, default=InsuranceVerificationStatus.PENDING, index=True
    )
    verification_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    coverage_starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    coverage_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

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

    patient = relationship(
        "Patient",
        back_populates="insurance",
    )
    entitlements = relationship("AccessEntitlement", back_populates="insurance")
