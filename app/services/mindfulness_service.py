from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mindfulness import BreathingSession, MeditationSession, MoodEntry
from app.models.patient import Patient
from app.schemas.mindfulness import (BreathingDay, BreathingSessionCreate,
                                     BreathingSummary, MeditationDay,
                                     MeditationSessionCreate, MeditationSummary,
                                     MoodCreate, MoodDay, MoodSummary)
from app.services.audit_service import add_audit_event
from app.services.nutrition_service import patient_for_user

_SCORES = {"horrible": 1, "bad": 2, "fine": 3, "good": 4, "amazing": 5}
_MOODS = ("horrible", "bad", "fine", "good", "amazing")


def mood_summary(db: Session, patient: Patient, day: date) -> MoodSummary:
    first = day - timedelta(days=6)
    entries = db.scalars(select(MoodEntry).where(
        MoodEntry.patient_id == patient.id,
        MoodEntry.log_date >= first, MoodEntry.log_date <= day,
    ).order_by(MoodEntry.created_at.desc(), MoodEntry.id.desc())).all()
    today_entries = [entry for entry in entries if entry.log_date == day]
    history = []
    for offset in range(7):
        current = first + timedelta(days=offset)
        scores = [_SCORES[entry.mood] for entry in entries if entry.log_date == current]
        average = sum(scores) / len(scores) if scores else None
        history.append(MoodDay(
            date=current, count=len(scores), average_score=average,
            average_mood=_MOODS[min(4, int(average + .5) - 1)] if average is not None else None,
        ))
    return MoodSummary(date=day, latest=today_entries[0] if today_entries else None,
                       today_entries=today_entries, history=history)


def create_mood(db: Session, patient: Patient, user_id: UUID,
                request: MoodCreate) -> MoodEntry:
    entry = MoodEntry(patient_id=patient.id, **request.model_dump())
    db.add(entry)
    db.flush()
    add_audit_event(db, "MOOD_LOG_CREATED", user_id=user_id,
                    resource_type="mood_entry", resource_id=str(entry.id))
    db.commit()
    db.refresh(entry)
    return entry


def breathing_summary(db: Session, patient: Patient, day: date,
                      timezone_offset_minutes: int = 0) -> BreathingSummary:
    first = day - timedelta(days=6)
    offset = timedelta(minutes=timezone_offset_minutes)
    start = datetime.combine(first, time.min, timezone.utc) - offset
    end = datetime.combine(day + timedelta(days=1), time.min, timezone.utc) - offset
    entries = db.scalars(select(BreathingSession).where(
        BreathingSession.patient_id == patient.id,
        BreathingSession.started_at >= start,
        BreathingSession.started_at < end,
    )).all()
    return BreathingSummary(history=[BreathingDay(
        date=current,
        count=sum((entry.started_at.astimezone(timezone.utc) + offset).date() == current
                  for entry in entries),
        duration_seconds=sum(entry.duration_seconds for entry in entries
                             if (entry.started_at.astimezone(timezone.utc) + offset).date() == current),
    ) for current in (first + timedelta(days=offset) for offset in range(7))])


def create_breathing_session(db: Session, patient: Patient, user_id: UUID,
                             request: BreathingSessionCreate) -> BreathingSession:
    entry = BreathingSession(patient_id=patient.id, **request.model_dump())
    db.add(entry)
    db.flush()
    add_audit_event(db, "BREATHING_SESSION_COMPLETED", user_id=user_id,
                    resource_type="breathing_session", resource_id=str(entry.id))
    db.commit()
    db.refresh(entry)
    return entry


def meditation_summary(db: Session, patient: Patient, day: date,
                       timezone_offset_minutes: int = 0) -> MeditationSummary:
    first = day - timedelta(days=6)
    offset = timedelta(minutes=timezone_offset_minutes)
    start = datetime.combine(first, time.min, timezone.utc) - offset
    end = datetime.combine(day + timedelta(days=1), time.min, timezone.utc) - offset
    entries = db.scalars(select(MeditationSession).where(
        MeditationSession.patient_id == patient.id,
        MeditationSession.started_at >= start,
        MeditationSession.started_at < end,
    )).all()
    totals = {first + timedelta(days=i): [0, 0] for i in range(7)}
    for entry in entries:
        local_day = (entry.started_at.astimezone(timezone.utc) + offset).date()
        totals[local_day][0] += 1
        totals[local_day][1] += entry.duration_seconds
    return MeditationSummary(history=[MeditationDay(
        date=current, count=totals[current][0], duration_seconds=totals[current][1],
    ) for current in totals])


def create_meditation_session(db: Session, patient: Patient, user_id: UUID,
                              request: MeditationSessionCreate) -> MeditationSession:
    entry = MeditationSession(patient_id=patient.id, **request.model_dump())
    db.add(entry)
    db.flush()
    add_audit_event(db, "MEDITATION_SESSION_COMPLETED", user_id=user_id,
                    resource_type="meditation_session", resource_id=str(entry.id))
    db.commit()
    db.refresh(entry)
    return entry
