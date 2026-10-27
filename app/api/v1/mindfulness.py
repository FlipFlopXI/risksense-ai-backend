from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_database, require_role
from app.models.user import User, UserRole
from app.schemas.mindfulness import (BreathingSessionCreate, BreathingSessionResponse,
                                     BreathingSummary, MeditationSessionCreate,
                                     MeditationSessionResponse, MeditationSummary,
                                     MoodCreate, MoodResponse, MoodSummary)
from app.services import mindfulness_service as service

router = APIRouter(prefix="/mindfulness", tags=["Mindfulness"])


@router.get("/moods/summary", response_model=MoodSummary)
def mood_summary(day: date = Query(...), user: User = Depends(require_role(UserRole.PATIENT)),
                 db: Session = Depends(get_database)):
    return service.mood_summary(db, service.patient_for_user(db, user.id), day)


@router.post("/moods", response_model=MoodResponse, status_code=201)
def create_mood(request: MoodCreate, user: User = Depends(require_role(UserRole.PATIENT)),
                db: Session = Depends(get_database)):
    return service.create_mood(db, service.patient_for_user(db, user.id), user.id, request)


@router.get("/breathing/summary", response_model=BreathingSummary)
def breathing_summary(day: date = Query(...), timezone_offset_minutes: int = Query(0, ge=-720, le=840),
                      user: User = Depends(require_role(UserRole.PATIENT)),
                      db: Session = Depends(get_database)):
    return service.breathing_summary(db, service.patient_for_user(db, user.id),
                                     day, timezone_offset_minutes)


@router.post("/breathing/sessions", response_model=BreathingSessionResponse, status_code=201)
def create_breathing_session(request: BreathingSessionCreate,
                             user: User = Depends(require_role(UserRole.PATIENT)),
                             db: Session = Depends(get_database)):
    return service.create_breathing_session(
        db, service.patient_for_user(db, user.id), user.id, request)


@router.get("/meditation/summary", response_model=MeditationSummary)
def meditation_summary(day: date = Query(...),
                       timezone_offset_minutes: int = Query(0, ge=-720, le=840),
                       user: User = Depends(require_role(UserRole.PATIENT)),
                       db: Session = Depends(get_database)):
    return service.meditation_summary(
        db, service.patient_for_user(db, user.id), day, timezone_offset_minutes)


@router.post("/meditation/sessions", response_model=MeditationSessionResponse, status_code=201)
def create_meditation_session(request: MeditationSessionCreate,
                              user: User = Depends(require_role(UserRole.PATIENT)),
                              db: Session = Depends(get_database)):
    return service.create_meditation_session(
        db, service.patient_for_user(db, user.id), user.id, request)
