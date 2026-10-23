from datetime import datetime, timezone
from unittest.mock import Mock
from app.services.drug_assistant_service import voluntary_context, relevant_context


def test_explicit_vs_hypothetical_pregnancy_and_clear_timing():
    assert voluntary_context("Can I use metformin if I'm pregnant?", {}) == {}
    explicit = voluntary_context("I just found out I'm pregnant and take metformin", {})
    assert explicit["pregnancy_status"]["value"] == "PREGNANT"
    timed = voluntary_context("I'm 8 weeks pregnant", {})
    assert timed["gestational_context"]["reported_weeks"] == 8
    cleared = voluntary_context("I'm not pregnant", timed)
    assert cleared["pregnancy_status"]["value"] == "NOT_PREGNANT" and "gestational_context" not in cleared


def test_nonclinical_intent_reads_no_health_data():
    db = Mock()
    assert relevant_context(db, Mock(), "DRUG_GENERAL", {}) == {}
    db.scalar.assert_not_called()


def test_context_does_not_infer_pregnancy_from_demographics():
    db = Mock()
    db.scalar.return_value = None
    patient = Mock(gender="female", date_of_birth=datetime(1990, 1, 1).date())
    assert relevant_context(db, patient, "DRUG_PREGNANCY", {}) == {}
    retrospective = voluntary_context("I took metformin before I knew I was pregnant.", {})
    assert "pregnancy_status" not in retrospective
    assert retrospective["exposure_timing"]["source"] == "session_patient_report"


def test_lactation_filters_irrelevant_pregnancy_and_infant_data():
    db = Mock()
    db.scalar.return_value = Mock(breastfeeding_status="NO", infant_date_of_birth=datetime(2025, 1, 1).date(),
                                  infant_premature=True, pregnancy_context_updated_at=datetime.now(timezone.utc))
    result = relevant_context(db, Mock(), "DRUG_LACTATION", {"pregnancy_status": {"value": "PREGNANT"}})
    assert set(result) == {"breastfeeding_status"}
