from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_database, require_role
from app.models.lab_result import LabTestType
from app.models.patient import Patient
from app.models.user import User, UserRole
from app.schemas.labs import LabResultCreateRequest, LabResultResponse
from app.services.health_service import get_patient_by_user_id
from app.services.lab_service import create_lab_result, list_lab_results

router = APIRouter(prefix="/health/labs", tags=["Laboratory Results"])


def patient_for(user: User, db: Session) -> Patient:
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    return patient


@router.post("/", response_model=LabResultResponse, status_code=status.HTTP_201_CREATED)
def create(request: LabResultCreateRequest, user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    try:
        return create_lab_result(db, patient_for(user, db).id, request, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/", response_model=list[LabResultResponse])
def list_results(test_type: LabTestType | None = None, limit: int = Query(100, ge=1, le=200), user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    return list_lab_results(db, patient_for(user, db).id, test_type, limit)
