from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_current_user,
    get_database,
    require_role,
)
from app.models.user import User, UserRole
from app.schemas.health import (
    HealthProfileCreateRequest,
    HealthProfileResponse,
    HealthProfileUpdateRequest,
)
from app.services.health_service import (
    create_health_profile,
    get_health_profile,
    get_patient_by_user_id,
    update_health_profile,
)


router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.post(
    "/profile",
    response_model=HealthProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile(
    request: HealthProfileCreateRequest,
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
        return create_health_profile(
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
    "/profile",
    response_model=HealthProfileResponse,
)
def get_profile(
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

    profile = get_health_profile(
        db,
        patient.id,
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health profile not found.",
        )

    return profile


@router.put(
    "/profile",
    response_model=HealthProfileResponse,
)
def update_profile(
    request: HealthProfileUpdateRequest,
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

    profile = get_health_profile(
        db,
        patient.id,
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health profile not found.",
        )

    return update_health_profile(
        db,
        profile,
        request,
    )