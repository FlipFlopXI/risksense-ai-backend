import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from pydantic import ValidationError

from app.schemas.fitness import BodyCompositionCreate, BodyCompositionResponse, WeightUpdate
from app.schemas.health import HealthProfileCreateRequest, HealthProfileUpdateRequest
from app.schemas.nutrition import MetabolicLogCreate, MetabolicLogResponse


class PatientInputValidationTests(unittest.TestCase):
    def test_meter_and_insulin_limits(self):
        for category, value in (("fasting", "20"), ("general", "600"),
                                ("insulin_dose", "0.5"), ("insulin_dose", "500")):
            self.assertEqual(MetabolicLogCreate(log_date=date.today(),
                category=category, value=value).category, category)
        for category, value in (("fasting", "19.99"), ("post_meal", "600.01"),
                                ("insulin_dose", "500.01")):
            with self.assertRaises(ValidationError):
                MetabolicLogCreate(log_date=date.today(), category=category, value=value)

    def test_legacy_metabolic_response_can_still_be_read(self):
        row = MetabolicLogResponse(id=uuid4(), log_date=date.today(),
            category="general", value=Decimal("700"), unit="mg/dL",
            created_at=datetime.now(timezone.utc))
        self.assertEqual(row.value, Decimal("700"))

    def test_weight_and_body_composition_write_bounds(self):
        self.assertEqual(WeightUpdate(weight_kg=25).weight_kg, 25)
        for value in (2, 24.99, 350.01):
            with self.assertRaises(ValidationError):
                WeightUpdate(weight_kg=value)
        for schema in (HealthProfileCreateRequest, HealthProfileUpdateRequest):
            for value in (2, 24.99, 351):
                with self.assertRaises(ValidationError):
                    schema(weight_kg=value)
        self.assertEqual(BodyCompositionCreate(skeletal_muscle_kg=30,
            body_fat_percent=25).body_fat_percent, 25)
        for value in (0, 81):
            with self.assertRaises(ValidationError):
                BodyCompositionCreate(skeletal_muscle_kg=30, body_fat_percent=value)
        legacy = BodyCompositionResponse(id=uuid4(), created_at=datetime.now(timezone.utc),
            skeletal_muscle_kg=30, body_fat_percent=90)
        self.assertEqual(legacy.body_fat_percent, 90)


if __name__ == "__main__":
    unittest.main()
