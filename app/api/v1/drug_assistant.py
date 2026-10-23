from collections.abc import Generator
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.dependencies import get_database, get_current_user, require_role
from app.ml.drug_assistant.runtime import AssistantUnavailable, load_runtime, normalize, thaw
from app.ml.drug_assistant.composer import public_drug
from app.ml.drug_assistant.provider import reviewed_sources
from app.models.user import User, UserRole
from app.schemas.drug_assistant import ChatRequest, ChatResponse, SessionCreate, SessionUpdate, SessionResponse, MessageResponse, DrugSummary
from app.services import drug_assistant_service as service
from app.api.v1.clinicians import current_clinician

router = APIRouter(prefix="/drug-assistant", tags=["Drug Assistant"])


def catalogue_user(user: User = Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN)), db: Session = Depends(get_database)):
    if user.role == UserRole.CLINICIAN:
        current_clinician(user, db)
    return user


def assistant_database(db: Session = Depends(get_database)) -> Generator[Session, None, None]:
    try:
        yield db
    except (AssistantUnavailable, SQLAlchemyError):
        db.rollback()
        raise HTTPException(503, detail={"code": "DRUG_ASSISTANT_UNAVAILABLE", "message": "Drug Assistant is temporarily unavailable."}) from None
    except Exception:
        db.rollback()
        raise


def catalogue_runtime():
    try:
        return load_runtime()
    except AssistantUnavailable:
        raise HTTPException(503, detail={"code": "DRUG_ARTIFACT_INVALID", "message": "Drug catalogue is unavailable."}) from None


@router.post("/sessions", response_model=SessionResponse, status_code=201)
def create_session(request: SessionCreate, user: User = Depends(get_current_user), db: Session = Depends(assistant_database)):
    return service.create_session(db, user, request)


@router.get("/sessions", response_model=list[SessionResponse])
def sessions(patient_id: UUID | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
             user: User = Depends(get_current_user), db: Session = Depends(assistant_database)):
    return service.list_sessions(db, user, patient_id, limit, offset)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def session(session_id: UUID, patient_id: UUID | None = None, user: User = Depends(get_current_user), db: Session = Depends(assistant_database)):
    return service.session_for(db, user, session_id, patient_id)[0]


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
def close(session_id: UUID, request: SessionUpdate, patient_id: UUID | None = None, user: User = Depends(get_current_user), db: Session = Depends(assistant_database)):
    return service.close_session(db, user, session_id, patient_id)


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
def messages(session_id: UUID, patient_id: UUID | None = None, limit: int = Query(50, ge=1, le=100), after_sequence: int = Query(0, ge=0),
             user: User = Depends(get_current_user), db: Session = Depends(assistant_database)):
    return service.list_messages(db, user, session_id, patient_id, limit, after_sequence)


@router.post("/chat", response_model=ChatResponse, status_code=201)
def chat(request: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(assistant_database)):
    return service.chat(db, user, request)


@router.get("/drugs", response_model=list[DrugSummary])
def drugs(q: str = Query("", max_length=100), limit: int = Query(50, ge=1, le=208), offset: int = Query(0, ge=0),
          user: User = Depends(catalogue_user), runtime=Depends(catalogue_runtime)):
    ids = [drug_id for drug_id, record in runtime.drugs.items() if not q or any(normalize(q) in normalize(name) for name in (record["generic_name"], *record["aliases"]))]
    return [public_drug(runtime, drug_id) for drug_id in sorted(ids)[offset:offset + limit]]


@router.get("/drugs/{drug_id}", response_model=DrugSummary)
def drug(drug_id: str, user: User = Depends(catalogue_user), runtime=Depends(catalogue_runtime)):
    if drug_id not in runtime.drugs:
        raise HTTPException(404, detail={"code": "UNSUPPORTED_DRUG", "message": "Medication not in catalogue."})
    return public_drug(runtime, drug_id)


@router.get("/drugs/{drug_id}/sources")
def sources(drug_id: str, user: User = Depends(catalogue_user), runtime=Depends(catalogue_runtime)):
    if drug_id not in runtime.drugs:
        raise HTTPException(404, detail={"code": "UNSUPPORTED_DRUG", "message": "Medication not in catalogue."})
    record = runtime.drugs[drug_id]
    return {"drug_id": drug_id, "reviewed_sources": list(reviewed_sources(record)),
            "retrieval_mappings": thaw(record["sources"]), "notice": "Retrieval mappings are reference destinations, not evidence retrieved for this medication."}
