from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.mindfulness import BreathingSession, MeditationSession, MoodEntry
from app.schemas.mindfulness import BreathingSessionCreate, MeditationSessionCreate, MoodCreate
from app.services.mindfulness_service import (breathing_summary, create_breathing_session,
                                               create_meditation_session, create_mood,
                                               meditation_summary, mood_summary)


class _Results:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Session:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.added = []

    def scalars(self, statement):
        return _Results(self.rows)

    def add(self, item):
        self.added.append(item)

    def flush(self):
        pass

    def commit(self):
        pass

    def refresh(self, item):
        pass


def test_mood_input_validates_category_and_descriptions():
    result = MoodCreate(log_date=date.today(), mood="good",
                        emotion=" Calm ", reason=" Sleep ")
    assert (result.emotion, result.reason) == ("Calm", "Sleep")
    for mood, emotion, reason in (("unknown", "Calm", "Sleep"),
                                  ("good", " ", "Sleep"),
                                  ("good", "Calm", " ")):
        with pytest.raises(ValidationError):
            MoodCreate(log_date=date.today(), mood=mood,
                       emotion=emotion, reason=reason)


def test_seven_day_average_preserves_unlogged_days():
    patient = SimpleNamespace(id=uuid4())
    today = date.today()
    rows = [MoodEntry(id=uuid4(), patient_id=patient.id, log_date=today,
                      mood=mood, emotion="Calm", reason="Rest",
                      created_at=datetime.now(timezone.utc))
            for mood in ("good", "fine")]
    result = mood_summary(_Session(rows), patient, today)
    assert len(result.history) == 7
    assert result.history[0].date == today - timedelta(days=6)
    assert result.history[0].average_mood is None
    assert result.history[-1].average_score == 3.5
    assert result.history[-1].average_mood == "good"
    assert len(result.today_entries) == 2


def test_create_mood_audits_without_raw_emotion_or_reason():
    db = _Session()
    patient = SimpleNamespace(id=uuid4())
    entry = create_mood(db, patient, uuid4(),
        MoodCreate(log_date=date.today(), mood="fine",
                   emotion="Private feeling", reason="Private reason"))
    assert entry.mood == "fine"
    audit = [item for item in db.added if getattr(item, "action", None) == "MOOD_LOG_CREATED"]
    assert len(audit) == 1
    assert audit[0].details is None
    assert audit[0].error_message is None


def test_breathing_session_summary_and_audit():
    db = _Session()
    patient = SimpleNamespace(id=uuid4())
    start = datetime.now(timezone.utc).replace(microsecond=0)
    request = BreathingSessionCreate(exercise="box", duration_seconds=90, started_at=start)
    entry = create_breathing_session(db, patient, uuid4(), request)
    assert isinstance(entry, BreathingSession)
    assert entry.patient_id == patient.id
    assert entry.duration_seconds == 90
    assert any(getattr(item, "action", None) == "BREATHING_SESSION_COMPLETED"
               for item in db.added)
    db.rows = [entry]
    result = breathing_summary(db, patient, start.date())
    assert len(result.history) == 7
    assert result.history[-1].count == 1
    assert result.history[-1].duration_seconds == 90


def test_breathing_session_rejects_invalid_duration_and_naive_timestamp():
    for seconds, stamp in ((0, datetime.now(timezone.utc)),
                           (3601, datetime.now(timezone.utc)),
                           (60, datetime.now())):
        with pytest.raises(ValidationError):
            BreathingSessionCreate(exercise="box", duration_seconds=seconds,
                                   started_at=stamp)


def test_breathing_summary_uses_patient_local_day():
    patient = SimpleNamespace(id=uuid4())
    entry = BreathingSession(patient_id=patient.id, exercise="belly",
                             duration_seconds=120,
                             started_at=datetime(2026, 10, 24, 23, 30,
                                                 tzinfo=timezone.utc))
    result = breathing_summary(_Session([entry]), patient, date(2026, 10, 25), 120)
    assert result.history[-1].count == 1
    assert result.history[-1].duration_seconds == 120


def test_meditation_session_summary_and_audit():
    db = _Session()
    patient = SimpleNamespace(id=uuid4())
    start = datetime(2026, 10, 24, 23, 30, tzinfo=timezone.utc)
    request = MeditationSessionCreate(category="nature", track_id="nature_02",
        duration_seconds=125, started_at=start)
    entry = create_meditation_session(db, patient, uuid4(), request)
    assert isinstance(entry, MeditationSession)
    assert entry.patient_id == patient.id
    assert any(getattr(item, "action", None) == "MEDITATION_SESSION_COMPLETED"
               for item in db.added)
    db.rows = [entry]
    result = meditation_summary(db, patient, date(2026, 10, 25), 120)
    assert len(result.history) == 7
    assert result.history[-1].count == 1
    assert result.history[-1].duration_seconds == 125


def test_meditation_session_rejects_invalid_track_duration_and_timestamp():
    for category, track, seconds, stamp in (
        ("nature", "sleep_01", 60, datetime.now(timezone.utc)),
        ("nature", "nature_07", 60, datetime.now(timezone.utc)),
        ("nature", "nature_02", 0, datetime.now(timezone.utc)),
        ("nature", "nature_02", 60, datetime.now()),
    ):
        with pytest.raises(ValidationError):
            MeditationSessionCreate(category=category, track_id=track,
                                    duration_seconds=seconds, started_at=stamp)
