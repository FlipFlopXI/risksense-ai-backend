from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.nutrition import MetabolicLogEntry
from app.schemas.nutrition import MetabolicLogCreate
from app.services.nutrition_service import create_metabolic_entry, metabolic_summary


class _Results:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Session:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.added = []
        self.deleted = []

    def scalars(self, query):
        return _Results(self.rows)

    def scalar(self, query):
        return self.rows[0] if self.rows else None

    def add(self, item):
        self.added.append(item)

    def flush(self):
        pass

    def commit(self):
        pass

    def refresh(self, item):
        pass

    def delete(self, item):
        self.deleted.append(item)


def test_metabolic_categories_and_values_are_bounded():
    for category in ("fasting", "post_meal", "general", "insulin_dose"):
        assert MetabolicLogCreate(log_date=date.today(), category=category,
                                  value="8.5" if category == "insulin_dose" else "85").category == category
    for category, value in (("unknown", "100"), ("fasting", "0"),
                            ("fasting", "19.99"), ("post_meal", "600.01"),
                            ("insulin_dose", "500.01"), ("insulin_dose", "1001"),
                            ("general", "1.234")):
        with pytest.raises(ValidationError):
            MetabolicLogCreate(log_date=date.today(), category=category, value=value)


def test_glucose_and_insulin_units_cannot_be_interchanged():
    patient = SimpleNamespace(id=uuid4())
    user_id = uuid4()
    for category, unit in (("fasting", "mg/dL"), ("post_meal", "mg/dL"),
                           ("general", "mg/dL"), ("insulin_dose", "U")):
        db = _Session()
        entry = create_metabolic_entry(db, patient, user_id,
            MetabolicLogCreate(log_date=date.today(), category=category,
                               value=Decimal("8.50" if category == "insulin_dose" else "85.00")))
        assert isinstance(entry, MetabolicLogEntry)
        assert entry.unit == unit
        assert any(getattr(item, "action", None) == "METABOLIC_LOG_CREATED"
                   for item in db.added)


def test_summary_returns_only_query_results_and_empty_history():
    patient = SimpleNamespace(id=uuid4())
    today = date.today()
    row = MetabolicLogEntry(id=uuid4(), patient_id=patient.id,
        log_date=today - timedelta(days=2), category="general",
        value=Decimal("123.00"), unit="mg/dL",
        created_at=datetime.now(timezone.utc))
    result = metabolic_summary(_Session([row]), patient, today)
    assert result.entries[0].value == Decimal("123.00")
    assert metabolic_summary(_Session(), patient, today).entries == []
