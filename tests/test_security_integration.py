from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.access_entitlement import AccessEntitlement, EntitlementStatus
from app.models.audit import AuditLog
from app.models.clinician import Clinician, ClinicianApprovalStatus
from app.models.insurance import Insurance, InsuranceVerificationStatus
from app.models.patient import Patient
from app.models.patient_clinician import PatientClinician, PatientClinicianStatus
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.services.entitlement_service import get_effective_entitlement
from app.services.verification_service import staged_activate_subscription


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(user: User) -> str:
    return create_access_token(str(user.id), user.role.value)


def _user(db, role: UserRole, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("SafeTestPassword123!"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _patient(db, email: str) -> tuple[User, Patient]:
    user = _user(db, UserRole.PATIENT, email)
    patient = Patient(user_id=user.id, first_name="Test", last_name="Patient")
    db.add(patient)
    db.flush()
    return user, patient


def _clinician(
    db,
    email: str,
    risk_sense_id: str,
    approval: ClinicianApprovalStatus,
) -> tuple[User, Clinician]:
    user = _user(db, UserRole.CLINICIAN, email)
    clinician = Clinician(
        user_id=user.id,
        risk_sense_id=risk_sense_id,
        approval_status=approval,
        approved_at=datetime.now(timezone.utc) if approval == ClinicianApprovalStatus.APPROVED else None,
        first_name="Test",
        last_name="Clinician",
        license_number=f"LIC-{risk_sense_id}",
    )
    db.add(clinician)
    db.flush()
    return user, clinician


def test_patient_registration_login_and_jwt_failures_are_database_backed(client, db):
    response = client.post("/auth/register", json={
        "email": "registered.patient@example.com",
        "password": "SafeTestPassword123!",
        "first_name": "Registered",
        "last_name": "Patient",
    })
    assert response.status_code == 201
    user_id = response.json()["id"]
    patient = db.scalar(select(Patient).where(Patient.user_id == UUID(user_id)))
    assert patient is not None

    login = client.post("/auth/login", data={
        "username": "registered.patient@example.com",
        "password": "SafeTestPassword123!",
    })
    assert login.status_code == 200
    assert client.get("/auth/me", headers=_auth(login.json()["access_token"])).status_code == 200

    assert client.get("/auth/me", headers=_auth("not-a-jwt")).status_code == 401
    expired = jwt.encode(
        {"sub": user_id, "type": "access", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    assert client.get("/auth/me", headers=_auth(expired)).status_code == 401
    actions = set(db.scalars(select(AuditLog.action)).all())
    assert {"REGISTER", "LOGIN_SUCCESS", "INVALID_TOKEN"} <= actions


def test_patient_requests_cannot_set_authoritative_subscription_or_insurance_state(client, db):
    patient_user, patient = _patient(db, "state.patient@example.test")
    _clinician(db, "approved.state@example.test", "RS-CLN-10001", ClinicianApprovalStatus.APPROVED)
    db.commit()
    headers = _auth(_token(patient_user))

    subscription = client.post("/subscriptions/", headers=headers, json={
        "plan": "premium", "clinician_risk_sense_id": "RS-CLN-10001",
        "status": "active", "expires_at": "2099-01-01T00:00:00Z",
    })
    assert subscription.status_code == 422
    assert db.scalar(select(Subscription).where(Subscription.patient_id == patient.id)) is None

    insurance = client.post("/insurance/", headers=headers, json={
        "provider_name": "Test Health", "clinician_risk_sense_id": "RS-CLN-10001",
        "verification_status": "verified", "coverage_status": "active",
    })
    assert insurance.status_code == 422
    assert db.scalar(select(Insurance).where(Insurance.patient_id == patient.id)) is None

    valid_subscription = client.post("/subscriptions/", headers=headers, json={
        "plan": "premium", "clinician_risk_sense_id": "RS-CLN-10001",
    })
    assert valid_subscription.status_code == 201
    assert valid_subscription.json()["status"] == "pending"
    valid_insurance = client.post("/insurance/", headers=headers, json={
        "provider_name": "Test Health", "clinician_risk_sense_id": "RS-CLN-10001",
    })
    assert valid_insurance.status_code == 201
    assert valid_insurance.json()["verification_status"] == "pending"
    assert valid_insurance.json()["coverage_status"] == "pending"


def test_staged_subscription_activation_requires_approved_clinician_and_creates_security_records(client, db):
    admin = _user(db, UserRole.ADMIN, "activation.admin@example.test")
    patient_user, patient = _patient(db, "activation.patient@example.test")
    clinician_user, clinician = _clinician(
        db, "approved.activation@example.test", "RS-CLN-10002", ClinicianApprovalStatus.APPROVED
    )
    subscription = Subscription(
        patient_id=patient.id,
        requested_clinician_risk_sense_id=clinician.risk_sense_id,
        plan="premium",
        status=SubscriptionStatus.PENDING,
    )
    db.add(subscription)
    db.commit()

    denied = client.post(
        "/access/mock/subscription/complete",
        headers=_auth(_token(patient_user)),
        json={"patient_id": str(patient.id), "days": 30},
    )
    assert denied.status_code == 403

    activated = client.post(
        "/access/mock/subscription/complete",
        headers=_auth(_token(admin)),
        json={"patient_id": str(patient.id), "days": 30},
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    db.expire_all()
    assert db.get(Subscription, subscription.id).status == SubscriptionStatus.ACTIVE
    link = db.scalar(select(PatientClinician).where(
        PatientClinician.patient_id == patient.id,
        PatientClinician.clinician_id == clinician.id,
    ))
    assert link is not None and link.status == PatientClinicianStatus.ACTIVE
    entitlement = db.scalar(select(AccessEntitlement).where(AccessEntitlement.patient_id == patient.id))
    assert entitlement is not None and entitlement.status == EntitlementStatus.ACTIVE
    assert get_effective_entitlement(db, patient.id).id == entitlement.id
    actions = set(db.scalars(select(AuditLog.action)).all())
    assert {"UNAUTHORIZED_ACCESS_ATTEMPT", "CLINICIAN_LINKED", "ENTITLEMENT_ACTIVATED", "SUBSCRIPTION_ACTIVATION"} <= actions

    _, unlinked_patient = _patient(db, "unlinked.patient@example.test")
    db.commit()
    clinician_headers = _auth(_token(clinician_user))
    assert client.get(f"/clinicians/patients/{unlinked_patient.id}", headers=clinician_headers).status_code == 404
    assert client.get(f"/clinicians/patients/{patient.id}", headers=clinician_headers).status_code == 200


def test_unapproved_clinician_is_rejected_and_expired_entitlement_is_ineffective(db):
    admin = _user(db, UserRole.ADMIN, "service.admin@example.test")
    _, patient = _patient(db, "service.patient@example.test")
    _, clinician = _clinician(
        db, "unapproved.service@example.test", "RS-CLN-10003", ClinicianApprovalStatus.PENDING
    )
    subscription = Subscription(
        patient_id=patient.id,
        requested_clinician_risk_sense_id=clinician.risk_sense_id,
        plan="premium",
        status=SubscriptionStatus.PENDING,
    )
    db.add(subscription)
    db.commit()
    try:
        staged_activate_subscription(db, patient, subscription, clinician.risk_sense_id, admin.id)
        assert False, "unapproved clinician was accepted"
    except ValueError as exc:
        assert str(exc) == "Approved clinician not found."
        db.rollback()
    assert db.scalar(select(PatientClinician).where(PatientClinician.patient_id == patient.id)) is None
    assert db.scalar(select(AccessEntitlement).where(AccessEntitlement.patient_id == patient.id)) is None

    clinician.approval_status = ClinicianApprovalStatus.APPROVED
    clinician.approved_at = datetime.now(timezone.utc)
    db.commit()
    entitlement = staged_activate_subscription(
        db, patient, subscription, clinician.risk_sense_id, admin.id, days=1
    )
    # Model a previously verified entitlement whose valid coverage period ended.
    now = datetime.now(timezone.utc)
    entitlement.verified_at = now - timedelta(days=2)
    subscription.started_at = entitlement.verified_at
    entitlement.expires_at = now - timedelta(days=1)
    subscription.expires_at = entitlement.expires_at
    db.commit()
    assert get_effective_entitlement(db, patient.id) is None


def test_staged_insurance_verification_is_admin_only_and_audited(client, db):
    admin = _user(db, UserRole.ADMIN, "insurance.admin@example.test")
    patient_user, patient = _patient(db, "insurance.patient@example.test")
    _, clinician = _clinician(
        db, "approved.insurance@example.test", "RS-CLN-10004", ClinicianApprovalStatus.APPROVED
    )
    insurance = Insurance(
        patient_id=patient.id,
        requested_clinician_risk_sense_id=clinician.risk_sense_id,
        provider_name="Test Health",
        coverage_status="pending",
        verification_status=InsuranceVerificationStatus.PENDING,
    )
    db.add(insurance)
    db.commit()
    payload = {"patient_id": str(patient.id)}
    assert client.post(
        "/access/mock/insurance/complete", headers=_auth(_token(patient_user)), json=payload
    ).status_code == 403
    response = client.post(
        "/access/mock/insurance/complete", headers=_auth(_token(admin)), json=payload
    )
    assert response.status_code == 200
    db.expire_all()
    migrated = db.get(Insurance, insurance.id)
    assert migrated.verification_status == InsuranceVerificationStatus.VERIFIED
    assert migrated.verification_source == "MOCK_INSURANCE"
    actions = set(db.scalars(select(AuditLog.action)).all())
    assert {"INSURANCE_VERIFICATION", "ENTITLEMENT_ACTIVATED", "CLINICIAN_LINKED"} <= actions
