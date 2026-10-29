"""Patient-controlled delivery preference for sensitive result emails."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PatientNotificationPreference(Base):
    __tablename__ = "patient_notification_preferences"

    patient_id: Mapped[UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True,
    )
    email_elevated_results: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )
