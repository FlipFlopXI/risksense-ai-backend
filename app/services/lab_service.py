from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lab_result import LabResult, LabTestType
from app.schemas.labs import LabResultCreateRequest
from app.services.audit_service import add_audit_event


def create_lab_result(db: Session, patient_id: UUID, request: LabResultCreateRequest, actor_id: UUID) -> LabResult:
    if request.measured_at.tzinfo is None or request.measured_at > datetime.now(timezone.utc):
        raise ValueError("measured_at must be timezone-aware and cannot be in the future.")
    result = LabResult(patient_id=patient_id, test_type=request.test_type, value=request.value, unit=request.unit.strip(), source=request.source.strip(), measured_at=request.measured_at)
    db.add(result)
    db.flush()
    add_audit_event(db, "LAB_RESULT_CREATED", user_id=actor_id, resource_type="lab_result", resource_id=str(result.id), details={"test_type": request.test_type.value})
    db.commit()
    db.refresh(result)
    return result


def list_lab_results(db: Session, patient_id: UUID, test_type: LabTestType | None = None, limit: int = 100) -> list[LabResult]:
    query = select(LabResult).where(LabResult.patient_id == patient_id)
    if test_type:
        query = query.where(LabResult.test_type == test_type)
    return list(db.scalars(query.order_by(LabResult.measured_at.desc()).limit(limit)).all())
