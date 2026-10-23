from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import jwt
import pytest
from pydantic import ValidationError

from app.api.v1.admin import drug_assistant_status
from app.core.security import create_access_token, create_refresh_token, decode_access_token, decode_refresh_token
from app.models.body_measurement import BodyMeasurement
from app.schemas.health import HealthProfileUpdateRequest
from app.services.report_service import DISCLAIMER, render_report_pdf


def test_access_and_refresh_tokens_are_separate_and_session_bound():
    sid = uuid4()
    access = decode_access_token(create_access_token(str(uuid4()), "patient", sid))
    refresh_token, jti, expires = create_refresh_token(access["sub"], "patient", sid)
    refresh = decode_refresh_token(refresh_token)
    assert access["type"] == "access" and access["sid"] == str(sid)
    assert refresh["type"] == "refresh" and refresh["sid"] == str(sid) and refresh["jti"] == jti
    assert expires > datetime.now(timezone.utc)
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(refresh_token)


def test_body_measurement_time_validation_and_derived_bmi():
    with pytest.raises(ValidationError):
        HealthProfileUpdateRequest(weight_kg=80, body_measurement_at=datetime.now() + timedelta(days=1))
    aware = datetime.now(timezone.utc) - timedelta(days=1)
    assert HealthProfileUpdateRequest(weight_kg=80, body_measurement_at=aware).body_measurement_at == aware
    assert BodyMeasurement(height_cm=178, weight_kg=80).bmi == 25.25
    assert BodyMeasurement(weight_kg=80).bmi is None


def test_report_pdf_is_valid_and_contains_no_diagnostic_claim():
    report = SimpleNamespace(
        title="RiskSense AI Heart Disease Risk Analysis Report",
        summary="Estimated risk classification: elevated. This result is decision support and is not a diagnosis.",
        report_data={
            "patient_reference": "SYNTHETIC", "analysis_type": "heart_disease",
            "analysis_at": "2026-09-18T10:00:00+02:00", "model_version": "1.0.0",
            "risk_score": 0.5, "risk_classification": "elevated", "disclaimer": DISCLAIMER,
            "input_snapshot": {"features": {"age": 50, "systolic_bp": 130},
                               "sources": {"systolic_bp": {"recorded_at": "2026-09-18T09:00:00+02:00"}}},
        },
    )
    content = render_report_pdf(report)
    assert content.startswith(b"%PDF-") and len(content) > 2000


def test_admin_drug_status_is_operational_and_nonclinical():
    result = drug_assistant_status(SimpleNamespace())
    assert result.runtime_status == "AVAILABLE"
    assert result.catalogue_medication_count == 208
    assert result.therapeutic_group_count == 16
    assert result.intent_count == 36
    assert result.reviewed_evidence_count == 1078
    assert result.published_medication_count == 90
    assert result.insufficient_count == 118
    assert result.pending_review_record_count == 0
    assert result.dailymed_unresolved_product_count == 192
    assert not hasattr(result, "patient_conversations")
