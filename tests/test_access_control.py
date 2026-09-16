from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from app.models.access_entitlement import EntitlementSource, EntitlementStatus
from app.models.insurance import InsuranceVerificationStatus
from app.models.subscription import SubscriptionStatus
from app.schemas.insurance import InsuranceCreateRequest
from app.schemas.subscriptions import SubscriptionUpdateRequest


def test_patient_cannot_submit_subscription_status_or_expiry():
    try:
        SubscriptionUpdateRequest(status="active", expires_at=datetime.now(timezone.utc) + timedelta(days=30))
        assert False, "authoritative subscription fields were accepted"
    except ValidationError:
        pass


def test_patient_cannot_submit_insurance_verification():
    try:
        InsuranceCreateRequest(provider_name="Example", clinician_risk_sense_id="RS-CLN-00001", verification_status="verified")
        assert False, "insurance verification state was accepted"
    except ValidationError:
        pass


def test_security_state_values_are_explicit():
    assert SubscriptionStatus.PENDING.value == "pending"
    assert InsuranceVerificationStatus.PENDING.value == "pending"
    assert EntitlementSource.INSURANCE.value == "insurance"
    assert EntitlementStatus.ACTIVE.value == "active"
