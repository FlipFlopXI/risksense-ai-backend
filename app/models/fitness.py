from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ActivityEntry(Base):
    __tablename__ = "activity_entries"
    __table_args__ = (
        CheckConstraint("steps BETWEEN 0 AND 100000", name="ck_activity_steps"),
        CheckConstraint("activity_minutes BETWEEN 0 AND 1440", name="ck_activity_minutes"),
        CheckConstraint("activity_calories_kcal BETWEEN 0 AND 10000", name="ck_activity_calories"),
        CheckConstraint("distance_km BETWEEN 0 AND 500", name="ck_activity_distance"),
        Index("ix_activity_patient_date", "patient_id", "log_date"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    steps: Mapped[int] = mapped_column(Integer, nullable=False)
    activity_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    activity_calories_kcal: Mapped[float] = mapped_column(Float, nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BodyCompositionEntry(Base):
    __tablename__ = "body_composition_entries"
    __table_args__ = (
        CheckConstraint("skeletal_muscle_kg > 0 AND skeletal_muscle_kg <= 250", name="ck_body_composition_muscle"),
        CheckConstraint("body_fat_percent >= 0 AND body_fat_percent <= 100", name="ck_body_composition_fat"),
        Index("ix_body_composition_patient_time", "patient_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    skeletal_muscle_kg: Mapped[float] = mapped_column(Float, nullable=False)
    body_fat_percent: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
