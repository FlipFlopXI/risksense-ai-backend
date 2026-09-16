from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class EntitlementSource(str, Enum):
    SUBSCRIPTION = "subscription"
    INSURANCE = "insurance"


class EntitlementStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class AccessEntitlement(Base):
    __tablename__ = "access_entitlements"
    __table_args__ = (
        CheckConstraint(
            "(source = 'subscription' AND subscription_id IS NOT NULL AND insurance_id IS NULL) OR "
            "(source = 'insurance' AND insurance_id IS NOT NULL AND subscription_id IS NULL)",
            name="ck_entitlement_source_reference",
        ),
        CheckConstraint("expires_at IS NULL OR verified_at IS NULL OR expires_at >= verified_at", name="ck_entitlement_dates"),
        CheckConstraint("source IN ('subscription', 'insurance')", name="ck_entitlement_source"),
        CheckConstraint("status IN ('pending', 'active', 'expired', 'cancelled')", name="ck_entitlement_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[EntitlementSource] = mapped_column(String(20), nullable=False)
    status: Mapped[EntitlementStatus] = mapped_column(String(20), nullable=False, default=EntitlementStatus.PENDING, index=True)
    clinician_id: Mapped[UUID | None] = mapped_column(ForeignKey("clinicians.id", ondelete="SET NULL"), index=True)
    insurance_id: Mapped[UUID | None] = mapped_column(ForeignKey("insurance.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[UUID | None] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True)
    reference_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    verification_source: Mapped[str | None] = mapped_column(String(50))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    patient = relationship("Patient", back_populates="entitlements")
    clinician = relationship("Clinician", back_populates="entitlements")
    insurance = relationship("Insurance", back_populates="entitlements")
    subscription = relationship("Subscription", back_populates="entitlements")
