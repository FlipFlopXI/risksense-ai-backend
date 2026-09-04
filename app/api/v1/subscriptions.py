from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_database,
    require_role,
)
from app.models.user import User, UserRole
from app.schemas.subscriptions import (
    SubscriptionCreateRequest,
    SubscriptionResponse,
    SubscriptionUpdateRequest,
)
from app.services.subscription_service import (
    create_subscription,
    get_patient_by_user_id,
    get_subscription,
    update_subscription,
)


router = APIRouter(
    prefix="/subscriptions",
    tags=["Subscriptions"],
)


@router.post(
    "/",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_patient_subscription(
    request: SubscriptionCreateRequest,
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
        return create_subscription(
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
    response_model=SubscriptionResponse,
)
def get_patient_subscription(
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

    subscription = get_subscription(
        db,
        patient.id,
    )

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found.",
        )

    return subscription


@router.put(
    "/",
    response_model=SubscriptionResponse,
)
def update_patient_subscription(
    request: SubscriptionUpdateRequest,
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

    subscription = get_subscription(
        db,
        patient.id,
    )

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found.",
        )

    return update_subscription(
        db,
        subscription,
        request,
    )