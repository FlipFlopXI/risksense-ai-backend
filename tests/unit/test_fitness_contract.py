from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.services.fitness_service import activity_summary, body_summary


class _Results:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _ActivitySession:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self, statement):
        return _Results(self.rows)


class _BodySession:
    def __init__(self, profile):
        self.profile = profile
        self.calls = 0

    def scalar(self, statement):
        self.calls += 1
        return self.profile if self.calls == 1 else None


def test_activity_history_is_seven_days_and_uses_only_logged_values():
    today = date.today()
    rows = [SimpleNamespace(log_date=today, steps=1200, activity_minutes=20,
                            activity_calories_kcal=85, distance_km=1.3),
            SimpleNamespace(log_date=today, steps=300, activity_minutes=5,
                            activity_calories_kcal=15, distance_km=.2)]
    result = activity_summary(_ActivitySession(rows), SimpleNamespace(id=uuid4()), today)
    assert len(result.history) == 7
    assert result.history[0].date == today - timedelta(days=6)
    assert result.today.steps == 1500
    assert result.today.activity_minutes == 25
    assert result.today.activity_calories_kcal == 100
    assert result.today.distance_km == 1.5
    assert all(day.steps == 0 for day in result.history[:-1])


def test_bmi_reference_requires_adult_and_excludes_pregnancy():
    profile = SimpleNamespace(height_cm=180, weight_kg=81, bmi=25,
                              pregnancy_status="PREGNANT")
    patient = SimpleNamespace(id=uuid4(), date_of_birth=date(1990, 1, 1))
    result = body_summary(_BodySession(profile), patient)
    assert result.adult_bmi_reference_applicable is False
    profile.pregnancy_status = "NOT_PREGNANT"
    result = body_summary(_BodySession(profile), patient)
    assert result.adult_bmi_reference_applicable is True
    patient.date_of_birth = date.today().replace(year=date.today().year - 15)
    result = body_summary(_BodySession(profile), patient)
    assert result.adult_bmi_reference_applicable is False
