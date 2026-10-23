from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class BodyMeasurement(Base):
    __tablename__ = "body_measurements"
    __table_args__ = (
        CheckConstraint("height_cm IS NULL OR (height_cm > 0 AND height_cm <= 300)", name="ck_body_measurement_height"),
        CheckConstraint("weight_kg IS NULL OR (weight_kg > 0 AND weight_kg <= 500)", name="ck_body_measurement_weight"),
        CheckConstraint("waist_circumference_cm IS NULL OR (waist_circumference_cm > 0 AND waist_circumference_cm <= 300)", name="ck_body_measurement_waist"),
        CheckConstraint("height_cm IS NOT NULL OR weight_kg IS NOT NULL OR waist_circumference_cm IS NOT NULL", name="ck_body_measurement_nonempty"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    height_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    waist_circumference_cm: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="health_profile")
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    patient = relationship("Patient", back_populates="body_measurements")

    @property
    def bmi(self) -> float | None:
        if self.height_cm is None or self.weight_kg is None:
            return None
        return round(self.weight_kg / ((self.height_cm / 100) ** 2), 2)
