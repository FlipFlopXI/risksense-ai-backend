from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Vital(Base):
    __tablename__ = "vitals"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    patient_id: Mapped[UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    heart_rate: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    oxygen_saturation: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    temperature: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    blood_pressure_systolic: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    blood_pressure_diastolic: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    patient = relationship(
        "Patient",
        back_populates="vitals",
    )