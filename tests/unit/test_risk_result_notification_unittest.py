"""Opt-in and email content checks without a database or live delivery."""

import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from uuid import uuid4

from app.models.prediction import Prediction
from app.core.config import settings
from app.services.email_templates import elevated_risk_email
from app.services.risk_result_notification_service import (
    ResultEmailUnavailable, send_elevated_result_if_enabled, set_email_enabled,
)


def prediction(*, score: float, target: str = "diabetes_risk", classification: str = "elevated") -> Prediction:
    return Prediction(
        id=uuid4(), patient_id=uuid4(), model_id=uuid4(),
        prediction_target=target, risk_score=score,
        risk_classification=classification,
        predicted_at=datetime.now(timezone.utc),
        input_data={"model_version": "1", "contributing_factors": [
            {"feature": "bmi", "direction": "raises", "relative_magnitude": .7},
            {"feature": "age", "direction": "lowers", "relative_magnitude": .3},
        ]},
    )


class ElevatedRiskEmailTests(unittest.TestCase):
    def test_cannot_enable_email_when_delivery_is_unconfigured(self):
        db = Mock()
        with patch.object(settings, "BREVO_API_KEY", ""):
            with self.assertRaises(ResultEmailUnavailable):
                set_email_enabled(db, uuid4(), uuid4(), True)
        db.execute.assert_not_called()

    def test_email_template_shows_score_factors_and_change(self):
        body = elevated_risk_email(
            model_name="Diabetes", score=.726,
            factors=[("BMI", "raises"), ("Age", "lowers")], previous_score=.681,
        )
        self.assertIn("72.6%", body)
        self.assertIn("68.1%", body)
        self.assertIn("4.5 percentage points higher", body)
        self.assertIn("BMI: raises the model estimate", body)
        self.assertIn("font-size:36px", body.html)
        self.assertIn("Contributing factors", body.html)
        self.assertIn("not a diagnosis", body.html)

    def test_without_previous_result_says_comparison_is_unavailable(self):
        body = elevated_risk_email(
            model_name="Heart Disease", score=.81, factors=[], previous_score=None,
        )
        self.assertIn("No previous Heart Disease score", body)

    def test_no_email_without_opt_in_or_elevated_classification(self):
        db = Mock()
        with (patch("app.services.risk_result_notification_service.email_enabled", return_value=False),
              patch("app.services.risk_result_notification_service.send_transactional_email") as send):
            send_elevated_result_if_enabled(db, prediction(score=.8, classification="standard"))
            send_elevated_result_if_enabled(db, prediction(score=.8))
        send.assert_not_called()

    def test_opted_in_elevated_result_sends_same_target_comparison(self):
        db = Mock()
        current = prediction(score=.726)
        previous = prediction(score=.681)
        patient = Mock()
        patient.user.id = uuid4()
        patient.user.email = "person@example.test"
        patient.user.is_active = True
        db.get.return_value = patient
        db.scalar.return_value = previous
        with (patch("app.services.risk_result_notification_service.email_enabled", return_value=True),
              patch("app.services.risk_result_notification_service.send_transactional_email") as send):
            send_elevated_result_if_enabled(db, current)
        body = send.call_args.args[2]
        self.assertIn("72.6%", body)
        self.assertIn("4.5 percentage points higher", body)
        self.assertIn("BMI", body)
        self.assertEqual(send.call_args.args[0], "person@example.test")
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
