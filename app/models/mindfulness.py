from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class MoodEntry(Base):
    __tablename__ = "mood_entries"
    __table_args__ = (
        CheckConstraint("mood IN ('amazing','good','fine','bad','horrible')", name="ck_mood_entries_mood"),
        Index("ix_mood_entries_patient_date", "patient_id", "log_date"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    mood: Mapped[str] = mapped_column(String(12), nullable=False)
    emotion: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BreathingSession(Base):
    __tablename__ = "breathing_sessions"
    __table_args__ = (
        CheckConstraint("exercise IN ('box','478','belly','custom')", name="ck_breathing_sessions_exercise"),
        CheckConstraint("duration_seconds > 0 AND duration_seconds <= 3600", name="ck_breathing_sessions_duration"),
        Index("ix_breathing_sessions_patient_started", "patient_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    exercise: Mapped[str] = mapped_column(String(12), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MeditationSession(Base):
    __tablename__ = "meditation_sessions"
    __table_args__ = (
        CheckConstraint("category IN ('sleep','ambient','nature','instrumental')",
                        name="ck_meditation_sessions_category"),
        CheckConstraint("duration_seconds > 0 AND duration_seconds <= 14400",
                        name="ck_meditation_sessions_duration"),
        Index("ix_meditation_sessions_patient_started", "patient_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    track_id: Mapped[str] = mapped_column(String(40), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
