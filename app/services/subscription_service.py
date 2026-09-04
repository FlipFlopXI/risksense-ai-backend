from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.subscription import (
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.schemas.subscriptions import (
    SubscriptionCreateRequest,
    SubscriptionUpdateRequest,
)


def get_patient_by_user_id(
    db: Session,
    user_id: UUID,
) -> Patient | None:
    statement = select(Patient).where(
        Patient.user_id == user_id
    )
    return db.scalar(statement)


def get_subscription(
    db: Session,
    patient_id: UUID,
) -> Subscription | None:
    statement = select(Subscription).where(
        Subscription.patient_id == patient_id
    )
    return db.scalar(statement)


def create_subscription(
    db: Session,
    patient: Patient,
    request: SubscriptionCreateRequest,
) -> Subscription:
    existing_subscription = get_subscription(
        db,
        patient.id,
    )

    if existing_subscription:
        raise ValueError(
            "Subscription already exists for this patient."
        )

    subscription = Subscription(
        patient_id=patient.id,
        plan=request.plan,
        status=SubscriptionStatus.ACTIVE,
    )

    db.add(subscription)
    db.commit()
    db.refresh(subscription)

    return subscription


def update_subscription(
    db: Session,
    subscription: Subscription,
    request: SubscriptionUpdateRequest,
) -> Subscription:
    update_data = request.model_dump(
        exclude_unset=True
    )

    for field, value in update_data.items():
        setattr(subscription, field, value)

    db.commit()
    db.refresh(subscription)

    return subscription