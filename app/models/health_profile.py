from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class HealthProfile(Base):
    __tablename__ = "health_profiles"

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

    height_cm: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    weight_kg: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    blood_type: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
    )

    smoking_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    activity_level: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    family_history: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    existing_conditions: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )

    current_medications: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )

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
        back_populates="health_profile",
    )