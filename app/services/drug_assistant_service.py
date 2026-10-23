from datetime import datetime, timezone
import re
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.ml.drug_assistant.runtime import load_runtime, normalize
from app.ml.drug_assistant.intent import classify
from app.ml.drug_assistant.composer import compose
from app.models.drug_chat import DrugChatSession, DrugChatMessage
from app.models.health_profile import HealthProfile
from app.models.patient import Patient
from app.models.patient_medication import PatientMedication
from app.models.user import User, UserRole
from app.schemas.drug_assistant import ChatRequest, ChatResponse, SessionCreate
from app.services.audit_service import add_audit_event, record_auth_event_best_effort
from app.services.clinical_access_service import authorize_patient


def new_session(db: Session, user: User, patient: Patient, title: str | None = None) -> DrugChatSession:
    session = DrugChatSession(id=uuid4(), patient_id=patient.id, initiated_by_user_id=user.id,
                              title=title, status="OPEN", state={}, next_sequence=0)
    db.add(session)
    db.flush()
    add_audit_event(db, "DRUG_CHAT_SESSION_CREATED", user_id=user.id, resource_type="drug_chat_session", resource_id=str(session.id))
    return session


def create_session(db: Session, user: User, request: SessionCreate) -> DrugChatSession:
    patient = authorize_patient(db, user, request.patient_id, chat=True)
    load_runtime()
    session = new_session(db, user, patient, request.title)
    db.commit()
    db.refresh(session)
    return session


def session_for(db: Session, user: User, session_id: UUID, patient_id: UUID | None, *, lock: bool = False) -> tuple[DrugChatSession, Patient]:
    patient = authorize_patient(db, user, patient_id, chat=True)
    query = select(DrugChatSession).where(DrugChatSession.id == session_id, DrugChatSession.patient_id == patient.id)
    if lock:
        query = query.with_for_update()
    session = db.scalar(query)
    if session is None:
        record_auth_event_best_effort(db, "DRUG_CHAT_ACCESS_DENIED", user.id, "failure")
        raise HTTPException(404, detail={"code": "SESSION_NOT_FOUND", "message": "Session not found."})
    return session, patient


def list_sessions(db: Session, user: User, patient_id: UUID | None, limit: int, offset: int):
    patient = authorize_patient(db, user, patient_id, chat=True)
    return list(db.scalars(select(DrugChatSession).where(DrugChatSession.patient_id == patient.id)
                          .order_by(DrugChatSession.updated_at.desc(), DrugChatSession.id).offset(offset).limit(limit)))


def list_messages(db: Session, user: User, session_id: UUID, patient_id: UUID | None, limit: int, after_sequence: int):
    session_for(db, user, session_id, patient_id)
    return list(db.scalars(select(DrugChatMessage).where(DrugChatMessage.session_id == session_id,
                           DrugChatMessage.sequence > after_sequence).order_by(DrugChatMessage.sequence).limit(limit)))


def close_session(db: Session, user: User, session_id: UUID, patient_id: UUID | None):
    session, _ = session_for(db, user, session_id, patient_id, lock=True)
    if session.status != "CLOSED":
        session.status, session.closed_at = "CLOSED", datetime.now(timezone.utc)
        add_audit_event(db, "DRUG_CHAT_SESSION_CLOSED", user_id=user.id, resource_type="drug_chat_session", resource_id=str(session.id))
        db.commit()
        db.refresh(session)
    return session


def voluntary_context(message: str, prior: dict) -> dict:
    """Only explicit first-person reports; never infer from a hypothetical question."""
    value = normalize(message)
    context = dict(prior)
    now = datetime.now(timezone.utc).isoformat()
    if not re.search(r"\b(if|suppose|hypothetical)\b", value):
        if re.search(r"\bi (?:am|m) not pregnant\b", value):
            context.pop("gestational_context", None)
            context["pregnancy_status"] = {"value": "NOT_PREGNANT", "source": "session_patient_report", "reported_at": now}
        elif re.search(r"\bi (?:am|m|just found out i (?:am|m)) (?:\d{1,2} weeks? )?pregnant\b", value):
            context["pregnancy_status"] = {"value": "PREGNANT", "source": "session_patient_report", "reported_at": now}
            weeks = re.search(r"\bi (?:am|m) (\d{1,2}) weeks? pregnant\b", value)
            if weeks and 0 < int(weeks[1]) <= 45:
                context["gestational_context"] = {"reported_weeks": int(weeks[1]), "reported_at": now, "source": "session_patient_report"}
        elif re.search(r"\bi (?:am|m) trying to conceive\b", value):
            context.pop("gestational_context", None)
            context["pregnancy_status"] = {"value": "TRYING_TO_CONCEIVE", "source": "session_patient_report", "reported_at": now}
        if re.search(r"\bi took .+ before i knew i was pregnant\b", value):
            context["exposure_timing"] = {"value": "reported exposure before pregnancy recognition", "source": "session_patient_report", "reported_at": now}
        if re.search(r"\bi (?:am|m) (?:not )?breastfeeding\b", value):
            context["breastfeeding_status"] = {"value": "NO" if "not breastfeeding" in value else "YES", "source": "session_patient_report", "reported_at": now}
    return context


def relevant_context(db: Session, patient: Patient, intent: str, reported: dict) -> dict:
    pregnancy = intent.startswith("DRUG_PREGNANCY") or intent in {"DRUG_REPRODUCTIVE_POTENTIAL", "DRUG_FERTILITY", "DRUG_CONTRACEPTION"}
    lactation = intent == "DRUG_LACTATION"
    conditions = intent in {"DRUG_HEART_CONTEXT", "DRUG_DIABETES_CONTEXT", "DRUG_PATIENT_CONTEXT"}
    medications = intent in {"DRUG_INTERACTION", "DRUG_PATIENT_CONTEXT"}
    if not any((pregnancy, lactation, conditions, medications)):
        return {}
    profile = db.scalar(select(HealthProfile).where(HealthProfile.patient_id == patient.id))
    used = {}
    fields = (["pregnancy_status", "estimated_due_date"] if pregnancy else []) + (["breastfeeding_status", "infant_date_of_birth", "infant_premature"] if lactation else [])
    for field in fields:
        stored = getattr(profile, field, None)
        if stored is not None:
            used[field] = {"value": stored.isoformat() if hasattr(stored, "isoformat") else stored, "source": "health_profile", "updated_at": profile.pregnancy_context_updated_at.isoformat() if profile.pregnancy_context_updated_at else None}
        if field in reported:
            used[field] = reported[field]
    if pregnancy and "gestational_context" in reported:
        used["gestational_context"] = reported["gestational_context"]
    if pregnancy and "exposure_timing" in reported:
        used["exposure_timing"] = reported["exposure_timing"]
    # A newly reported non-pregnant/unknown state must not carry stale timing.
    if used.get("pregnancy_status", {}).get("value") != "PREGNANT":
        used.pop("gestational_context", None)
        used.pop("estimated_due_date", None)
    if lactation and used.get("breastfeeding_status", {}).get("value") in {"NO", "PREFER_NOT_TO_SAY"}:
        used.pop("infant_date_of_birth", None)
        used.pop("infant_premature", None)
    if conditions and profile and profile.existing_conditions:
        used["conditions"] = {"value": profile.existing_conditions, "source": "health_profile_patient_report"}
    if medications:
        records = db.scalars(select(PatientMedication).where(PatientMedication.patient_id == patient.id, PatientMedication.is_active.is_(True))).all()
        used["medications"] = [{"id": str(row.id), "drug_id": row.drug_id, "display_name": row.display_name} for row in records]
        if profile and profile.current_medications:
            used["legacy_medications"] = {"value": profile.current_medications, "source": "health_profile_unstructured_patient_report"}
    return used


def chat(db: Session, user: User, request: ChatRequest) -> ChatResponse:
    if request.session_id:
        session, patient = session_for(db, user, request.session_id, request.patient_id, lock=True)
        if session.status != "OPEN":
            raise HTTPException(409, detail={"code": "SESSION_CLOSED", "message": "Create a new session to continue."})
    else:
        patient = authorize_patient(db, user, request.patient_id, chat=True)
        session = None
    runtime = load_runtime()
    if session is None:
        session = new_session(db, user, patient)
    intent = classify(request.message)
    state = dict(session.state)
    pending_urgent = state.get("urgent_pending")
    # This is a report of seeking help, never a medical assessment of recovery.
    if re.search(r"\bi (?:am|m) (?:now )?(?:with (?:a |my )?(?:doctor|paramedic)|in (?:the )?(?:hospital|emergency department))\b|\bi have contacted (?:emergency services|poison control)\b", normalize(request.message)):
        pending_urgent = None
    reported = state.get("reported_context", {})
    if user.role == UserRole.PATIENT and not intent.urgent_category and not pending_urgent:
        reported = voluntary_context(request.message, reported)
    context = {} if intent.urgent_category or pending_urgent else relevant_context(db, patient, intent.name, reported)
    payload = compose(request.message, runtime, tuple(state.get("drug_ids", [])), context, pending_urgent=pending_urgent)
    response_id = uuid4()
    payload.update(session_id=str(session.id), message_id=str(response_id))
    response = ChatResponse.model_validate(payload)
    drugs = [item["drug_id"] for item in payload["drugs"]]
    session.state = {"drug_ids": drugs if drugs else ([] if payload["resolution_status"] in {"UNSUPPORTED_DRUG", "AMBIGUOUS_DRUG"} else state.get("drug_ids", [])),
                     "intent": payload["intent"], "reported_context": reported, "urgent_pending": payload["urgent_category"]}
    first = session.next_sequence + 1
    common = dict(session_id=session.id, actor_user_id=user.id, intent=payload["intent"], resolved_drug_ids=drugs,
                  evidence_status=payload["evidence_status"], patient_context=context,
                  source_provenance=[*payload["sources"], {"artifact_hashes": dict(runtime.hashes)}], safety_classification=payload["urgent_category"])
    db.add_all([DrugChatMessage(id=uuid4(), sequence=first, role="user", content=request.message, **common),
                DrugChatMessage(id=response_id, sequence=first + 1, role="assistant", response=response.model_dump(mode="json"), **common)])
    session.next_sequence += 2
    session.updated_at = datetime.now(timezone.utc)
    for event in ("DRUG_CHAT_MESSAGE_CREATED", "DRUG_CHAT_URGENT_ROUTE" if payload["urgent"] else "DRUG_KNOWLEDGE_RETRIEVED"):
        add_audit_event(db, event, user_id=user.id, resource_type="drug_chat_message", resource_id=str(response_id),
                        details={"intent": payload["intent"], "evidence_status": payload["evidence_status"], "urgent": payload["urgent"]})
    if payload.get("response_validation_failed"):
        add_audit_event(db, "DRUG_RESPONSE_VALIDATION_FAILED", user_id=user.id,
                        resource_type="drug_chat_message", resource_id=str(response_id),
                        details={"intent": payload["intent"]})
    db.commit()
    return response
