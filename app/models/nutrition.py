from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class NutritionGoal(Base):
    __tablename__ = "nutrition_goals"
    __table_args__ = (
        UniqueConstraint("patient_id", name="uq_nutrition_goals_patient"),
        CheckConstraint("calories_kcal BETWEEN 500 AND 6000", name="ck_nutrition_goal_calories"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    calories_kcal: Mapped[int] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class FoodLogEntry(Base):
    __tablename__ = "food_log_entries"
    __table_args__ = (
        CheckConstraint("meal_type IN ('breakfast','lunch','dinner','morning_snack','afternoon_snack','evening_snack')", name="ck_food_log_meal_type"),
        CheckConstraint("amount_g > 0 AND amount_g <= 5000", name="ck_food_log_amount"),
        CheckConstraint("calories_kcal >= 0 AND calories_kcal <= 20000", name="ck_food_log_calories"),
        CheckConstraint("carbs_g >= 0 AND fat_g >= 0 AND protein_g >= 0", name="ck_food_log_macros"),
        Index("ix_food_log_patient_date", "patient_id", "log_date"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[str] = mapped_column(String(24), nullable=False)
    food_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(100))
    amount_g: Mapped[Decimal] = mapped_column(Numeric(9, 2), nullable=False)
    calories_kcal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    carbs_g: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    fat_g: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    protein_g: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WaterGoal(Base):
    __tablename__ = "water_goals"
    __table_args__ = (
        UniqueConstraint("patient_id", name="uq_water_goals_patient"),
        CheckConstraint("goal_ml BETWEEN 250 AND 4000", name="ck_water_goal_ml"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    goal_ml: Mapped[int] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class WaterLogEntry(Base):
    __tablename__ = "water_log_entries"
    __table_args__ = (
        CheckConstraint("amount_ml BETWEEN 1 AND 4000", name="ck_water_log_amount"),
        Index("ix_water_log_patient_date", "patient_id", "log_date"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_ml: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MetabolicLogEntry(Base):
    __tablename__ = "metabolic_log_entries"
    __table_args__ = (
        CheckConstraint("category IN ('fasting','post_meal','general','insulin_dose')", name="ck_metabolic_log_category"),
        CheckConstraint("value > 0 AND value <= 1000", name="ck_metabolic_log_value"),
        CheckConstraint("(category = 'insulin_dose' AND unit = 'U') OR (category <> 'insulin_dose' AND unit = 'mg/dL')", name="ck_metabolic_log_unit"),
        Index("ix_metabolic_log_patient_date", "patient_id", "log_date"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
