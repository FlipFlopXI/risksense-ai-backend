from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_database, require_role
from app.models.user import User, UserRole
from app.schemas.fitness import (ActivityCreate, ActivityResponse, ActivitySummary,
                                 BodyCompositionCreate, BodyCompositionResponse,
                                 BodySummary, WeightUpdate)
from app.services import fitness_service as service

router = APIRouter(prefix="/fitness", tags=["Fitness"])


@router.get("/activity/summary", response_model=ActivitySummary)
def activity_summary(day: date = Query(...), user: User = Depends(require_role(UserRole.PATIENT)),
                     db: Session = Depends(get_database)):
    return service.activity_summary(db, service.patient_for_user(db, user.id), day)


@router.post("/activity/entries", response_model=ActivityResponse, status_code=201)
def create_activity(request: ActivityCreate, user: User = Depends(require_role(UserRole.PATIENT)),
                    db: Session = Depends(get_database)):
    return service.create_activity(db, service.patient_for_user(db, user.id), user.id, request)


@router.get("/body", response_model=BodySummary)
def body_summary(user: User = Depends(require_role(UserRole.PATIENT)),
                 db: Session = Depends(get_database)):
    return service.body_summary(db, service.patient_for_user(db, user.id))


@router.put("/body/weight", response_model=BodySummary)
def update_weight(request: WeightUpdate, user: User = Depends(require_role(UserRole.PATIENT)),
                  db: Session = Depends(get_database)):
    return service.update_weight(db, service.patient_for_user(db, user.id), user.id, request.weight_kg)


@router.post("/body/composition", response_model=BodyCompositionResponse, status_code=201)
def create_composition(request: BodyCompositionCreate,
                       user: User = Depends(require_role(UserRole.PATIENT)),
                       db: Session = Depends(get_database)):
    return service.create_composition(db, service.patient_for_user(db, user.id), user.id, request)
