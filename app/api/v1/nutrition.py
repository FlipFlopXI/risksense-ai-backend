from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.dependencies import get_database, require_role
from app.models.user import User, UserRole
from app.schemas.nutrition import (FoodLogCreate, FoodLogResponse, NutritionGoalResponse,
                                   NutritionGoalUpdate, NutritionSummary, PreviousFood, FoodSearchResult,
                                   WaterGoalUpdate, WaterGoalResponse, WaterLogCreate,
                                   WaterLogResponse, WaterSummary)
from app.schemas.nutrition import MetabolicLogCreate, MetabolicLogResponse, MetabolicSummary
from app.services import nutrition_service as service
from app.services.food_catalog import search_catalog

router = APIRouter(prefix="/nutrition", tags=["Nutrition"])


@router.get("/metabolic/summary", response_model=MetabolicSummary)
def metabolic_summary(day: date = Query(...), user: User = Depends(require_role(UserRole.PATIENT)),
                      db: Session = Depends(get_database)):
    return service.metabolic_summary(db, service.patient_for_user(db, user.id), day)


@router.post("/metabolic/entries", response_model=MetabolicLogResponse, status_code=201)
def create_metabolic_entry(request: MetabolicLogCreate,
                           user: User = Depends(require_role(UserRole.PATIENT)),
                           db: Session = Depends(get_database)):
    return service.create_metabolic_entry(db, service.patient_for_user(db, user.id), user.id, request)


@router.get("/water/summary", response_model=WaterSummary)
def water_summary(day: date = Query(...), user: User = Depends(require_role(UserRole.PATIENT)),
                  db: Session = Depends(get_database)):
    return service.water_summary(db, service.patient_for_user(db, user.id), day)


@router.put("/water/goal", response_model=WaterGoalResponse)
def set_water_goal(request: WaterGoalUpdate,
                   user: User = Depends(require_role(UserRole.PATIENT)),
                   db: Session = Depends(get_database)):
    return service.set_water_goal(db, service.patient_for_user(db, user.id),
                                  user.id, request.goal_ml)


@router.post("/water/entries", response_model=WaterLogResponse, status_code=201)
def create_water_entry(request: WaterLogCreate,
                       user: User = Depends(require_role(UserRole.PATIENT)),
                       db: Session = Depends(get_database)):
    return service.create_water_entry(db, service.patient_for_user(db, user.id),
                                      user.id, request)


@router.get("/catalog", response_model=list[FoodSearchResult])
def catalog(query: str = Query(..., min_length=2, max_length=80),
            user: User = Depends(require_role(UserRole.PATIENT))):
    return search_catalog(query)


@router.get("/foods", response_model=list[PreviousFood])
def previous_foods(query: str = Query("", max_length=80),
                   user: User = Depends(require_role(UserRole.PATIENT)),
                   db: Session = Depends(get_database)):
    return service.previous_foods(db, service.patient_for_user(db, user.id), query.strip())


@router.get("/summary", response_model=NutritionSummary)
def summary(day: date = Query(...), user: User = Depends(require_role(UserRole.PATIENT)),
            db: Session = Depends(get_database)):
    return service.summary(db, service.patient_for_user(db, user.id), day)


@router.put("/goal", response_model=NutritionGoalResponse)
def set_goal(request: NutritionGoalUpdate, user: User = Depends(require_role(UserRole.PATIENT)),
             db: Session = Depends(get_database)):
    return service.set_goal(db, service.patient_for_user(db, user.id), user.id, request.calories_kcal)


@router.post("/entries", response_model=FoodLogResponse, status_code=201)
def create_entry(request: FoodLogCreate, user: User = Depends(require_role(UserRole.PATIENT)),
                 db: Session = Depends(get_database)):
    return service.create_entry(db, service.patient_for_user(db, user.id), user.id, request)


@router.delete("/entries/{entry_id}", status_code=204)
def delete_entry(entry_id: UUID, user: User = Depends(require_role(UserRole.PATIENT)),
                 db: Session = Depends(get_database)):
    service.delete_entry(db, service.patient_for_user(db, user.id), user.id, entry_id)
    return Response(status_code=204)
