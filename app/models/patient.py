from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    date_of_birth: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
    )

    phone_number: Mapped[Optional[str]] = mapped_column(
        String(30),
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

    user = relationship(
        "User",
        back_populates="patient",
    )

    health_profile = relationship(
        "HealthProfile",
        back_populates="patient",
        uselist=False,
        cascade="all, delete-orphan",
    )

    subscription = relationship(
        "Subscription",
        back_populates="patient",
        uselist=False,
        cascade="all, delete-orphan",
    )

    insurance = relationship(
        "Insurance",
        back_populates="patient",
        uselist=False,
        cascade="all, delete-orphan",
    )

    vitals = relationship(
        "Vital",
        back_populates="patient",
        cascade="all, delete-orphan",
        order_by="Vital.recorded_at",
    )