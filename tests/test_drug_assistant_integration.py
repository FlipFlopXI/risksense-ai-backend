from datetime import datetime, timedelta, timezone
from uuid import UUID
from unittest.mock import Mock
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from app.models.drug_chat import DrugChatSession, DrugChatMessage
from app.models.audit import AuditLog
from app.models.health_profile import HealthProfile
from app.models.patient_clinician import PatientClinician, PatientClinicianStatus
from app.models.clinician import ClinicianApprovalStatus
from app.models.access_entitlement import EntitlementStatus
from app.models.patient_medication import PatientMedication
from app.services import drug_assistant_service as service
from app.services.drug_assistant_service import voluntary_context
from test_heart_disease_integration import scenario
from test_security_integration import _auth, _token, _patient

CHAT = "/drug-assistant/chat"
SESSIONS = "/drug-assistant/sessions"


def ask(client, scenario, message="What is metformin?", **kwargs):
    return client.post(CHAT, headers=scenario["headers"], json={"message": message, **kwargs})


def test_conversation_persistence_provenance_and_history(client, db, scenario):
    response = ask(client, scenario)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["drug"]["drug_id"] == "metformin"
    assert body["evidence_status"] == "INSUFFICIENT_EVIDENCE" and body["sources"] == []
    assert db.get(DrugChatSession, UUID(body["session_id"]))
    messages = list(db.scalars(select(DrugChatMessage).order_by(DrugChatMessage.sequence)))
    assert [row.role for row in messages] == ["user", "assistant"]
    assert messages[1].resolved_drug_ids == ["metformin"]
    assert messages[1].intent == "DRUG_GENERAL"
    assert messages[1].evidence_status == "INSUFFICIENT_EVIDENCE"
    assert "artifact_hashes" in messages[1].source_provenance[-1]
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "DRUG_CHAT_MESSAGE_CREATED"))
    assert audit.resource_id == body["message_id"]
    assert "message" not in audit.details and "metformin" not in str(audit.details)
    history = client.get(SESSIONS + "/" + body["session_id"] + "/messages", headers=scenario["headers"])
    assert history.status_code == 200 and len(history.json()) == 2
    assert history.json()[1]["response"]["message_id"] == body["message_id"]
    assert client.get(SESSIONS, headers=scenario["headers"]).json()[0]["id"] == body["session_id"]


def test_session_context_explicit_and_isolated(client, db, scenario):
    result = ask(client, scenario, "I'm 8 weeks pregnant and taking metformin.").json()
    assert result["patient_context_used"]["pregnancy_status"]["value"] == "PREGNANT"
    assert result["patient_context_used"]["gestational_context"]["reported_weeks"] == 8
    followup = ask(client, scenario, "What human evidence is known about this?", session_id=result["session_id"]).json()
    assert followup["drug"]["drug_id"] == "metformin"
    assert followup["patient_context_used"]["pregnancy_status"]["value"] == "PREGNANT"
    separate = ask(client, scenario, "Can I take metformin while pregnant?").json()
    assert separate["patient_context_used"] == {}
    # Chat never silently writes pregnancy data into the health profile.
    profile = db.scalar(select(HealthProfile).where(HealthProfile.patient_id == scenario["patient"].id))
    assert profile is None or profile.pregnancy_status is None
    assert voluntary_context("If I am pregnant", {}) == {}


def test_unknown_does_not_reuse_prior_drug_and_close(client, scenario):
    initial = ask(client, scenario).json()
    unknown = ask(client, scenario, "What is xyzmed?", session_id=initial["session_id"])
    assert unknown.json()["evidence_status"] == "UNSUPPORTED_DRUG"
    ambiguous = ask(client, scenario, "What about this medicine?", session_id=initial["session_id"])
    assert ambiguous.json()["intent"] == "AMBIGUOUS_DRUG"
    closed = client.patch(SESSIONS + "/" + initial["session_id"], headers=scenario["headers"], json={"status": "CLOSED"})
    assert closed.status_code == 200 and closed.json()["closed_at"]
    assert ask(client, scenario, session_id=initial["session_id"]).status_code == 409


def test_urgent_persisted_and_audited(client, db, scenario):
    result = ask(client, scenario, "I took 40 tablets and I feel sick.")
    assert result.status_code == 201 and result.json()["urgent"]
    row = db.get(DrugChatMessage, UUID(result.json()["message_id"]))
    assert row.safety_classification == "suspected_overdose"
    assert row.patient_context == {}
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "DRUG_CHAT_URGENT_ROUTE", AuditLog.resource_id == str(row.id)))


def test_cross_patient_and_admin_denied(client, db, scenario):
    initial = ask(client, scenario).json()
    other_user, other = _patient(db, "other.drug@example.test")
    db.commit()
    # A different patient's entitlement cannot be supplied or inferred from a session.
    assert ask(client, scenario, patient_id=str(other.id)).status_code == 404
    other_headers = _auth(_token(other_user))
    assert client.get(SESSIONS + "/" + initial["session_id"], headers=other_headers).status_code in (403, 404)
    assert client.post(CHAT, headers=_auth(_token(scenario["admin"])), json={"message": "What is metformin?"}).status_code == 403
    assert client.post(CHAT, json={"message": "What is metformin?"}).status_code == 401


def test_clinician_approval_and_active_link(client, db, scenario):
    headers = _auth(_token(scenario["clinician_user"]))
    payload = {"message": "What is metformin?", "patient_id": str(scenario["patient"].id)}
    assert client.post(CHAT, headers=headers, json=payload).status_code == 201
    assert client.post(CHAT, headers=headers, json={"message": "What is metformin?"}).status_code == 422
    link = db.scalar(select(PatientClinician).where(PatientClinician.patient_id == scenario["patient"].id))
    link.status = PatientClinicianStatus.INACTIVE
    db.commit()
    assert client.post(CHAT, headers=headers, json=payload).status_code == 404
    link.status = PatientClinicianStatus.ACTIVE
    scenario["clinician"].approval_status = ClinicianApprovalStatus.PENDING
    db.commit()
    assert client.post(CHAT, headers=headers, json=payload).status_code == 403


@pytest.mark.parametrize("expired", [True, False])
def test_entitlement_revoked_between_turns(client, db, scenario, expired):
    initial = ask(client, scenario).json()
    if expired:
        scenario["entitlement"].verified_at = datetime.now(timezone.utc) - timedelta(days=2)
        scenario["entitlement"].expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    else:
        scenario["entitlement"].status = EntitlementStatus.CANCELLED
    db.commit()
    assert ask(client, scenario, session_id=initial["session_id"]).status_code == 403
    assert client.get(SESSIONS + "/" + initial["session_id"], headers=scenario["headers"]).status_code == 403


def test_audit_failure_rolls_back_session_and_messages(client, db, scenario, monkeypatch):
    real_audit = service.add_audit_event
    def fail_message(db, action, **kwargs):
        if action == "DRUG_CHAT_MESSAGE_CREATED":
            raise SQLAlchemyError("private SQL credentials")
        return real_audit(db, action, **kwargs)
    monkeypatch.setattr(service, "add_audit_event", fail_message)
    result = ask(client, scenario)
    assert result.status_code == 503 and "private" not in result.text
    assert db.scalar(select(func.count(DrugChatSession.id))) == 0
    assert db.scalar(select(func.count(DrugChatMessage.id))) == 0
    assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "DRUG_CHAT_SESSION_CREATED")) == 0


def test_pregnancy_profile_update_and_legacy_medications_preserved(client, db, scenario):
    created = client.post("/health/profile", headers=scenario["headers"], json={"height_cm": 178, "weight_kg": 80, "current_medications": "legacy free text"})
    assert created.status_code == 201
    updated = client.put("/health/profile", headers=scenario["headers"], json={"pregnancy_status": "PREGNANT", "estimated_due_date": (datetime.now(timezone.utc).date() + timedelta(days=100)).isoformat()})
    assert updated.status_code == 200
    assert updated.json()["current_medications"] == "legacy free text" and updated.json()["bmi"] == 25.25
    assert updated.json()["pregnancy_context_updated_at"]
    # Merge validation rejects stale due date if status alone is changed.
    assert client.put("/health/profile", headers=scenario["headers"], json={"pregnancy_status": "NOT_PREGNANT"}).status_code == 422
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "PREGNANCY_CONTEXT_UPDATED"))


def test_medication_crud_ownership_and_linked_read(client, db, scenario):
    created = client.post("/patient-medications", headers=scenario["headers"], json={"display_name": "paracetamol", "dose": "as entered"})
    assert created.status_code == 201
    body = created.json()
    assert body["drug_id"] == "acetaminophen"
    endpoint = "/patient-medications/" + body["id"]
    assert client.patch(endpoint, headers=scenario["headers"], json={"frequency": "patient report"}).status_code == 200
    linked = _auth(_token(scenario["clinician_user"]))
    assert client.get(endpoint, headers=linked, params={"patient_id": str(scenario["patient"].id)}).status_code == 200
    assert client.patch(endpoint, headers=linked, json={"dose": "changed"}).status_code == 403
    other_user, _ = _patient(db, "other.medication@example.test")
    db.commit()
    assert client.get(endpoint, headers=_auth(_token(other_user))).status_code == 404
    assert client.delete(endpoint, headers=scenario["headers"]).json()["is_active"] is False
    assert db.get(PatientMedication, UUID(body["id"])) is not None
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "PATIENT_MEDICATION_DEACTIVATED"))


def test_catalogue_and_versioned_aliases(client, scenario):
    response = client.get("/api/v1/drug-assistant/drugs", headers=scenario["headers"], params={"limit": 208})
    assert response.status_code == 200 and len(response.json()) == 208
    source = client.get("/drug-assistant/drugs/metformin/sources", headers=scenario["headers"]).json()
    assert source["reviewed_sources"] == [] and source["retrieval_mappings"]
    assert client.get("/drug-assistant/drugs/unknown", headers=scenario["headers"]).status_code == 404
    response = client.post("/api/v1/drug-assistant/chat", headers=scenario["headers"], json={"message": "What is metformin?"})
    assert response.status_code == 201
