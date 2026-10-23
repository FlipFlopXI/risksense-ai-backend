from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        CheckConstraint("risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 1)", name="ck_predictions_risk_score"),
    )

    @property
    def model_version(self) -> str | None:
        return (self.input_data or {}).get("model_version")

    @property
    def decision_threshold(self) -> float | None:
        return (self.input_data or {}).get("decision_threshold")

    @property
    def contributing_factors(self) -> list[dict]:
        return (self.input_data or {}).get("contributing_factors", [])

    @property
    def interpretation(self) -> str | None:
        factors = self.contributing_factors
        if not factors or self.risk_score is None:
            return None
        labels = {
            "age": "Age", "sex": "Sex", "bmi": "BMI",
            "waist_circumference": "Waist circumference",
            "systolic_bp": "Systolic blood pressure",
            "diastolic_bp": "Diastolic blood pressure",
            "total_cholesterol": "Total cholesterol",
            "fasting_blood_sugar_high": "Fasting glucose category",
        }
        raised = [labels.get(item["feature"], item["feature"])
                  for item in factors if item["direction"] == "raises"][:2]
        lowered = [labels.get(item["feature"], item["feature"])
                   for item in factors if item["direction"] == "lowers"][:2]
        parts = [f"The model estimated a {self.risk_score * 100:.1f}% score."]
        if raised:
            parts.append(f"{', '.join(raised)} raised the model score relative to its training baseline.")
        if lowered:
            parts.append(f"{', '.join(lowered)} lowered the model score relative to its training baseline.")
        parts.append("These are model contributions, not clinical causes or a diagnosis.")
        return " ".join(parts)

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
