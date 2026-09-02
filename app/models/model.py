from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Model(Base):
    __tablename__ = "ml_models"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    prediction_target: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    algorithm: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    dataset_name: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
    )

    accuracy: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    precision_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    recall_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    f1_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    model_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
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

    predictions = relationship(
        "Prediction",
        back_populates="model",
    )