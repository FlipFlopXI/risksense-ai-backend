from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MealType = Literal["breakfast", "lunch", "dinner", "morning_snack", "afternoon_snack", "evening_snack"]


class NutritionGoalUpdate(BaseModel):
    calories_kcal: int = Field(ge=500, le=6000)


class NutritionGoalResponse(NutritionGoalUpdate):
    model_config = ConfigDict(from_attributes=True)
    updated_at: datetime


class FoodLogCreate(BaseModel):
    log_date: date
    meal_type: MealType
    food_name: str = Field(min_length=2, max_length=200)
    source: Literal["open_food_facts", "self_reported"] = "self_reported"
    source_id: str | None = Field(default=None, max_length=100)
    amount_g: Decimal = Field(gt=0, le=5000, max_digits=9, decimal_places=2)
    calories_per_100g: Decimal | None = Field(default=None, ge=0, le=1000)
    carbs_per_100g: Decimal | None = Field(default=None, ge=0, le=100)
    fat_per_100g: Decimal | None = Field(default=None, ge=0, le=100)
    protein_per_100g: Decimal | None = Field(default=None, ge=0, le=100)

    @field_validator("food_name")
    @classmethod
    def clean_food_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Enter a food name.")
        return cleaned

    @model_validator(mode="after")
    def validate_source(self):
        if self.source == "open_food_facts":
            if not self.source_id or not self.source_id.isdigit():
                raise ValueError("A product barcode is required.")
        elif any(value is None for value in (
            self.calories_per_100g, self.carbs_per_100g,
            self.fat_per_100g, self.protein_per_100g,
        )):
            raise ValueError("Enter all nutrition values from the food label.")
        return self


class FoodSearchResult(BaseModel):
    code: str
    name: str
    brand: str | None = None
    calories_per_100g: Decimal
    carbs_per_100g: Decimal
    fat_per_100g: Decimal
    protein_per_100g: Decimal


class FoodLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    log_date: date
    meal_type: MealType
    food_name: str
    source: str
    amount_g: Decimal
    calories_kcal: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    protein_g: Decimal
    created_at: datetime


class PreviousFood(BaseModel):
    food_name: str
    source: str
    source_id: str | None
    calories_per_100g: Decimal
    carbs_per_100g: Decimal
    fat_per_100g: Decimal
    protein_per_100g: Decimal


class NutritionDay(BaseModel):
    date: date
    calories_kcal: Decimal


class NutritionSummary(BaseModel):
    date: date
    goal_kcal: int | None
    calories_kcal: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    protein_g: Decimal
    history: list[NutritionDay]
    entries: list[FoodLogResponse]


class WaterGoalUpdate(BaseModel):
    goal_ml: int = Field(ge=250, le=4000)


class WaterGoalResponse(WaterGoalUpdate):
    model_config = ConfigDict(from_attributes=True)
    updated_at: datetime


class WaterLogCreate(BaseModel):
    log_date: date
    amount_ml: int = Field(ge=1, le=4000)


class WaterLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    log_date: date
    amount_ml: int
    created_at: datetime


class WaterDay(BaseModel):
    date: date
    amount_ml: int


class WaterSummary(BaseModel):
    date: date
    goal_ml: int | None
    total_ml: int
    history: list[WaterDay]
    entries: list[WaterLogResponse]


MetabolicCategory = Literal["fasting", "post_meal", "general", "insulin_dose"]


class MetabolicLogCreate(BaseModel):
    log_date: date
    category: MetabolicCategory
    value: Decimal = Field(gt=0, le=1000, max_digits=8, decimal_places=2)


class MetabolicLogResponse(MetabolicLogCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    unit: str
    created_at: datetime


class MetabolicSummary(BaseModel):
    date: date
    entries: list[MetabolicLogResponse]
