"""Patient-owned food logging with source-attributed nutrient snapshots."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.nutrition import FoodLogEntry, NutritionGoal, WaterGoal, WaterLogEntry, MetabolicLogEntry
from app.models.patient import Patient
from app.schemas.nutrition import FoodLogCreate, NutritionDay, NutritionSummary, PreviousFood, WaterLogCreate, WaterDay, WaterSummary, MetabolicLogCreate, MetabolicSummary
from app.services.audit_service import add_audit_event
from app.services.food_catalog import get_catalog_product, scale_nutrients


def patient_for_user(db: Session, user_id: UUID) -> Patient:
    patient = db.scalar(select(Patient).where(Patient.user_id == user_id))
    if patient is None:
        raise HTTPException(404, "Patient profile not found.")
    return patient


def get_goal(db: Session, patient_id: UUID) -> NutritionGoal | None:
    return db.scalar(select(NutritionGoal).where(NutritionGoal.patient_id == patient_id))


def set_goal(db: Session, patient: Patient, user_id: UUID, calories: int) -> NutritionGoal:
    goal = get_goal(db, patient.id)
    if goal is None:
        goal = NutritionGoal(patient_id=patient.id, calories_kcal=calories)
        db.add(goal)
    else:
        goal.calories_kcal = calories
    add_audit_event(db, "NUTRITION_GOAL_UPDATED", user_id=user_id,
                    resource_type="nutrition_goal", resource_id=str(patient.id))
    db.commit()
    db.refresh(goal)
    return goal


def create_entry(db: Session, patient: Patient, user_id: UUID, request: FoodLogCreate) -> FoodLogEntry:
    if request.source == "open_food_facts":
        product = get_catalog_product(request.source_id)
        food_name = product.name
        values = (product.calories_per_100g, product.carbs_per_100g,
                  product.fat_per_100g, product.protein_per_100g)
    else:
        food_name = request.food_name
        values = (request.calories_per_100g, request.carbs_per_100g,
                  request.fat_per_100g, request.protein_per_100g)
    totals = scale_nutrients(values, request.amount_g)
    entry = FoodLogEntry(
        patient_id=patient.id, log_date=request.log_date, meal_type=request.meal_type,
        food_name=food_name, source=request.source,
        source_id=request.source_id if request.source == "open_food_facts" else None,
        amount_g=request.amount_g, calories_kcal=totals[0], carbs_g=totals[1],
        fat_g=totals[2], protein_g=totals[3],
    )
    db.add(entry)
    db.flush()
    add_audit_event(db, "FOOD_LOG_CREATED", user_id=user_id,
                    resource_type="food_log", resource_id=str(entry.id))
    db.commit()
    db.refresh(entry)
    return entry


def delete_entry(db: Session, patient: Patient, user_id: UUID, entry_id: UUID) -> None:
    entry = db.scalar(select(FoodLogEntry).where(FoodLogEntry.id == entry_id,
                                                FoodLogEntry.patient_id == patient.id))
    if entry is None:
        raise HTTPException(404, "Food log entry not found.")
    db.delete(entry)
    add_audit_event(db, "FOOD_LOG_DELETED", user_id=user_id,
                    resource_type="food_log", resource_id=str(entry_id))
    db.commit()


def summary(db: Session, patient: Patient, day: date) -> NutritionSummary:
    first = day - timedelta(days=6)
    rows = db.scalars(select(FoodLogEntry).where(
        FoodLogEntry.patient_id == patient.id, FoodLogEntry.log_date >= first,
        FoodLogEntry.log_date <= day,
    ).order_by(FoodLogEntry.created_at)).all()
    entries = [row for row in rows if row.log_date == day]

    def total(field: str) -> Decimal:
        return sum((getattr(row, field) for row in entries), Decimal(0))

    history = [NutritionDay(date=first + timedelta(days=index),
                            calories_kcal=sum((row.calories_kcal for row in rows
                                               if row.log_date == first + timedelta(days=index)), Decimal(0)))
               for index in range(7)]
    goal = get_goal(db, patient.id)
    return NutritionSummary(date=day, goal_kcal=goal.calories_kcal if goal else None,
                            calories_kcal=total("calories_kcal"), carbs_g=total("carbs_g"),
                            fat_g=total("fat_g"), protein_g=total("protein_g"),
                            history=history, entries=entries)


def previous_foods(db: Session, patient: Patient, query: str) -> list[PreviousFood]:
    rows = db.scalars(select(FoodLogEntry).where(
        FoodLogEntry.patient_id == patient.id,
        FoodLogEntry.food_name.ilike(f"%{query}%"),
    ).order_by(FoodLogEntry.created_at.desc()).limit(100)).all()
    found: dict[str, PreviousFood] = {}
    for row in rows:
        key = row.food_name.casefold()
        if key in found:
            continue
        scale = Decimal(100) / row.amount_g
        found[key] = PreviousFood(
            food_name=row.food_name,
            source=row.source,
            source_id=row.source_id,
            calories_per_100g=(row.calories_kcal * scale).quantize(Decimal("0.01")),
            carbs_per_100g=(row.carbs_g * scale).quantize(Decimal("0.01")),
            fat_per_100g=(row.fat_g * scale).quantize(Decimal("0.01")),
            protein_per_100g=(row.protein_g * scale).quantize(Decimal("0.01")),
        )
        if len(found) == 20:
            break
    return list(found.values())


def water_summary(db: Session, patient: Patient, day: date) -> WaterSummary:
    first = day - timedelta(days=6)
    rows = db.scalars(select(WaterLogEntry).where(
        WaterLogEntry.patient_id == patient.id,
        WaterLogEntry.log_date >= first,
        WaterLogEntry.log_date <= day,
    ).order_by(WaterLogEntry.created_at.desc(), WaterLogEntry.id.desc())).all()
    entries = [row for row in rows if row.log_date == day]
    totals: dict[date, int] = {}
    for row in rows:
        totals[row.log_date] = totals.get(row.log_date, 0) + row.amount_ml
    goal = db.scalar(select(WaterGoal).where(WaterGoal.patient_id == patient.id))
    return WaterSummary(
        date=day, goal_ml=goal.goal_ml if goal else None,
        total_ml=totals.get(day, 0), entries=entries,
        history=[WaterDay(date=first + timedelta(days=i),
                          amount_ml=totals.get(first + timedelta(days=i), 0))
                 for i in range(7)],
    )


def set_water_goal(db: Session, patient: Patient, user_id: UUID, goal_ml: int) -> WaterGoal:
    goal = db.scalar(select(WaterGoal).where(WaterGoal.patient_id == patient.id))
    if goal is None:
        goal = WaterGoal(patient_id=patient.id, goal_ml=goal_ml)
        db.add(goal)
    else:
        goal.goal_ml = goal_ml
    add_audit_event(db, "WATER_GOAL_UPDATED", user_id=user_id,
                    resource_type="water_goal", resource_id=str(patient.id))
    db.commit()
    db.refresh(goal)
    return goal


def create_water_entry(db: Session, patient: Patient, user_id: UUID,
                       request: WaterLogCreate) -> WaterLogEntry:
    entry = WaterLogEntry(patient_id=patient.id, log_date=request.log_date,
                          amount_ml=request.amount_ml)
    db.add(entry)
    db.flush()
    add_audit_event(db, "WATER_LOG_CREATED", user_id=user_id,
                    resource_type="water_log", resource_id=str(entry.id))
    db.commit()
    db.refresh(entry)
    return entry


def metabolic_summary(db: Session, patient: Patient, day: date) -> MetabolicSummary:
    first = day - timedelta(days=6)
    entries = db.scalars(select(MetabolicLogEntry).where(
        MetabolicLogEntry.patient_id == patient.id,
        MetabolicLogEntry.log_date >= first,
        MetabolicLogEntry.log_date <= day,
    ).order_by(MetabolicLogEntry.created_at.desc(), MetabolicLogEntry.id.desc())).all()
    return MetabolicSummary(date=day, entries=entries)


def create_metabolic_entry(db: Session, patient: Patient, user_id: UUID,
                           request: MetabolicLogCreate) -> MetabolicLogEntry:
    entry = MetabolicLogEntry(
        patient_id=patient.id, log_date=request.log_date,
        category=request.category, value=request.value,
        unit="U" if request.category == "insulin_dose" else "mg/dL",
    )
    db.add(entry)
    db.flush()
    add_audit_event(db, "METABOLIC_LOG_CREATED", user_id=user_id,
                    resource_type="metabolic_log", resource_id=str(entry.id))
    db.commit()
    db.refresh(entry)
    return entry
