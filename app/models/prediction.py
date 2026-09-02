from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    patient_id: Mapped[UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    model_id: Mapped[UUID] = mapped_column(
        ForeignKey("ml_models.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    prediction_target: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    risk_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    risk_classification: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    prediction_result: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    input_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    explanation: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    predicted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    model = relationship(
        "Model",
        back_populates="predictions",
    )

    patient = relationship(
        "Patient",
        back_populates="predictions",
    )

    reports = relationship(
        "Report",
        back_populates="prediction",
    )