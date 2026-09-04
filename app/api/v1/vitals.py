from fastapi import APIRouter, Depends, HTTPException, Query, status

from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_current_user,
    get_database,
    require_role,
)
from app.models.user import User, UserRole
from app.schemas.vitals import (
    VitalBatchCreateRequest,
    VitalBatchResponse,
    VitalCreateRequest,
    VitalResponse,
)
from app.services.vitals_service import (
    create_vital,
    create_vital_batch,
    get_latest_vital,
    get_patient_by_user_id,
    get_patient_vitals,
)


router = APIRouter(
    prefix="/health/vitals",
    tags=["Vitals"],
)


@router.post(
    "/",
    response_model=VitalResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_patient_vital(
    request: VitalCreateRequest,
    current_user: User = Depends(
        require_role(UserRole.PATIENT)
    ),
    db: Session = Depends(get_database),
):
    patient = get_patient_by_user_id(
        db,
        current_user.id,
    )

    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )

    return create_vital(
        db,
        patient,
        request,
    )


@router.get(
    "/",
    response_model=list[VitalResponse],
)
def get_patient_vital_history(
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    current_user: User = Depends(
        require_role(UserRole.PATIENT)
    ),
    db: Session = Depends(get_database),
):
    patient = get_patient_by_user_id(
        db,
        current_user.id,
    )

    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )

    return get_patient_vitals(
        db,
        patient.id,
        limit,
    )


@router.get(
    "/latest",
    response_model=VitalResponse,
)
def get_patient_latest_vital(
    current_user: User = Depends(
        require_role(UserRole.PATIENT)
    ),
    db: Session = Depends(get_database),
):
    patient = get_patient_by_user_id(
        db,
        current_user.id,
    )

    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )

    vital = get_latest_vital(
        db,
        patient.id,
    )

    if not vital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No vital records found.",
        )

    return vital


@router.post(
    "/batch",
    response_model=VitalBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_patient_vitals_batch(
    request: VitalBatchCreateRequest,
    current_user: User = Depends(
        require_role(UserRole.PATIENT)
    ),
    db: Session = Depends(get_database),
):
    patient = get_patient_by_user_id(
        db,
        current_user.id,
    )

    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )

    vitals = create_vital_batch(
        db,
        patient,
        request.vitals,
    )

    return VitalBatchResponse(
        vitals=vitals,
        count=len(vitals),
    )