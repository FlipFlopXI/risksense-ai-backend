from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class HealthProfile(Base):
    __tablename__ = "health_profiles"
    __table_args__ = (CheckConstraint(
        "waist_circumference_cm IS NULL OR (waist_circumference_cm > 0 AND waist_circumference_cm <= 300)",
        name="ck_health_profiles_waist_cm",
    ), CheckConstraint("pregnancy_status IS NULL OR pregnancy_status IN ('NOT_PREGNANT','PREGNANT','POSSIBLY_PREGNANT','TRYING_TO_CONCEIVE','POSTPARTUM','PREFER_NOT_TO_SAY','UNKNOWN')", name="ck_profile_pregnancy_status"),
       CheckConstraint("breastfeeding_status IS NULL OR breastfeeding_status IN ('YES','NO','PREFER_NOT_TO_SAY','UNKNOWN')", name="ck_profile_breastfeeding_status"))
    waist_circumference_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pregnancy_status: Mapped[str | None] = mapped_column(String(30))
    estimated_due_date: Mapped[date | None] = mapped_column(Date)
    pregnancy_context_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    breastfeeding_status: Mapped[str | None] = mapped_column(String(30))
    infant_date_of_birth: Mapped[date | None] = mapped_column(Date)
    infant_premature: Mapped[bool | None] = mapped_column()

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

    @property
    def bmi(self) -> float | None:
        if not self.height_cm or not self.weight_kg:
            return None
        return round(self.weight_kg / ((self.height_cm / 100) ** 2), 2)
    alcohol_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    family_history_diabetes: Mapped[Optional[bool]] = mapped_column(nullable=True)
    family_history_heart_disease: Mapped[Optional[bool]] = mapped_column(nullable=True)
    family_history_hypertension: Mapped[Optional[bool]] = mapped_column(nullable=True)
