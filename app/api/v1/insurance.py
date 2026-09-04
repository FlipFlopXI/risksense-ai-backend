from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_database,
    require_role,
)
from app.models.user import User, UserRole
from app.schemas.insurance import (
    InsuranceCreateRequest,
    InsuranceResponse,
    InsuranceUpdateRequest,
)
from app.services.insurance_service import (
    create_insurance,
    get_insurance,
    get_patient_by_user_id,
    update_insurance,
)


router = APIRouter(
    prefix="/insurance",
    tags=["Insurance"],
)


@router.post(
    "/",
    response_model=InsuranceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_patient_insurance(
    request: InsuranceCreateRequest,
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

    try:
        return create_insurance(
            db,
            patient,
            request,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/",
    response_model=InsuranceResponse,
)
def get_patient_insurance(
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

    insurance = get_insurance(
        db,
        patient.id,
    )

    if not insurance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insurance information not found.",
        )

    return insurance


@router.put(
    "/",
    response_model=InsuranceResponse,
)
def update_patient_insurance(
    request: InsuranceUpdateRequest,
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

    insurance = get_insurance(
        db,
        patient.id,
    )

    if not insurance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insurance information not found.",
        )

    return update_insurance(
        db,
        insurance,
        request,
    )